"""Assemble the ranked forecast from the belief map, and apply the cost lens.

Two rankings are produced and both are reported. One is by confidence alone.
The other is by confidence times the cost weight of the implied therapeutic
route. Showing both side by side is the point: the reordering between them is
the claim the cost lens makes, and a reader should be able to see it rather than
take it on trust.

Genes whose HbF role was already established before the cutoff are separated
out rather than ranked. Ranking them would inflate precision with facts the
system was handed, and this benchmark is about what comes next.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.base import Agent
from hindcast.agents.belief_reviser import BeliefMap, Claim
from hindcast.cost import COST_WEIGHTS, cost_weighted_score
from hindcast.models import CostClass


class ForecastItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank_by_confidence: int
    rank_by_cost_impact: int
    gene_symbol: str
    gene_id: str
    claim_id: str
    confidence: float
    implied_modality: str
    modality_rationale: str
    cost_weight: float
    cost_impact: float
    evidence_count: int
    max_supporting_weight: float
    supporting_record_ids: list[str] = Field(default_factory=list)
    contradicting_record_ids: list[str] = Field(default_factory=list)
    statement: str = ""


class Refusal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gene_symbol: str
    gene_id: str
    claim_id: str
    confidence: float
    reason: str
    evidence_count: int
    max_supporting_weight: float


class Forecast(BaseModel):
    """What the system predicts, and what it declines to predict."""

    model_config = ConfigDict(extra="forbid")

    cutoff: str
    items: list[ForecastItem] = Field(default_factory=list)
    refusals: list[Refusal] = Field(default_factory=list)
    already_established: list[str] = Field(default_factory=list)
    ranking_note: str = ""

    def symbols_by_confidence(self) -> list[str]:
        return [i.gene_symbol for i in sorted(self.items, key=lambda x: x.rank_by_confidence)]

    def symbols_by_cost_impact(self) -> list[str]:
        return [i.gene_symbol for i in sorted(self.items, key=lambda x: x.rank_by_cost_impact)]

    def refused_symbols(self) -> set[str]:
        return {r.gene_symbol for r in self.refusals}


class Forecaster(Agent):
    name = "forecaster"

    def run(
        self,
        belief: BeliefMap,
        *,
        established_before_cutoff: set[str],
        include_established: bool = False,
    ) -> Forecast:
        with self.tool("partition_claims", claims=len(belief.claims)) as call:
            candidates: list[Claim] = []
            established: list[str] = []
            for claim in belief.claims.values():
                if claim.gene_symbol in established_before_cutoff and not include_established:
                    established.append(claim.gene_symbol)
                    continue
                candidates.append(claim)
            call.records_in = len(belief.claims)
            call.records_out = len(candidates)
            call.result_summary = (
                f"{len(established)} genes already established before the cutoff were "
                f"set aside; {len(candidates)} remain as forecast candidates"
            )

        with self.tool("apply_refusal_rule") as call:
            reportable = [c for c in candidates if c.reportable]
            refused = [c for c in candidates if not c.reportable]
            call.records_out = len(reportable)
            call.result_summary = (
                f"{len(reportable)} claims clear the refusal thresholds, "
                f"{len(refused)} are refused"
            )

        with self.tool("rank_two_ways") as call:
            by_conf = sorted(reportable, key=lambda c: (-c.confidence, c.gene_symbol))
            scored: dict[str, float] = {}
            for claim in reportable:
                cost_class = _cost_class(claim.implied_modality)
                scored[claim.id] = cost_weighted_score(claim.confidence, cost_class)
            by_cost = sorted(
                reportable, key=lambda c: (-scored[c.id], -c.confidence, c.gene_symbol)
            )
            conf_rank = {c.id: i + 1 for i, c in enumerate(by_conf)}
            cost_rank = {c.id: i + 1 for i, c in enumerate(by_cost)}

            items = []
            for claim in by_conf:
                cost_class = _cost_class(claim.implied_modality)
                items.append(
                    ForecastItem(
                        rank_by_confidence=conf_rank[claim.id],
                        rank_by_cost_impact=cost_rank[claim.id],
                        gene_symbol=claim.gene_symbol,
                        gene_id=claim.gene_id,
                        claim_id=claim.id,
                        confidence=round(claim.confidence, 6),
                        implied_modality=str(cost_class),
                        modality_rationale=claim.modality_rationale,
                        cost_weight=COST_WEIGHTS[cost_class],
                        cost_impact=round(scored[claim.id], 6),
                        evidence_count=claim.evidence_count,
                        max_supporting_weight=round(claim.max_supporting_weight, 6),
                        supporting_record_ids=claim.supporting_record_ids[:40],
                        contradicting_record_ids=claim.contradicting_record_ids[:40],
                        statement=claim.statement,
                    )
                )
            moved = sum(1 for i in items if i.rank_by_confidence != i.rank_by_cost_impact)
            call.records_out = len(items)
            call.result_summary = f"{moved} of {len(items)} items change rank under the cost lens"

        forecast = Forecast(
            cutoff=belief.cutoff,
            items=items,
            refusals=[
                Refusal(
                    gene_symbol=c.gene_symbol,
                    gene_id=c.gene_id,
                    claim_id=c.id,
                    confidence=round(c.confidence, 6),
                    reason=c.refusal_reason(),
                    evidence_count=c.evidence_count,
                    max_supporting_weight=round(c.max_supporting_weight, 6),
                )
                for c in sorted(refused, key=lambda c: (-c.confidence, c.gene_symbol))
            ],
            already_established=sorted(established),
            ranking_note=(
                "Two rankings are reported. rank_by_confidence is the evidence "
                "ordering. rank_by_cost_impact multiplies confidence by the cost "
                "weight of the implied route, so a moderately confident small "
                "molecule outranks a highly confident multi-edit ex vivo product."
            ),
        )
        self.finish(
            {
                "cutoff": forecast.cutoff,
                "forecast_items": len(forecast.items),
                "refusals": len(forecast.refusals),
                "already_established": len(forecast.already_established),
                "top5_by_confidence": forecast.symbols_by_confidence()[:5],
                "top5_by_cost_impact": forecast.symbols_by_cost_impact()[:5],
            }
        )
        return forecast


def _cost_class(raw: str | None) -> CostClass:
    if not raw:
        return CostClass.EX_VIVO_SINGLE_EDIT
    try:
        return CostClass(raw)
    except ValueError:
        return CostClass.EX_VIVO_SINGLE_EDIT
