"""Bootstrap intervals over genes, for metrics computed on a handful of them.

Contract. In: a finished ranking with its ground truth, or one flag per claim.
Out: a percentile `Interval` for precision at 5, the reciprocal rank of the
first hit, or a rate. No model call and no new data: the genes already scored
are resampled with replacement.

What this module must never do:

*   Draw from anything but `random.Random(SEED)`. Each interval starts its own
    generator from the fixed seed, so an interval depends only on its inputs
    and replays exactly, whatever was computed before it.
*   Stand in for more data. An interval over 3 ground-truth genes is wide
    because 3 genes say little, and it is reported as wide.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

from hindcast.agents.base import SEED

#: Resamples per interval. See METHODOLOGY.md.
RESAMPLES = 2000

#: Coverage of the reported interval.
LEVEL = 0.95


class Interval(BaseModel):
    """A percentile bootstrap interval. With 0 units nothing was resampled."""

    model_config = ConfigDict(extra="forbid")

    lower: float
    upper: float
    level: float = LEVEL
    resamples: int = RESAMPLES
    seed: int = SEED
    #: Genes resampled.
    units: int


def _interval(units: int, statistic: Callable[[list[int]], float]) -> Interval:
    """Percentile interval of `statistic` over resampled unit indices."""
    if units == 0:
        return Interval(lower=0.0, upper=0.0, units=0)
    rng = random.Random(SEED)
    values = sorted(
        statistic([rng.randrange(units) for _ in range(units)]) for _ in range(RESAMPLES)
    )
    # Nearest rank, so each bound is a value some resample produced.
    tail = (1 - LEVEL) / 2
    lower = values[int(tail * RESAMPLES)]
    upper = values[int((1 - tail) * RESAMPLES) - 1]
    return Interval(lower=round(lower, 6), upper=round(upper, 6), units=units)


def ranking_intervals(
    ranked: Sequence[str], truth: set[str], asked: set[str]
) -> tuple[Interval, Interval]:
    """Intervals for precision at 5 and for the reciprocal rank of the first hit.

    The units are the genes the question covered: those ranked, those refused
    and those in the ground truth. A resample keeps the drawn genes in their
    ranked order, a gene drawn twice taking two adjacent places, and is scored
    as the ranking was.
    """
    units = sorted(asked | set(ranked) | truth)

    def resampled(draws: list[int]) -> list[str]:
        counts = Counter(units[i] for i in draws)
        return [gene for gene in ranked for _ in range(counts[gene])]

    def precision_at_5(draws: list[int]) -> float:
        return sum(gene in truth for gene in resampled(draws)[:5]) / 5

    def reciprocal_rank(draws: list[int]) -> float:
        first = next((i + 1 for i, g in enumerate(resampled(draws)) if g in truth), None)
        return 1 / first if first else 0.0

    return _interval(len(units), precision_at_5), _interval(len(units), reciprocal_rank)


def rate_interval(flags: Sequence[bool]) -> Interval:
    """Interval for the share of true flags, one flag per gene."""
    return _interval(len(flags), lambda draws: sum(flags[i] for i in draws) / len(flags))
