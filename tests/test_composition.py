"""The composition route: ACTS_THROUGH and what may travel along it.

This is the only route that can reach a gene the pre-cutoff literature does not
write about, so the restrictions on it are the ones that decide whether the
route is a reasoning step or a way of manufacturing claims.
"""

from __future__ import annotations

from datetime import date

from hindcast.ingest.ontology import GeneRecord
from hindcast.ingest.sources import COMPLEX_GROUP_SUFFIX, complex_membership_edges
from hindcast.models import EdgeType


class _Ontology:
    """Just enough of OntologyIndex for the edge derivation."""

    def __init__(self, genes: list[GeneRecord]) -> None:
        self.genes = {g.hgnc_id: g for g in genes}
        self.exclusions: list = []


def _gene(hgnc: str, symbol: str, family: str, approved: date) -> GeneRecord:
    return GeneRecord(
        hgnc_id=f"HGNC:{hgnc}",
        symbol=symbol,
        name=symbol,
        aliases=(),
        prev_symbols=(),
        gene_family=family,
        locus_type="gene with protein product",
        location="1p1",
        ensembl_gene_id=None,
        entrez_id=None,
        approved=approved,
    )


NURD = "NuRD complex subunits"
ZINC = "Zinc fingers C2H2-type"


def test_complex_members_are_linked_both_ways() -> None:
    idx = _Ontology(
        [
            _gene("1919", "CHD4", f"PHD finger proteins|{NURD}", date(1995, 1, 1)),
            _gene("6917", "MBD2", f"Methyl-CpG binding|{NURD}", date(1998, 1, 1)),
        ]
    )
    result = complex_membership_edges(idx)
    assert len(result.edges) == 2
    assert {e.type for e in result.edges} == {EdgeType.ACTS_THROUGH}
    pairs = {(e.attrs["src_symbol"], e.attrs["dst_symbol"]) for e in result.edges}
    assert pairs == {("CHD4", "MBD2"), ("MBD2", "CHD4")}
    for edge in result.edges:
        assert edge.attrs["gene_group"] == NURD
        assert edge.attrs["basis"] == "hgnc_complex_group"


def test_domain_families_do_not_create_edges() -> None:
    """Sharing a structural domain is not sharing a mechanism.

    ZNF410 and BCL11A are both C2H2 zinc fingers. HIC2 and ZBTB7A both carry a
    BTB domain. Neither pairing is evidence that one acts through the other, and
    those groups run to hundreds of genes.
    """
    idx = _Ontology(
        [
            _gene("13221", "BCL11A", f"{ZINC}|BAF complex subunits", date(2001, 1, 1)),
            _gene("23504", "ZNF410", ZINC, date(2004, 1, 1)),
            _gene("4828", "HIC2", f"{ZINC}|BTB domain containing", date(2003, 1, 1)),
        ]
    )
    assert complex_membership_edges(idx).edges == []


def test_edge_is_dated_by_the_later_endpoint() -> None:
    """An edge must not be visible in a slice before both its genes exist."""
    idx = _Ontology(
        [
            _gene("1919", "CHD4", NURD, date(1995, 1, 1)),
            _gene("6917", "MBD2", NURD, date(2009, 6, 1)),
        ]
    )
    for edge in complex_membership_edges(idx).edges:
        assert edge.prov.effective_date == date(2009, 6, 1)


def test_group_suffix_is_the_only_admitted_kind() -> None:
    assert COMPLEX_GROUP_SUFFIX == "complex subunits"
    assert NURD.lower().endswith(COMPLEX_GROUP_SUFFIX)
    assert not ZINC.lower().endswith(COMPLEX_GROUP_SUFFIX)


def test_every_edge_carries_a_license_and_provenance() -> None:
    idx = _Ontology(
        [
            _gene("1919", "CHD4", NURD, date(1995, 1, 1)),
            _gene("6917", "MBD2", NURD, date(1998, 1, 1)),
        ]
    )
    for edge in complex_membership_edges(idx).edges:
        assert edge.prov.license
        assert edge.prov.source_id
        assert edge.prov.ingest_hash
