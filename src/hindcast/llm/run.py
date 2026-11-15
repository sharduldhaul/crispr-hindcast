"""Run the language-model forecaster on one slice and grade it.

Contract. In: a cutoff, a retrieval condition and a model ID. Out: an
`LLMSliceResult` written to `eval/results/llm/`, graded by the same adversary
and grader as every rule-based row.

The separation that matters here: the forecaster is handed the slice and the
candidate symbols and nothing else. The rule book is read in this module for
two purposes only, to drop candidates whose role was already established
before the cutoff (the rule-based forecaster is told the same) and to grade
the finished forecast. The traps are built after the model has answered, and
grounding is checked last, as a separate step the grader never sees.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hindcast import provenance
from hindcast.agents.adversary import Adversary
from hindcast.agents.grader import Grader, Scorecard
from hindcast.llm.client import DEFAULT_MODEL_ID, ReplayCache, Transport
from hindcast.llm.forecaster import LLMForecaster, ModelRun, RetrievalCondition, RunStatus
from hindcast.llm.grounding import GroundingReport, check_grounding
from hindcast.llm.memorization import MemorizationReport, check_memorization
from hindcast.pipeline import DEFAULT_DB, RESULTS_DIR, _check_alias_resolution, load_rulebook
from hindcast.provenance import ProvenanceReport
from hindcast.scope import ALL_SCOPE_GENES
from hindcast.store import Store

LLM_RESULTS_DIR = RESULTS_DIR / "llm"


class LLMSliceResult(BaseModel):
    """One language-model row: what was asked, what came back and how it scored.

    `scorecard`, `grounding` and `memorization` are present exactly when `run.status` is `ran`.
    """

    model_config = ConfigDict(extra="forbid")

    cutoff: str
    run_id: str
    run: ModelRun
    scorecard: Scorecard | None = None
    grounding: GroundingReport | None = None
    memorization: MemorizationReport | None = None
    trap_count: int = 0
    provenance_report: ProvenanceReport | None = None
    slice_manifest: dict[str, str] = Field(default_factory=dict)


def candidate_symbols(establishment: dict[str, dict], cutoff: date) -> list[str]:
    """Scope genes whose role was not yet established before the cutoff."""
    established_before = {
        symbol
        for symbol, entry in establishment.items()
        if entry.get("established")
        and entry.get("establishing_record")
        and date.fromisoformat(entry["establishing_record"]["date"][:10]) < cutoff
    }
    return sorted(set(ALL_SCOPE_GENES) - established_before)


def run_llm_slice(
    cutoff: date,
    condition: RetrievalCondition,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    store_path: Path | str = DEFAULT_DB,
    cache: ReplayCache | None = None,
    transport: Transport | None = None,
    trajectory_dir: Path | None = None,
    results_dir: Path | None = None,
) -> LLMSliceResult:
    """Ask the model, grade the answer, write the result. Offline unless `transport` is given."""
    run_id = f"{cutoff.isoformat()}_llm-{condition}"
    store = Store(store_path)
    try:
        slice_store = store.open_slice(cutoff)
        try:
            slice_store.assert_no_leak()
            establishment = load_rulebook()

            forecaster = LLMForecaster(run_id, trajectory_dir=trajectory_dir)
            run = forecaster.run(
                slice_store,
                candidates=candidate_symbols(establishment, cutoff),
                condition=condition,
                model_id=model_id,
                cache=cache or ReplayCache(),
                transport=transport,
            )
            result = LLMSliceResult(
                cutoff=cutoff.isoformat(),
                run_id=run_id,
                run=run,
                slice_manifest=slice_store.manifest(),
            )

            if run.status is RunStatus.RAN:
                assert run.forecast is not None
                adversary = Adversary(run_id, trajectory_dir=trajectory_dir)
                traps = adversary.run(
                    store, slice_store, establishment=establishment, cutoff=cutoff
                )
                # Checked against the slice, not the full store: an ID dated
                # after the cutoff is one the model could not have been given.
                prov = provenance.check_forecast(run.forecast, slice_store)
                card = Grader(run_id, trajectory_dir=trajectory_dir).run(
                    run.forecast,
                    traps,
                    establishment=establishment,
                    cutoff=cutoff,
                    provenance_check=prov.as_grader_input(),
                    alias_check=_check_alias_resolution(slice_store, traps),
                )
                card.notes.append(
                    "Language-model row. A refusal carries no confidence from the model "
                    "and is entered at 0 for the calibration error. The cost lens does "
                    "not apply: the model is not asked for a therapeutic route."
                )
                result.scorecard = card
                # After the grader, and never passed to it: the grader scores
                # the forecast and stays blind to how it was supported.
                result.grounding = check_grounding(run, slice_store, store)
                result.memorization = check_memorization(card, result.grounding)
                result.trap_count = len(traps.traps)
                result.provenance_report = prov

            target = results_dir or LLM_RESULTS_DIR
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{run_id}.json").write_text(
                json.dumps(result.model_dump(), indent=2, sort_keys=True, default=str)
            )
            return result
        finally:
            slice_store.close()
    finally:
        store.close()
