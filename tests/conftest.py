from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from hindcast.models import Edge, EdgeType, Node, NodeType, Provenance, TimeScope
from hindcast.store import Store


def dated_prov(source_id: str, when: date, **kw) -> Provenance:
    return Provenance(
        source_id=source_id,
        license="MIT License",
        time_scope=TimeScope.DATED,
        publication_date=when,
        **kw,
    )


@pytest.fixture(autouse=True)
def _trajectories_to_tmp(tmp_path: Path, monkeypatch) -> None:
    """Keep test runs out of the committed trajectories directory.

    `trajectories/` holds the logs for the real evaluation runs and is committed.
    A test that writes there would put junk beside the evidence.
    """
    import hindcast.agents.base as base

    monkeypatch.setattr(base, "TRAJECTORY_DIR", tmp_path / "trajectories")


@pytest.fixture
def toy_store(tmp_path: Path) -> Store:
    """A graph with one pre-2018 and one post-2018 measurement.

    The post-2018 row stands in for the EIF2AK1 result, which the primary
    evaluation must not be able to see.
    """
    store = Store(tmp_path / "toy.db")
    nodes = [
        Node(
            id="gene:HGNC:13221",
            type=NodeType.GENE,
            label="BCL11A",
            attrs={"hgnc_id": "HGNC:13221", "symbol": "BCL11A", "aliases": ["CTIP1", "EVI9"]},
            prov=Provenance(
                source_id="hgnc:13221",
                license="CC0 1.0",
                time_scope=TimeScope.REFERENCE,
                effective_date=date(2001, 6, 1),
            ),
        ),
        Node(
            id="gene:HGNC:3005",
            type=NodeType.GENE,
            label="EIF2AK1",
            attrs={"hgnc_id": "HGNC:3005", "symbol": "EIF2AK1", "aliases": ["HRI", "HHRI"]},
            prov=Provenance(
                source_id="hgnc:3005",
                license="CC0 1.0",
                time_scope=TimeScope.REFERENCE,
                effective_date=date(2001, 6, 1),
            ),
        ),
        Node(
            id="pheno:hbf_protein",
            type=NodeType.PHENOTYPE,
            label="HbF protein level",
            attrs={"family": "HBF", "directness": "direct_protein"},
            prov=Provenance(
                source_id="vocab:hbf_protein",
                license="MIT License",
                time_scope=TimeScope.VOCABULARY,
            ),
        ),
        Node(
            id="pub:23522779",
            type=NodeType.PUBLICATION,
            label="BCL11A enhancer dissection",
            attrs={"pmid": "23522779"},
            prov=dated_prov("europepmc:23522779", date(2013, 3, 22), pmid="23522779"),
        ),
        Node(
            id="meas:pre",
            type=NodeType.MEASUREMENT,
            label="BCL11A knockout raises HbF",
            attrs={
                "value": 2.4,
                "gene_id": "gene:HGNC:13221",
                "phenotype_id": "pheno:hbf_protein",
                "assay": "hbf_protein_pct",
            },
            prov=dated_prov("test:pre", date(2013, 3, 22), pmid="23522779"),
        ),
        Node(
            id="meas:post",
            type=NodeType.MEASUREMENT,
            label="EIF2AK1 loss raises HbF",
            attrs={
                "value": 3.1,
                "gene_id": "gene:HGNC:3005",
                "phenotype_id": "pheno:hbf_protein",
                "assay": "hbf_protein_pct",
            },
            prov=dated_prov("test:post", date(2018, 6, 1), pmid="29735697"),
        ),
    ]
    edges = [
        Edge(
            id="edge:pre",
            type=EdgeType.REPORTS,
            src="pub:23522779",
            dst="meas:pre",
            prov=dated_prov("test:edge_pre", date(2013, 3, 22)),
        ),
        # An edge dated before the cutoff whose target is dated after it. The
        # materializer must drop this, or the slice would leak the existence of
        # the hidden node.
        Edge(
            id="edge:dangling",
            type=EdgeType.SUPPORTS,
            src="meas:pre",
            dst="meas:post",
            prov=dated_prov("test:edge_dangle", date(2013, 4, 1)),
        ),
    ]
    store.add_nodes(nodes)
    store.add_edges(edges)
    yield store
    store.close()
