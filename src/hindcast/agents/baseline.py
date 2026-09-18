"""The no-graph baseline, for the ablation row that asks whether structure earns its place.

The brief asks for a row comparing the full system against a general model given
the same prompt and no graph. That row needs a language model, and this
repository deliberately contains none: hard rule 4 requires a clone to reproduce
the exact scorecard offline with no API keys and no network. So the row is
implemented in two halves.

The half that runs offline is `FlatLiteratureBaseline`. It receives exactly the
same pre-T evidence, with the graph structure removed: a flat count of
publications per gene, and nothing else. No ontology normalization, no method
signature, no belief revision, no essentiality, no genetic support, no cost
lens. It ranks genes by how much the pre-T literature talks about them, which is
what a reader with no structure would do. If the full system cannot beat this,
the structure is decoration.

The half that needs a model is `CachedModelBaseline`. It reads responses from a
committed cache keyed by a hash of the prompt. With no cached responses
committed, it reports the row as not run rather than inventing a result, and the
scorecard says so. Anyone with an API key can populate the cache with
`scripts/populate_model_cache.py` and the row becomes reproducible from then on,
because the cache is what is replayed and not the API.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.base import Agent
from hindcast.agents.forecast import Forecast, ForecastItem
from hindcast.models import CostClass, NodeType
from hindcast.store import SliceStore

CACHE_DIR = Path(__file__).resolve().parents[3] / "eval" / "model_cache"

#: The prompt the model baseline would be given. Committed so the comparison is
#: legible even when the row has not been run.
BASELINE_PROMPT = """\
You are given a list of human genes and, for each, the number of publications
before {cutoff} that mention the gene together with fetal hemoglobin or with the
erythroid context. Using only that information and your own knowledge as of
{cutoff}, rank the genes most likely to be found, after {cutoff}, to raise fetal
hemoglobin when lost or inhibited in human erythroid cells. Return a ranked list
of gene symbols and a confidence between 0 and 1 for each. If the information
does not support a ranking, say so.

