"""The memorization signal, on fixture claims."""

from __future__ import annotations

from hindcast.agents.grader import Scorecard, TrapResult
from hindcast.llm.grounding import ClaimGrounding, GroundingReport, Rate
from hindcast.llm.memorization import check_memorization


def grounding(**grounded_by_symbol: bool) -> GroundingReport:
    claims = [
        ClaimGrounding(gene_symbol=s, gene_id=f"gene:{s}", grounded=g, citations=[])
        for s, g in grounded_by_symbol.items()
    ]
    empty = Rate(numerator=0, denominator=0)
    return GroundingReport(
        citation_validity=empty,
        citations_in_context=empty,
        grounded_claim_rate=Rate(
            numerator=sum(grounded_by_symbol.values()), denominator=len(claims)
        ),
        claims=claims,
    )


def scorecard(truth: list[str], traps: list[TrapResult] | None = None) -> Scorecard:
    return Scorecard(
        cutoff="2018-01-01", run_id="fixture", ground_truth_symbols=truth, traps=traps or []
    )


def trap(symbol: str, kind: str, *, passed: bool) -> TrapResult:
    return TrapResult(
        trap_id=f"trap:{symbol}",
        kind=kind,
        gene_symbol=symbol,
        correct_answer="refuse",
        system_answer="claimed",
        passed=passed,
        detail="",
    )


def test_an_ungrounded_claim_for_a_gene_established_after_the_cutoff_is_recalled():
    report = check_memorization(scorecard(["EIF2AK1"]), grounding(EIF2AK1=False))

    assert report.recalled_claims == ["EIF2AK1"]
    assert report.recalled_rate == Rate(numerator=1, denominator=1)


def test_a_grounded_claim_for_the_same_gene_is_not_counted():
    report = check_memorization(scorecard(["EIF2AK1"]), grounding(EIF2AK1=True))

    assert report.post_cutoff_claims == ["EIF2AK1"]
    assert report.recalled_claims == []
    assert report.recalled_rate == Rate(numerator=0, denominator=1)


def test_an_ungrounded_claim_for_a_gene_never_established_is_not_recall():
    report = check_memorization(scorecard(["EIF2AK1"]), grounding(NFIX=False, EIF2AK1=False))

    assert report.post_cutoff_claims == ["EIF2AK1"]
    assert report.recalled_claims == ["EIF2AK1"]


def test_failed_postdates_cutoff_traps_are_listed_and_other_traps_are_not():
    traps = [
        trap("EIF2AK1", "postdates_cutoff", passed=False),
        trap("ZNF410", "postdates_cutoff", passed=True),
        trap("NFIX", "alias", passed=False),
    ]
    report = check_memorization(scorecard(["EIF2AK1"], traps), grounding(EIF2AK1=False))

    assert report.postdates_cutoff_traps_failed == ["EIF2AK1"]


def test_with_no_post_cutoff_claim_the_rate_keeps_a_zero_denominator():
    report = check_memorization(scorecard(["EIF2AK1"]), grounding(NFIX=False))

    assert report.recalled_rate == Rate(numerator=0, denominator=0)
