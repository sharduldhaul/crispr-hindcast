"""The language-model forecaster: one question, asked of a model, per slice.

Contract. In: a slice connection, the candidate gene symbols, a retrieval
condition and a model ID. Out: a `ModelRun` that always says what happened,
with one of three statuses.

*   `ran`: the model answered and the answer matched the schema. The answer is
    converted to the same `Forecast` the rule-based system produces, so the
    existing grader scores it unchanged.
*   `failed`: the model responded, but the response was refused, cut off or
    did not match the schema. The failure is recorded with its reason and the
    response is never repaired or retried.
*   `not_run`: the request is not in the replay cache and no live transport
    was given. Nothing is estimated in its place.

What the model receives is the task, the cutoff date, the candidate symbols
and, depending on the condition, evidence read through the slice connection.
It must never receive the rule book, the answer key or the traps, and nothing
in this module imports them.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hindcast.agents.base import Agent
from hindcast.agents.forecast import Forecast, ForecastItem, Refusal
from hindcast.llm.client import (
    ModelRequest,
    ModelResponse,
    ReplayCache,
    Transport,
    cost_usd,
)
from hindcast.llm.retrieval import EvidenceRow, evidence_rows, load_record
from hindcast.models import CostClass
from hindcast.store import SliceStore


class RetrievalCondition(StrEnum):
    """What evidence the model is given."""

    NONE = "none"
    TEXT = "text"


class RunStatus(StrEnum):
    RAN = "ran"
    FAILED = "failed"
    NOT_RUN = "not_run"


SYSTEM_PROMPT = """\
You are taking part in a retrospective forecasting evaluation in human genetics.
You answer as a researcher standing at a stated cutoff date. Use only what was \
known before that date. If you recall a result published on or after the cutoff, \
do not use it and do not let it raise your confidence.\
"""

TASK_PROMPT = """\
Cutoff date: {cutoff}

Question: which of the candidate genes below will be established, in work \
published on or after the cutoff date, as regulators of fetal hemoglobin (HbF) in \
human erythroid cells? "Established" means published functional evidence that \
perturbing the gene changes HbF.

For each candidate gene, do exactly one of two things.

1. Claim it. Give a confidence between 0 and 1 that the gene's role is established \
after the cutoff, the IDs of the evidence rows that support the claim, and a \
one-sentence rationale.
2. Refuse it. If what was known before the cutoff does not support a claim, list \
the gene under refusals with a one-sentence reason. Refusing is a correct answer \
when the evidence is not there.

Order claims from most to least confident. Cite only IDs that appear in the \
evidence given to you below. Never invent an ID.

Candidate genes:
{candidates}

Evidence:
{evidence}
"""

#: Evidence block for the `none` condition.
NO_EVIDENCE = (
    "No evidence rows are provided. Answer from what was known before the cutoff "
    "date, and leave cited_ids empty for every claim."
)

#: Heading of the evidence block for the `text` condition.
TEXT_EVIDENCE_HEADER = (
    "Each row is a publication dated before the cutoff, written as "
    "[ID] publication date | title, under the candidate gene it was retrieved for. "
    "Rows were retrieved by title search. A row being listed does not mean it "
    "supports a claim. Cite a row by the ID in its brackets."
)

#: Written under a gene for which retrieval returned nothing.
NO_ROWS = "(no rows)"

#: The response schema sent to the API. It mirrors `ModelAnswer`; the range of
#: `confidence` is checked on parsing because the schema cannot state it.
ANSWER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "gene_symbol": {"type": "string"},
                    "confidence": {"type": "number"},
                    "cited_ids": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
                "required": ["gene_symbol", "confidence", "cited_ids", "rationale"],
                "additionalProperties": False,
            },
        },
        "refusals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "gene_symbol": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["gene_symbol", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims", "refusals"],
    "additionalProperties": False,
}


class ModelClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    cited_ids: list[str]
    rationale: str


class ModelRefusal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str = Field(min_length=1)
    reason: str


class ModelAnswer(BaseModel):
    """The model's answer, exactly as it parsed. Ranked claims and refusals."""

    model_config = ConfigDict(extra="forbid")

    claims: list[ModelClaim]
    refusals: list[ModelRefusal]

    @model_validator(mode="after")
    def _one_answer_per_gene(self) -> ModelAnswer:
        symbols = [c.gene_symbol for c in self.claims] + [r.gene_symbol for r in self.refusals]
        repeated = sorted({s for s in symbols if symbols.count(s) > 1})
        if repeated:
            raise ValueError(f"more than one answer for: {', '.join(repeated)}")
        return self


class DuplicateAnswerError(ValueError):
    """Two answers name the same gene once aliases are resolved."""


