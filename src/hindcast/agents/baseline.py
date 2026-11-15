"""The no-graph baseline, for the ablation row that asks whether structure earns its place.

`FlatLiteratureBaseline` receives exactly the same pre-T evidence as the full
system, with the graph structure removed: a flat count of publications per
gene, and nothing else. No ontology normalization, no method signature, no
belief revision, no essentiality, no genetic support, no cost lens. It ranks
genes by how much the pre-T literature talks about them, which is what a reader
with no structure would do. If the full system cannot beat this, the structure
is decoration.

It contains no language model. The comparison against a model is a separate
track, in `hindcast.llm`.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict

from hindcast.agents.base import Agent
from hindcast.agents.forecast import Forecast, ForecastItem
from hindcast.models import CostClass, NodeType
from hindcast.store import SliceStore


class BaselineResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ran: bool
    forecast: Forecast | None = None


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
            ordered = sorted(counts.items(), key=lambda kv: (-hbf_counts[kv[0]], -kv[1], kv[0]))
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
