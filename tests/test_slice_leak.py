"""Hard rule 2: no evidence after T, enforced at the data layer.

These tests attempt the leak by every route the slice is supposed to close, and
assert each one fails. If any of them starts passing, the benchmark's central
claim is void, so they are the first tests in the suite.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from hindcast.models import Edge, EdgeType, Node, NodeType, Provenance
from hindcast.store import SliceStore, Store

CUTOFF = date(2018, 1, 1)


def test_post_cutoff_node_is_absent_not_filtered(toy_store: Store):
    """The post-T row is not in the slice database at all."""
    with toy_store.open_slice(CUTOFF) as sl:
        assert sl.node("meas:post") is None
        # Asked for directly, by raw SQL, with no filter of our own.
        rows = sl.sql("SELECT id FROM node WHERE id = 'meas:post'")
        assert rows == []
        # And nothing anywhere in the slice is dated on or after the cutoff.
        sl.assert_no_leak()
        assert sl.max_effective_date() < CUTOFF.isoformat()


def test_slice_cannot_attach_the_full_store(toy_store: Store):
    """The route that would defeat filtering: attach the source database."""
    with toy_store.open_slice(CUTOFF) as sl:
        with pytest.raises(sqlite3.DatabaseError):
            sl.conn.execute(f"ATTACH DATABASE '{toy_store.path}' AS leak")
        with pytest.raises(sqlite3.DatabaseError):
            sl.conn.execute("ATTACH DATABASE ':memory:' AS scratch")


def test_slice_is_read_only(toy_store: Store):
    """A slice cannot be written to, so it cannot be used to smuggle rows in."""
    with toy_store.open_slice(CUTOFF) as sl:
        for statement in (
            "INSERT INTO node (id,type,label,attrs,source_id,license,time_scope,effective_date) "
            "VALUES ('x','Gene','X','{}','s','MIT','DATED','2019-01-01')",
            "DELETE FROM node",
            "UPDATE node SET label = 'tampered'",
            "DROP TABLE node",
            "CREATE TABLE sneak (id TEXT)",
        ):
            with pytest.raises(sqlite3.DatabaseError):
                sl.conn.execute(statement)


def test_dangling_edge_to_hidden_node_is_dropped(toy_store: Store):
    """A pre-T edge pointing at a post-T node would leak that node's existence."""
    with toy_store.open_slice(CUTOFF) as sl:
        assert sl.edges(type="SUPPORTS") == []
        assert sl.counts.dropped_dangling_edges == 1
        for edge in sl.edges():
            assert sl.node(edge.src) is not None
            assert sl.node(edge.dst) is not None


def test_reference_nodes_are_filtered_by_approval_date(toy_store: Store):
    """A gene symbol coined after T must not appear, or node presence leaks."""
    toy_store.add_nodes(
        [
            Node(
                id="gene:HGNC:99999",
                type=NodeType.GENE,
                label="LATERGENE",
                attrs={"hgnc_id": "HGNC:99999", "symbol": "LATERGENE"},
                prov=Provenance(
                    source_id="hgnc:99999",
                    license="CC0 1.0",
                    time_scope="REFERENCE",
                    effective_date=date(2020, 5, 5),
                ),
            )
        ]
    )
    with toy_store.open_slice(CUTOFF) as sl:
        assert sl.node("gene:HGNC:99999") is None
        assert sl.gene_by_symbol("LATERGENE") is None
        # The pre-T gene is still reachable, including by its older alias.
        assert sl.gene_by_symbol("CTIP1") is not None


def test_earlier_slice_is_a_subset_of_a_later_one(toy_store: Store):
    """Monotonicity. Evidence only ever accumulates as T moves forward."""
    with toy_store.open_slice(date(2014, 1, 1)) as early, toy_store.open_slice(
        date(2019, 1, 1)
    ) as late:
        early_ids = {n.id for n in early.nodes()}
        late_ids = {n.id for n in late.nodes()}
        assert early_ids < late_ids
        assert "meas:post" in late_ids
        assert "meas:post" not in early_ids


def test_slice_reports_its_own_cutoff(toy_store: Store):
    """A slice file is self-describing, so a committed slice can be audited."""
    with toy_store.open_slice(CUTOFF) as sl:
        manifest = sl.manifest()
        assert manifest["cutoff"] == CUTOFF.isoformat()
        assert int(manifest["nodes"]) == sl.counts.nodes
        assert int(manifest["dropped_dangling_edges"]) == 1


def test_agents_receive_a_slice_with_no_path_back(toy_store: Store):
    """A SliceStore exposes no attribute holding the full store or its path."""
    with toy_store.open_slice(CUTOFF) as sl:
        assert not hasattr(sl, "add_nodes")
        assert not hasattr(sl, "open_slice")
        assert isinstance(sl, SliceStore)
        assert toy_store.path.name != sl.path.name