class ModelRun(BaseModel):
    """What one forecaster run did. Self-describing, whatever its status."""

    model_config = ConfigDict(extra="forbid")

    status: RunStatus
    status_reason: str
    condition: RetrievalCondition
    model_id: str
    served_model_id: str = ""
    prompt_hash: str
    cache_keys: list[str] = Field(default_factory=list)
    calls_replayed: int = 0
    calls_live: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    candidate_symbols: list[str]
    context_node_ids: list[str] = Field(default_factory=list)
    answer: ModelAnswer | None = None
    forecast: Forecast | None = None


class LLMForecaster(Agent):
    """Ask the model the forecasting question and type its answer."""

    name = "llm_forecaster"

    def run(
        self,
        slice_store: SliceStore,
        *,
        candidates: list[str],
        condition: RetrievalCondition,
        model_id: str,
        cache: ReplayCache,
        transport: Transport | None = None,
    ) -> ModelRun:
        slice_store.assert_no_leak()
        self.trajectory.environment["model"] = model_id
        candidates = sorted(candidates)

        evidence = NO_EVIDENCE
        context_node_ids: list[str] = []
        retrieval_missing = False
        if condition is RetrievalCondition.TEXT:
            with self.tool("replay_retrieval", cutoff=slice_store.cutoff) as call:
                record = load_record(slice_store.cutoff, candidates)
                if record is None:
                    retrieval_missing = True
                    call.result_summary = "no retrieval record: not run"
                else:
                    by_gene = evidence_rows(record, slice_store)
                    evidence = _text_evidence(by_gene)
                    context_node_ids = sorted({r.node_id for _, rows in by_gene for r in rows})
                    call.records_out = len(context_node_ids)
                    call.result_summary = (
                        f"{len(context_node_ids)} publications for {len(by_gene)} genes, "
                        f"read back through the slice"
                    )

        prompt = TASK_PROMPT.format(
            cutoff=slice_store.cutoff,
            candidates="\n".join(candidates),
            evidence=evidence,
        )
        request = ModelRequest(
            model_id=model_id,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_schema=ANSWER_JSON_SCHEMA,
        )
        run = ModelRun(
            status=RunStatus.NOT_RUN,
            status_reason="",
            condition=condition,
            model_id=model_id,
            prompt_hash=hashlib.sha256(f"{SYSTEM_PROMPT}\n{prompt}".encode()).hexdigest(),
            candidate_symbols=candidates,
            context_node_ids=context_node_ids,
        )
        inputs = {
            "cutoff": slice_store.cutoff,
            "condition": str(condition),
            "model_id": model_id,
            "candidates": len(candidates),
            "prompt_hash": run.prompt_hash,
        }

        if retrieval_missing:
            run.status_reason = (
                "No retrieval record for this cutoff in eval/model_cache/retrieval/. "
                "Run `hindcast embed-titles` and `hindcast retrieve` to write one."
            )
            self.finish(_summary(run), inputs=inputs)
            return run

        response = self._call(request, run, cache, transport)
        if response is None:
            run.status_reason = (
                "The request is not in eval/model_cache/ and no live call was made. "
                "Run `hindcast llm --live` with ANTHROPIC_API_KEY set to populate it."
            )
            self.finish(_summary(run), inputs=inputs)
            return run

        run.served_model_id = response.served_model_id
        run.cost_usd = cost_usd(model_id, run.input_tokens, run.output_tokens)

        with self.tool("parse_answer") as call:
            failure = ""
            if response.stop_reason != "end_turn":
                failure = f"the response stopped with stop_reason {response.stop_reason!r}"
            else:
                try:
                    run.answer = ModelAnswer.model_validate_json(response.text())
                except ValidationError as exc:
                    failure = (
                        f"the response did not match the answer schema "
                        f"({exc.error_count()} validation error(s))"
                    )
            if failure:
                run.status = RunStatus.FAILED
                run.status_reason = failure
                call.result_summary = failure
            else:
                assert run.answer is not None
                call.records_out = len(run.answer.claims) + len(run.answer.refusals)
                call.result_summary = (
                    f"{len(run.answer.claims)} claims, {len(run.answer.refusals)} refusals"
                )

        if run.answer is not None:
            with self.tool("build_forecast") as call:
                try:
                    run.forecast = _to_forecast(run.answer, slice_store, condition)
                except DuplicateAnswerError as exc:
                    run.status = RunStatus.FAILED
                    run.status_reason = f"two answers resolve to the same gene, {exc}"
                    call.result_summary = run.status_reason
                else:
                    run.status = RunStatus.RAN
                    call.records_out = len(run.forecast.items) + len(run.forecast.refusals)
                    call.result_summary = (
                        f"{len(run.forecast.items)} items, {len(run.forecast.refusals)} refusals"
                    )

        self.finish(_summary(run), inputs=inputs)
        return run

    def _call(
        self,
        request: ModelRequest,
        run: ModelRun,
        cache: ReplayCache,
        transport: Transport | None,
    ) -> ModelResponse | None:
        """One model call through the replay cache, with its usage added to `run`."""
        key = request.cache_key()
        with self.tool("model_call", cache_key=key) as call:
            response = cache.get(request)
            if response is not None:
                run.calls_replayed += 1
                source = "replayed from cache"
            elif transport is not None:
                response = transport(request)
                cache.put(request, response)
                run.calls_live += 1
                source = "live call, now cached"
            else:
                call.result_summary = "not in cache, no live transport: not run"
                return None
            run.cache_keys.append(key)
            run.input_tokens += response.input_tokens
            run.output_tokens += response.output_tokens
            call.records_out = 1
            call.result_summary = (
                f"{source}; {response.input_tokens} input tokens, "
                f"{response.output_tokens} output tokens, stop_reason {response.stop_reason}"
            )
            return response


