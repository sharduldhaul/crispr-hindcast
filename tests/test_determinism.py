"""Hard rule 4: deterministic replay.

A clone of this repository must reproduce the exact scorecard offline. These
tests check the properties that has to rest on: slicing the same store twice
gives the same rows, and replaying the same evidence twice gives byte-identical
output.
"""

from __future__ import annotations

import json
from datetime import date

from hindcast.store import Store

CUTOFF = date(2018, 1, 1)


def test_slicing_twice_gives_identical_rows(toy_store: Store):
    with toy_store.open_slice(CUTOFF) as a:
        first = sorted((n.id, n.prov.ingest_hash) for n in a.nodes())
        first_edges = sorted(e.id for e in a.edges())
        counts_a = (a.counts.nodes, a.counts.edges, a.counts.dropped_dangling_edges)
    with toy_store.open_slice(CUTOFF) as b:
        second = sorted((n.id, n.prov.ingest_hash) for n in b.nodes())
        second_edges = sorted(e.id for e in b.edges())
        counts_b = (b.counts.nodes, b.counts.edges, b.counts.dropped_dangling_edges)
    assert first == second
    assert first_edges == second_edges
    assert counts_a == counts_b


def test_no_randomness_reaches_the_seed(monkeypatch):
    """Nothing in this system samples. The seed exists so that if something
    later does, replay stays exact."""
    from hindcast.agents.base import SEED

    assert SEED == 20171231


def test_ingest_hash_is_stable_across_processes():
    """The hash is content-addressed, so it cannot depend on dict ordering or
    on the machine."""
    from hindcast.models import content_hash

    a = content_hash({"b": 2, "a": [1, {"z": 9, "y": 8}]})
    b = content_hash({"a": [1, {"y": 8, "z": 9}], "b": 2})
    assert a == b
    assert a == content_hash({"b": 2, "a": [1, {"z": 9, "y": 8}]})


def test_belief_revision_replays_identically(toy_store: Store):
    """Two runs over the same slice produce the same revision sequence."""
    from hindcast.agents.axioms import AxiomExtractor
    from hindcast.agents.belief_reviser import BeliefReviser

    runs = []
    for i in range(2):
        with toy_store.open_slice(CUTOFF) as sl:
            axioms = AxiomExtractor(f"det-{i}").run(sl)
            belief = BeliefReviser(f"det-{i}").run(sl, axioms)
            runs.append(
                json.dumps(
                    {
                        cid: [r.model_dump() for r in claim.revisions]
                        for cid, claim in sorted(belief.claims.items())
                    },
                    sort_keys=True,
                    default=str,
                )
            )
    assert runs[0] == runs[1]


def test_axiom_extraction_replays_identically(toy_store: Store):
    from hindcast.agents.axioms import AxiomExtractor

    out = []
    for i in range(2):
        with toy_store.open_slice(CUTOFF) as sl:
            result = AxiomExtractor(f"det-ax-{i}").run(sl)
            out.append(
                json.dumps(
                    [a.model_dump() for a in result.axioms], sort_keys=True, default=str
                )
            )
    assert out[0] == out[1]


def test_the_audit_log_cannot_be_rewritten(toy_store: Store):
    """The append-only property is enforced by the database, not by habit."""
    import sqlite3

    import pytest

    toy_store.log_revision(
        run_id="r",
        claim_id="c",
        evidence_id="e",
        evidence_date="2013-03-22",
        prior_confidence=0.05,
        posterior_confidence=0.1,
        prior_log_odds=-2.9,
        posterior_log_odds=-2.2,
        weight_applied=0.8,
        direction="supports",
        rationale="test",
    )
    with pytest.raises(sqlite3.DatabaseError):
        toy_store.conn.execute("UPDATE belief_revision SET posterior_confidence = 0.99")
    with pytest.raises(sqlite3.DatabaseError):
        toy_store.conn.execute("DELETE FROM belief_revision")
    rows = toy_store.revisions(claim_id="c")
    assert len(rows) == 1
    assert rows[0]["posterior_confidence"] == 0.1
