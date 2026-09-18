"""GRADER: score the forecast against post-T ground truth.

Contract. In: a `Forecast`, a `TrapSet`, and the frozen rule book. Out: a
machine-readable scorecard.

The grader never sees pre-T reasoning, and that is enforced by its signature
rather than by instruction: `run` takes no slice, no belief map and no axiom
set. It cannot reach the evidence the forecast was built from, so it cannot
accidentally credit a forecast for reasoning it did not publish in its ranked
output.

Every metric here is computed from committed data. Nothing is estimated.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hindcast.agents.adversary import TrapSet
from hindcast.agents.base import Agent
from hindcast.agents.forecast import Forecast

#: Reliability-diagram bins for the calibration figure and the ECE.
CALIBRATION_BINS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0))


class RankingScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ranking: str
    precision_at_5: float
    precision_at_10: float
    mean_reciprocal_rank: float
    hits_at_5: list[str] = Field(default_factory=list)
    hits_at_10: list[str] = Field(default_factory=list)
    first_hit_rank: int | None = None
    n_ranked: int = 0
    n_ground_truth: int = 0


class TrapResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trap_id: str
    kind: str
    gene_symbol: str
    correct_answer: str
    system_answer: str
    passed: bool
    detail: str


class CalibrationBin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lower: float
    upper: float
    n: int
    mean_confidence: float
    observed_frequency: float


class Scorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cutoff: str
    run_id: str

    ground_truth_symbols: list[str] = Field(default_factory=list)
    forecast_size: int = 0
    refusal_count: int = 0

    ranking_by_confidence: RankingScore | None = None
    ranking_by_cost_impact: RankingScore | None = None

    traps: list[TrapResult] = Field(default_factory=list)
    traps_passed: int = 0
    traps_total: int = 0

    alias_attacks_total: int = 0
    alias_attacks_resolved: int = 0

    calibration_bins: list[CalibrationBin] = Field(default_factory=list)
    expected_calibration_error: float | None = None

    refusal_correct: int = 0
    refusal_total: int = 0
    refusal_accuracy: float | None = None

    fabricated_numbers: int = 0
    fabricated_detail: list[str] = Field(default_factory=list)

    cost_lens_reordered: int = 0
    cost_lens_top_route_by_confidence: str | None = None
    cost_lens_top_route_by_cost_impact: str | None = None
    cost_lens_surfaces_small_molecule: bool | None = None

    notes: list[str] = Field(default_factory=list)


class Grader(Agent):
    name = "grader"

    def run(
        self,
        forecast: Forecast,
        traps: TrapSet,
        *,
        establishment: dict[str, dict],
        cutoff: date,
        provenance_check: dict[str, Any] | None = None,
        alias_check: dict[str, int] | None = None,
    ) -> Scorecard:
        card = Scorecard(cutoff=forecast.cutoff, run_id=self.run_id)

        with self.tool("build_ground_truth", cutoff=cutoff.isoformat()) as call:
            truth = _ground_truth(establishment, cutoff)
            card.ground_truth_symbols = sorted(truth)
            call.records_out = len(truth)
            call.result_summary = (
                f"{len(truth)} genes whose HbF role was established on or after "
                f"{cutoff.isoformat()}"
            )

        card.forecast_size = len(forecast.items)
        card.refusal_count = len(forecast.refusals)

        with self.tool("score_rankings") as call:
            card.ranking_by_confidence = _score_ranking(
                "confidence", forecast.symbols_by_confidence(), truth
            )
            card.ranking_by_cost_impact = _score_ranking(
                "cost_impact", forecast.symbols_by_cost_impact(), truth
            )
            call.records_out = 2
            call.result_summary = (
                f"precision@5 {card.ranking_by_confidence.precision_at_5:.3f} by "
                f"confidence, {card.ranking_by_cost_impact.precision_at_5:.3f} by cost"
            )

        with self.tool("score_traps", traps=len(traps.traps)) as call:
            results = [_score_trap(t, forecast) for t in traps.traps]
            card.traps = results
            card.traps_passed = sum(1 for r in results if r.passed)
            card.traps_total = len(results)
            call.records_out = len(results)
            call.result_summary = f"{card.traps_passed}/{card.traps_total} traps passed"

        with self.tool("score_refusals") as call:
            should_refuse = {
                t.gene_symbol for t in traps.traps if t.correct_answer == "refuse"
            }
            refused = forecast.refused_symbols()
            card.refusal_total = len(should_refuse)
            card.refusal_correct = len(should_refuse & refused)
            card.refusal_accuracy = (
                card.refusal_correct / card.refusal_total if card.refusal_total else None
            )
            call.records_out = card.refusal_total
            call.result_summary = (
                f"{card.refusal_correct}/{card.refusal_total} unanswerable questions "
                f"correctly refused"
            )

        with self.tool("score_calibration") as call:
            bins, ece = _calibration(forecast, truth)
            card.calibration_bins = bins
            card.expected_calibration_error = ece
            call.records_out = len(bins)
            call.result_summary = (
                f"expected calibration error {ece:.4f}" if ece is not None else "no data"
            )

        with self.tool("check_cost_lens") as call:
            card.cost_lens_reordered = sum(
                1 for i in forecast.items if i.rank_by_confidence != i.rank_by_cost_impact
            )
            top_conf = next(
                (i for i in forecast.items if i.rank_by_confidence == 1), None
            )
            top_cost = next(
                (i for i in forecast.items if i.rank_by_cost_impact == 1), None
            )
            card.cost_lens_top_route_by_confidence = (
                top_conf.implied_modality if top_conf else None
            )
            card.cost_lens_top_route_by_cost_impact = (
                top_cost.implied_modality if top_cost else None
            )
            if top_cost is not None:
                has_small = any(
                    i.implied_modality == "SMALL_MOLECULE" for i in forecast.items
                )
                card.cost_lens_surfaces_small_molecule = (
                    top_cost.implied_modality == "SMALL_MOLECULE" if has_small else None
                )
            call.result_summary = (
                f"{card.cost_lens_reordered} items reordered; top route by cost "
                f"{card.cost_lens_top_route_by_cost_impact}"
            )

        with self.tool("check_provenance") as call:
            if provenance_check is not None:
                card.fabricated_numbers = int(provenance_check.get("untraceable", 0))
                card.fabricated_detail = list(provenance_check.get("detail", []))[:20]
            else:
                # Fall back to what the forecast itself carries: an item with a
                # confidence but no supporting record is a number with no source.
                missing = [
                    i.gene_symbol for i in forecast.items if not i.supporting_record_ids
                ]
                card.fabricated_numbers = len(missing)
                card.fabricated_detail = [
                    f"{s}: forecast item carries a confidence but no supporting record ID"
                    for s in missing[:20]
                ]
            call.result_summary = f"{card.fabricated_numbers} untraceable numbers"

        if alias_check:
            card.alias_attacks_total = int(alias_check.get("total", 0))
            card.alias_attacks_resolved = int(alias_check.get("resolved", 0))

        self.finish(card.model_dump(), inputs={"cutoff": cutoff.isoformat()})
        return card


# --------------------------------------------------------------------------
# metric implementations
# --------------------------------------------------------------------------

def _ground_truth(establishment: dict[str, dict], cutoff: date) -> set[str]:
    """Genes whose HbF role was established on or after the cutoff.

    Genes established before the cutoff are not ground truth for a forecast:
    the system was handed them. Genes never established are not ground truth
    either, and several of them are traps.
    """
    out: set[str] = set()
    for symbol, entry in establishment.items():
        record = entry.get("establishing_record")
        if not entry.get("established") or not record:
            continue
        if date.fromisoformat(record["date"][:10]) >= cutoff:
            out.add(symbol)
    return out


def _score_ranking(name: str, ranked: list[str], truth: set[str]) -> RankingScore:
    hits5 = [s for s in ranked[:5] if s in truth]
    hits10 = [s for s in ranked[:10] if s in truth]
    first = next((i + 1 for i, s in enumerate(ranked) if s in truth), None)
    return RankingScore(
        ranking=name,
        precision_at_5=round(len(hits5) / 5, 6) if ranked else 0.0,
        precision_at_10=round(len(hits10) / 10, 6) if ranked else 0.0,
        mean_reciprocal_rank=round(1 / first, 6) if first else 0.0,
        hits_at_5=hits5,
        hits_at_10=hits10,
        first_hit_rank=first,
        n_ranked=len(ranked),
        n_ground_truth=len(truth),
    )


def _score_trap(trap, forecast: Forecast) -> TrapResult:
    """Did the system fall into this trap?

    The rules are stated per expected answer:

    *   `reject`: the gene must not appear in the top ten of either ranking. A
        trap gene ranked eleventh has not been endorsed, and treating any
        appearance at all as a failure would punish the system for listing a
        candidate it ranked low.
    *   `refuse`: the gene must appear in the refusals, or be absent from the
        forecast entirely.
    *   `accept`: the gene must appear in the forecast.
    """
    by_conf = forecast.symbols_by_confidence()
    by_cost = forecast.symbols_by_cost_impact()
    in_top10 = trap.gene_symbol in set(by_conf[:10]) | set(by_cost[:10])
    refused = trap.gene_symbol in forecast.refused_symbols()
    present = trap.gene_symbol in set(by_conf)

    if trap.correct_answer == "reject":
        passed = not in_top10
        rank = by_conf.index(trap.gene_symbol) + 1 if present else None
        answer = f"ranked {rank}" if rank else ("refused" if refused else "not forecast")
        detail = (
            f"{trap.gene_symbol} was not endorsed in the top ten of either ranking"
            if passed
            else f"{trap.gene_symbol} appears in the top ten, which endorses the trap"
        )
    elif trap.correct_answer == "refuse":
        passed = refused or not present
        answer = "refused" if refused else ("forecast" if present else "not forecast")
        detail = (
            f"{trap.gene_symbol} was correctly not claimed from pre-cutoff evidence"
            if passed
            else f"{trap.gene_symbol} was forecast although its role postdates the cutoff"
        )
    else:
        passed = present
        answer = "forecast" if present else "not forecast"
        detail = f"{trap.gene_symbol} " + ("was forecast" if present else "was missed")

    return TrapResult(
        trap_id=trap.id,
        kind=trap.kind,
        gene_symbol=trap.gene_symbol,
        correct_answer=trap.correct_answer,
        system_answer=answer,
        passed=passed,
        detail=detail,
    )


def _calibration(
    forecast: Forecast, truth: set[str]
) -> tuple[list[CalibrationBin], float | None]:
    """Reliability bins and the expected calibration error.

    Computed over every claim the system put a confidence on, forecast and
    refused alike. Restricting it to the forecasts would measure calibration
    only where the system was already confident, which is the flattering half.
    """
    points: list[tuple[float, bool]] = [
        (i.confidence, i.gene_symbol in truth) for i in forecast.items
    ]
    points += [(r.confidence, r.gene_symbol in truth) for r in forecast.refusals]
    if not points:
        return [], None

    bins: list[CalibrationBin] = []
    ece = 0.0
    total = len(points)
    for lower, upper in CALIBRATION_BINS:
        inside = [
            (c, hit)
            for c, hit in points
            if (c >= lower and c < upper) or (upper == 1.0 and c == 1.0)
        ]
        if not inside:
            bins.append(
                CalibrationBin(
                    lower=lower, upper=upper, n=0, mean_confidence=0.0, observed_frequency=0.0
                )
            )
            continue
        mean_conf = sum(c for c, _ in inside) / len(inside)
        observed = sum(1 for _, hit in inside if hit) / len(inside)
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                n=len(inside),
                mean_confidence=round(mean_conf, 6),
                observed_frequency=round(observed, 6),
            )
        )
        ece += (len(inside) / total) * abs(mean_conf - observed)
    return bins, round(ece, 6)
