"""Bootstrap intervals over genes."""

from __future__ import annotations

from hindcast.agents.grader import _score_ranking
from hindcast.bootstrap import LEVEL, RESAMPLES, ranking_intervals, rate_interval

RANKED = ["A", "B", "C", "D", "E", "F"]
TRUTH = {"A", "D", "Z"}
ASKED = {*RANKED, "G", "H"}


def test_the_same_inputs_give_the_same_interval_whatever_ran_before():
    first = ranking_intervals(RANKED, TRUTH, ASKED)
    rate_interval([True, False, True])
    second = ranking_intervals(RANKED, TRUTH, ASKED)

    assert first == second
    assert first[0].resamples == RESAMPLES and first[0].level == LEVEL


def test_the_interval_contains_the_point_estimate_and_stays_in_range():
    score = _score_ranking("confidence", RANKED, TRUTH, ASKED)

    p5, mrr = score.precision_at_5_interval, score.mean_reciprocal_rank_interval
    assert 0.0 <= p5.lower <= score.precision_at_5 <= p5.upper <= 1.0
    assert 0.0 <= mrr.lower <= score.mean_reciprocal_rank <= mrr.upper <= 1.0
    # Ranked, refused and ground-truth genes are all resampled: 8 asked plus Z.
    assert p5.units == mrr.units == 9


def test_few_ground_truth_genes_give_a_wide_interval():
    p5, _ = ranking_intervals(RANKED, {"A"}, ASKED)

    assert (p5.lower, p5.upper) == (0.0, 0.6)


def test_a_ranking_with_no_hit_has_a_zero_interval():
    p5, mrr = ranking_intervals(RANKED, {"Z"}, ASKED)

    assert (p5.lower, p5.upper, mrr.lower, mrr.upper) == (0.0, 0.0, 0.0, 0.0)


def test_a_rate_every_gene_agrees_on_has_no_spread():
    interval = rate_interval([True] * 6)

    assert (interval.lower, interval.upper, interval.units) == (1.0, 1.0, 6)


def test_a_mixed_rate_brackets_its_value():
    interval = rate_interval([True, False] * 5)

    assert interval.lower < 0.5 < interval.upper


def test_with_no_genes_nothing_is_resampled():
    interval = rate_interval([])

    assert (interval.lower, interval.upper, interval.units) == (0.0, 0.0, 0)
