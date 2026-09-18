"""Correlated evidence stays bounded, on both sides of the ledger.

The system reads two kinds of evidence that arrive in large correlated batches:
publications about a gene, and fitness screens that tested it. Neither is a set
of independent experiments. Treating them as independent broke the belief map
twice, in opposite directions, and both corrections are asserted here.
"""

from __future__ import annotations

import math

from hindcast.agents.belief_reviser import (
    ESSENTIALITY_CEILING,
    EVIDENCE_STRENGTH,
    LITERATURE_SCALE,
    PRIOR_LOG_ODDS,
    from_log_odds,
)


def _literature_total(n: int) -> float:
    """Sum of the per-publication increments the reviser applies."""
    return sum(LITERATURE_SCALE * (math.log1p(k) - math.log(k)) for k in range(1, n + 1))


def test_literature_total_is_logarithmic() -> None:
    for n in (1, 5, 20, 200):
        assert _literature_total(n) == LITERATURE_SCALE * math.log1p(n)


def test_literature_increments_decrease() -> None:
    increments = [
        LITERATURE_SCALE * (math.log1p(k) - math.log(k)) for k in range(1, 12)
    ]
    assert increments == sorted(increments, reverse=True)


def test_linear_literature_would_saturate() -> None:
    """Why the correction was needed.

    BCL11A carries 216 literature evidence items in the primary slice. One
    independent log-odds update each drove its confidence to 1.000, and every
    well studied gene with it, which flattened the ranking the forecast depends
    on.
    """
    linear = PRIOR_LOG_ODDS + 216 * 0.815 * EVIDENCE_STRENGTH
    assert from_log_odds(linear) > 0.999
    logarithmic = PRIOR_LOG_ODDS + _literature_total(216)
    assert from_log_odds(logarithmic) < 0.999


def _essentiality_total(n: int, fraction: float) -> float:
    """Sum of the per-screen increments, as the reviser normalises them."""
    norm = math.log1p(n)
    total = ESSENTIALITY_CEILING * fraction
    return sum((math.log1p(k) - math.log(k)) / norm * total for k in range(1, n + 1))


def test_essentiality_total_is_capped_by_the_ceiling() -> None:
    """400 screens of one pan-essential gene subtract no more than one screen's
    worth of ceiling."""
    for n in (1, 10, 400, 26171):
        assert math.isclose(_essentiality_total(n, 1.0), ESSENTIALITY_CEILING)


def test_essentiality_scales_with_the_hit_fraction() -> None:
    assert math.isclose(_essentiality_total(50, 0.5), ESSENTIALITY_CEILING * 0.5)
    assert math.isclose(_essentiality_total(50, 0.7), ESSENTIALITY_CEILING * 0.7)


def test_unbounded_essentiality_would_annihilate_the_claim() -> None:
    """Why this correction was needed.

    CHD4, RBBP4, CTCF, ATF4 and PRMT5 all sat at a confidence of exactly 0.000
    with around 400 evidence items each, because every fitness screen applied
    its own negative update. Three of those genes are in the answer key.
    """
    unbounded = PRIOR_LOG_ODDS - 393 * 0.1 * EVIDENCE_STRENGTH
    assert from_log_odds(unbounded) < 1e-12
    bounded = PRIOR_LOG_ODDS - _essentiality_total(393, 1.0)
    assert from_log_odds(bounded) > 0.01