Gene counts:
{counts}
"""


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ran: bool
    reason_not_run: str = ""
    forecast: Forecast | None = None
    prompt_hash: str = ""


class FlatLiteratureBaseline(Agent):
    """Rank genes by pre-T publication count. No graph, no weighting, no revision."""

    name = "baseline_flat_literature"

    def run(self, slice_store: SliceStore) -> BaselineResult:
        slice_store.assert_no_leak()
        with self.tool("count_publications_per_gene") as call:
            counts: Counter[str] = Counter()
            hbf_counts: Counter[str] = Counter()
            for pub in slice_store.nodes(NodeType.PUBLICATION):
                tiers = pub.attrs.get("matched_tiers") or []
                for symbol in pub.attrs.get("matched_genes") or []:
                    counts[symbol] += 1
                    if "hbf" in tiers:
                        hbf_counts[symbol] += 1
            call.records_out = len(counts)
            call.result_summary = f"{len(counts)} genes with at least one publication"

        with self.tool("rank_by_count") as call:
            # The only signal available: how much the pre-T literature talks
            # about a gene alongside fetal hemoglobin. Confidence is the share of
            # the maximum count, which is the crudest possible calibration and
            # is meant to be.
            ordered = sorted(
                counts.items(), key=lambda kv: (-hbf_counts[kv[0]], -kv[1], kv[0])
            )
            top = hbf_counts.most_common(1)
            denominator = top[0][1] if top and top[0][1] else 1
            items: list[ForecastItem] = []
            for rank, (symbol, total) in enumerate(ordered, start=1):
                confidence = min(hbf_counts[symbol] / denominator, 1.0)
                items.append(
                    ForecastItem(
                        rank_by_confidence=rank,
                        rank_by_cost_impact=rank,
                        gene_symbol=symbol,
                        gene_id=f"baseline:{symbol}",
                        claim_id=f"baseline:claim:{symbol}",
                        confidence=round(confidence, 6),
                        implied_modality=str(CostClass.EX_VIVO_SINGLE_EDIT),
                        modality_rationale=(
                            "the baseline has no cost lens; every gene is assigned the "
                            "same route so the ranking is unaffected by it"
                        ),
                        cost_weight=1.0,
                        cost_impact=round(confidence, 6),
                        evidence_count=total,
                        max_supporting_weight=0.0,
                        supporting_record_ids=[],
                        statement=(
                            f"{symbol} is mentioned in {total} pre-cutoff publications "
                            f"in an erythroid or HbF context, {hbf_counts[symbol]} of "
                            f"them naming HbF specifically."
                        ),
                    )
                )
            call.records_out = len(items)
            call.result_summary = f"{len(items)} genes ranked by raw publication count"

        forecast = Forecast(
            cutoff=slice_store.cutoff,
            items=items,
            refusals=[],
            already_established=[],
            ranking_note=(
                "No-graph baseline. Ranked by pre-cutoff publication count alone, with "
                "no ontology normalization, no method signature, no belief revision and "
                "no cost lens. Both rankings are identical because the baseline has no "
                "cost lens."
            ),
        )
        result = BaselineResult(name=self.name, ran=True, forecast=forecast)
        self.finish(
            {
                "genes_ranked": len(items),
                "top10": [i.gene_symbol for i in items[:10]],
            }
        )
        return result


class CachedModelBaseline(Agent):
    """A general model given the same prompt and no graph, replayed from cache."""

    name = "baseline_cached_model"

    def run(self, slice_store: SliceStore, *, model: str = "none") -> BaselineResult:
        counts: Counter[str] = Counter()
        for pub in slice_store.nodes(NodeType.PUBLICATION):
            for symbol in pub.attrs.get("matched_genes") or []:
                counts[symbol] += 1
        rendered = BASELINE_PROMPT.format(
            cutoff=slice_store.cutoff,
            counts="\n".join(f"{s}: {n}" for s, n in sorted(counts.items())),
        )
        prompt_hash = hashlib.sha256(rendered.encode()).hexdigest()
        cache_file = CACHE_DIR / f"{model}_{slice_store.cutoff}_{prompt_hash[:16]}.json"

        with self.tool("load_cached_response", cache_file=str(cache_file.name)) as call:
            if not cache_file.exists():
                call.result_summary = "no cached response committed"
                result = BaselineResult(
                    name=self.name,
                    ran=False,
                    prompt_hash=prompt_hash,
                    reason_not_run=(
                        "No cached model response is committed for this slice. This "
                        "repository contains no API keys and makes no network calls on "
                        "the demo path, per hard rule 4, so the model comparison row is "
                        "reported as not run rather than estimated. The prompt is "
                        "committed in hindcast.agents.baseline.BASELINE_PROMPT and the "
                        "cache key is this prompt's SHA-256. Populate "
                        f"eval/model_cache/{cache_file.name} to make the row "
                        "reproducible."
                    ),
                )
                self.finish(
                    {"ran": False, "prompt_hash": prompt_hash, "cache_file": cache_file.name}
                )
                return result

            payload = json.loads(cache_file.read_text())
            call.records_out = len(payload.get("ranking") or [])
            call.result_summary = f"replayed {call.records_out} ranked genes from cache"

        items = [
            ForecastItem(
                rank_by_confidence=rank,
                rank_by_cost_impact=rank,
                gene_symbol=entry["gene"],
                gene_id=f"cached_model:{entry['gene']}",
                claim_id=f"cached_model:claim:{entry['gene']}",
                confidence=float(entry.get("confidence", 0.0)),
                implied_modality=str(CostClass.EX_VIVO_SINGLE_EDIT),
                modality_rationale="the model baseline was not asked for a modality",
                cost_weight=1.0,
                cost_impact=float(entry.get("confidence", 0.0)),
                evidence_count=0,
                max_supporting_weight=0.0,
                supporting_record_ids=[],
                statement=entry.get("statement", ""),
            )
            for rank, entry in enumerate(payload.get("ranking") or [], start=1)
        ]
        forecast = Forecast(
            cutoff=slice_store.cutoff,
            items=items,
            refusals=[],
            already_established=[],
            ranking_note=f"Cached response from {payload.get('model', model)}, no graph.",
        )
        self.finish({"ran": True, "genes_ranked": len(items), "prompt_hash": prompt_hash})
        return BaselineResult(
            name=self.name, ran=True, forecast=forecast, prompt_hash=prompt_hash
        )