def _text_evidence(by_gene: list[tuple[str, list[EvidenceRow]]]) -> str:
    lines = [TEXT_EVIDENCE_HEADER]
    for symbol, rows in by_gene:
        lines.append("")
        lines.append(symbol)
        if not rows:
            lines.append(NO_ROWS)
        lines.extend(f"[{r.node_id}] {r.publication_date} | {r.title}" for r in rows)
    return "\n".join(lines)


def _summary(run: ModelRun) -> dict[str, Any]:
    return {
        "status": str(run.status),
        "status_reason": run.status_reason,
        "calls_replayed": run.calls_replayed,
        "calls_live": run.calls_live,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_usd": run.cost_usd,
        "claims": len(run.answer.claims) if run.answer else 0,
        "refusals": len(run.answer.refusals) if run.answer else 0,
    }


def _resolve(symbol: str, slice_store: SliceStore) -> tuple[str, str]:
    """The approved symbol and gene ID for a name the model used.

    The same resolution the curator applies to every ingested record, through
    the slice, so an alias the model used is graded as the gene it names. A
    name the slice cannot resolve is kept as written and marked unresolved.
    """
    name = symbol.strip().upper()
    node = slice_store.gene_by_symbol(name)
    if node is None:
        return name, f"unresolved:{name}"
    return str(node.attrs.get("symbol") or name), node.id


def _to_forecast(
    answer: ModelAnswer, slice_store: SliceStore, condition: RetrievalCondition
) -> Forecast:
    """Convert a parsed answer to the `Forecast` the grader reads.

    Claims are ranked by the model's confidence, ties kept in the order the
    model gave them. The model is not asked for a therapeutic route, so every
    item gets the same one and both rankings are identical, as for the flat
    literature baseline.
    """
    seen: set[str] = set()
    items: list[ForecastItem] = []
    ordered = sorted(answer.claims, key=lambda c: -c.confidence)
    for claim in ordered:
        symbol, gene_id = _resolve(claim.gene_symbol, slice_store)
        if symbol in seen:
            raise DuplicateAnswerError(symbol)
        seen.add(symbol)
        rank = len(items) + 1
        items.append(
            ForecastItem(
                rank_by_confidence=rank,
                rank_by_cost_impact=rank,
                gene_symbol=symbol,
                gene_id=gene_id,
                claim_id=f"llm:claim:{symbol}",
                confidence=round(claim.confidence, 6),
                implied_modality=str(CostClass.EX_VIVO_SINGLE_EDIT),
                modality_rationale="the model is not asked for a therapeutic route",
                cost_weight=1.0,
                cost_impact=round(claim.confidence, 6),
                evidence_count=len(claim.cited_ids),
                max_supporting_weight=0.0,
                supporting_record_ids=list(claim.cited_ids),
                statement=claim.rationale,
            )
        )

    refusals: list[Refusal] = []
    for refusal in answer.refusals:
        symbol, gene_id = _resolve(refusal.gene_symbol, slice_store)
        if symbol in seen:
            raise DuplicateAnswerError(symbol)
        seen.add(symbol)
        refusals.append(
            Refusal(
                gene_symbol=symbol,
                gene_id=gene_id,
                claim_id=f"llm:claim:{symbol}",
                # The model gives a reason and no number for a refusal. Zero
                # is the stated convention; METHODOLOGY.md covers its effect
                # on the calibration error.
                confidence=0.0,
                reason=refusal.reason,
                evidence_count=0,
                max_supporting_weight=0.0,
            )
        )

    return Forecast(
        cutoff=slice_store.cutoff,
        items=items,
        refusals=refusals,
        already_established=[],
        ranking_note=(
            f"Language-model forecast, retrieval condition {condition}. Ranked by the "
            f"model's stated confidence. Both rankings are identical because the model "
            f"is not asked for a therapeutic route."
        ),
    )
