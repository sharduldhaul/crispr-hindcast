"""Hard rule 3: refusal is a scored outcome, and the refusal path comes first.

These tests check the refusal rule itself rather than a particular run, so they
hold whatever the data turns out to say.
"""

from __future__ import annotations

from hindcast.agents.belief_reviser import (
    MIN_SUPPORTING_WEIGHT,
    PRIOR_CONFIDENCE,
    PRIOR_LOG_ODDS,
    REFUSAL_CONFIDENCE_THRESHOLD,
    Claim,
)


def make_claim(**kw) -> Claim:
    base = dict(
        id="claim:test",
        gene_id="gene:HGNC:1",
        gene_symbol="TESTGENE",
        phenotype_id="pheno:hbf_protein",
        direction="increases",
        statement="test",
        confidence=PRIOR_CONFIDENCE,
        log_odds=PRIOR_LOG_ODDS,
    )
    base.update(kw)
    return Claim(**base)


def test_a_claim_at_the_prior_is_refused():
    claim = make_claim()
    assert not claim.reportable
    assert "does not support a claim" in claim.refusal_reason()


def test_confidence_alone_is_not_enough():
    """A pile of weak co-mentions must not make a claim reportable."""
    claim = make_claim(
        confidence=0.9, max_supporting_weight=0.01, hbf_publication_support=2,
        evidence_count=400,
    )
    assert not claim.reportable
    reason = claim.refusal_reason()
    assert "no substance" in reason
    assert "rest on co-mentions" in reason


def test_a_substantial_hbf_literature_is_the_second_route_to_reportability():
    """A gene many independent groups have published HbF papers about can be
    ranked even with no single strong measurement."""
    from hindcast.agents.belief_reviser import MIN_HBF_PUBLICATIONS

    claim = make_claim(
        confidence=0.6, max_supporting_weight=0.02,
        hbf_publication_support=MIN_HBF_PUBLICATIONS,
    )
    assert claim.has_evidence_of_substance
    assert claim.reportable

    thin = make_claim(
        confidence=0.6, max_supporting_weight=0.02,
        hbf_publication_support=MIN_HBF_PUBLICATIONS - 1,
    )
    assert not thin.has_evidence_of_substance
    assert not thin.reportable


def test_literature_contribution_is_logarithmic_not_linear():
    """The correction for treating correlated papers as independent evidence."""
    import math

    from hindcast.agents.belief_reviser import (
        LITERATURE_SCALE,
        PRIOR_LOG_ODDS,
        from_log_odds,
    )

    def confidence_after(n: int) -> float:
        return from_log_odds(PRIOR_LOG_ODDS + LITERATURE_SCALE * math.log1p(n))

    # A large literature produces belief, not certainty.
    assert 0.85 < confidence_after(200) < 0.95
    # A handful of papers stays low.
    assert confidence_after(3) < 0.25
    # The k-th publication adds less than the first. The property holds in
    # log-odds, which is where the update happens: each paper contributes
    # ln(1+k) - ln(k), a decreasing sequence.
    increments = [
        LITERATURE_SCALE * (math.log1p(k) - math.log(k)) for k in range(1, 30)
    ]
    assert increments == sorted(increments, reverse=True)
    assert increments[0] > 10 * increments[-1]

    # Linear accumulation is what this replaces. At 0.20 per paper, 200 papers
    # would add 40 log-odds and drive confidence to 1.0.
    assert from_log_odds(PRIOR_LOG_ODDS + 200 * 0.20) > 0.999
    assert confidence_after(200) < 0.95


def test_one_strong_measurement_alone_is_not_enough():
    """By design, no single measurement can establish a therapeutic claim."""
    claim = make_claim(confidence=0.224, max_supporting_weight=2.0, evidence_count=1)
    assert claim.confidence < REFUSAL_CONFIDENCE_THRESHOLD
    assert not claim.reportable


def test_a_claim_clearing_both_thresholds_is_reportable():
    claim = make_claim(
        confidence=REFUSAL_CONFIDENCE_THRESHOLD + 0.01,
        max_supporting_weight=MIN_SUPPORTING_WEIGHT + 0.01,
        evidence_count=3,
    )
    assert claim.reportable


def test_refusal_reason_names_what_is_missing():
    """A refusal has to say what was insufficient, not just decline."""
    weak_confidence = make_claim(confidence=0.1, max_supporting_weight=1.0)
    assert "confidence 0.100" in weak_confidence.refusal_reason()
    weak_evidence = make_claim(confidence=0.5, max_supporting_weight=0.05)
    assert "0.050" in weak_evidence.refusal_reason()


def test_thresholds_are_stated_constants():
    """The thresholds are policy. If they move, METHODOLOGY.md is wrong."""
    assert REFUSAL_CONFIDENCE_THRESHOLD == 0.25
    assert MIN_SUPPORTING_WEIGHT == 0.30
    assert PRIOR_CONFIDENCE == 0.05


def test_log_odds_round_trip_is_stable():
    from hindcast.agents.belief_reviser import from_log_odds, to_log_odds

    for p in (0.001, 0.05, 0.25, 0.5, 0.75, 0.999):
        assert abs(from_log_odds(to_log_odds(p)) - p) < 1e-9


def test_evidence_order_does_not_change_the_result():
    """Log-odds accumulation is order independent, which matters because
    publication order is partly an accident of review times."""
    from hindcast.agents.belief_reviser import EVIDENCE_STRENGTH, from_log_odds

    weights = [0.2, 1.4, 0.05, 2.0, 0.7]
    forward = PRIOR_LOG_ODDS + sum(w * EVIDENCE_STRENGTH for w in weights)
    backward = PRIOR_LOG_ODDS + sum(w * EVIDENCE_STRENGTH for w in reversed(weights))
    assert abs(from_log_odds(forward) - from_log_odds(backward)) < 1e-12


def test_contradiction_moves_a_claim_down_without_zeroing_it():
    from hindcast.agents.belief_reviser import EVIDENCE_STRENGTH, from_log_odds, to_log_odds

    strong = to_log_odds(0.9)
    after = from_log_odds(strong - 0.35 * EVIDENCE_STRENGTH)
    assert 0.7 < after < 0.9
