"""The held-out prediction evaluation.

What is being checked here is that the holdout actually hides the rows, and that
the masking does not open a route past the slice.
"""

from __future__ import annotations

from datetime import date

from hindcast.heldout import HeldOutEvaluator, _MaskedSlice
from hindcast.models import NodeType
from hindcast.store import Store

CUTOFF = date(2018, 1, 1)


def test_masking_hides_the_named_rows(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as sl:
        assert sl.node("meas:pre") is not None
        masked = _MaskedSlice(sl, frozenset({"meas:pre"}))
        assert masked.node("meas:pre") is None
        assert "meas:pre" not in {n.id for n in masked.nodes(NodeType.MEASUREMENT)}


def test_masking_also_hides_edges_touching_a_hidden_row(toy_store: Store):
    """A visible edge to a hidden node would leak the hidden node's existence,
    which is the same mistake the slice materializer avoids."""
    with toy_store.open_slice(CUTOFF) as sl:
        masked = _MaskedSlice(sl, frozenset({"meas:pre"}))
        for edge in masked.edges():
            assert edge.src != "meas:pre"
            assert edge.dst != "meas:pre"


def test_masking_does_not_reveal_anything_post_cutoff(toy_store: Store):
    """Masking is a question about the reasoning, not a new storage path."""
    with toy_store.open_slice(CUTOFF) as sl:
        masked = _MaskedSlice(sl, frozenset({"meas:pre"}))
        assert masked.node("meas:post") is None
        masked.assert_no_leak()
        assert masked.cutoff == CUTOFF.isoformat()


def test_holdout_reports_only_genes_it_could_rank(toy_store: Store):
    report = HeldOutEvaluator("test-ho").run(toy_store, CUTOFF, max_genes=4, min_measurements=1)
    assert report.cutoff == CUTOFF.isoformat()
    # Recovery is only counted over genes that were reportable to begin with.
    for holdout in report.holdouts:
        if not holdout.reportable_with:
            assert holdout not in [h for h in report.holdouts if h.reportable_with]
    assert report.genes_tested == sum(1 for h in report.holdouts if h.reportable_with)


def test_holdout_is_deterministic(toy_store: Store):
    a = HeldOutEvaluator("ho-a").run(toy_store, CUTOFF, max_genes=4, min_measurements=1)
    b = HeldOutEvaluator("ho-b").run(toy_store, CUTOFF, max_genes=4, min_measurements=1)
    assert [h.gene_symbol for h in a.holdouts] == [h.gene_symbol for h in b.holdouts]
    assert [h.confidence_without_measurements for h in a.holdouts] == [
        h.confidence_without_measurements for h in b.holdouts
    ]
