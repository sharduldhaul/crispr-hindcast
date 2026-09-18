"""Ontology normalization, and the alias attacks the adversary runs.

If these fail, the adversary's paraphrase attacks are testing string matching
rather than the graph.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hindcast.ingest.ontology import OntologyIndex
from hindcast.scope import ALL_SCOPE_GENES, resolve_informal

HGNC = Path(__file__).resolve().parents[1] / "data" / "raw" / "hgnc" / "hgnc_complete_set.tsv"
pytestmark = pytest.mark.skipif(not HGNC.exists(), reason="HGNC release not fetched")


@pytest.fixture(scope="module")
def index() -> OntologyIndex:
    return OntologyIndex(hgnc_path=HGNC)


def test_every_scope_gene_resolves_to_exactly_one_gene(index: OntologyIndex):
    """Every name in the frozen scope list must reach one HGNC gene."""
    for symbol in ALL_SCOPE_GENES:
        gene = index.resolve_gene(symbol)
        assert gene is not None, f"{symbol} does not resolve"
        assert gene.symbol.upper() == symbol.upper(), (
            f"{symbol} resolves to {gene.symbol}, so the scope list holds a "
            f"historical name where it should hold the current symbol"
        )


def test_the_scope_list_has_no_duplicates_after_resolution(index: OntologyIndex):
    """Two names for one gene would double-count it in every ranking."""
    resolved = [index.resolve_gene(s) for s in ALL_SCOPE_GENES]
    ids = [g.hgnc_id for g in resolved if g]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"scope list resolves to duplicate genes: {duplicates}"


def test_withdrawn_symbols_resolve_to_the_current_gene(index: OntologyIndex):
    """The adversary restates queries in older symbols. This is that attack."""
    assert index.resolve_gene("EVI9").symbol == "BCL11A"
    assert index.resolve_gene("CTIP1").symbol == "BCL11A"
    assert index.resolve_gene("HRI").symbol == "EIF2AK1"
    assert index.resolve_gene("LSD1").symbol == "KDM1A"
    assert index.resolve_gene("SETD8").symbol == "KMT5A"


def test_informal_names_resolve_through_the_frozen_vocabulary():
    assert resolve_informal("gamma-globin") == ("HBG1", "HBG2")
    assert resolve_informal("Mi-2beta") == ("CHD4",)
    assert resolve_informal("HRI") == ("EIF2AK1",)
    assert resolve_informal("LRF") == ("ZBTB7A",)
    assert resolve_informal("not-a-gene") == ()


def test_an_ambiguous_alias_resolves_to_nothing(index: OntologyIndex):
    """Picking one of several genes with the same old name is the silent error
    that would put a wrong number in an output, so it is refused."""
    assert index.resolve_gene("TR2") is None
    assert "ambiguous" in index.resolution_failure("TR2")


def test_an_unknown_symbol_resolves_to_nothing(index: OntologyIndex):
    assert index.resolve_gene("NOTAREALGENE") is None
    assert "unknown symbol" in index.resolution_failure("NOTAREALGENE")


def test_stable_ids_win_over_symbols(index: OntologyIndex):
    """A numeric identifier is preferred, because symbols change and IDs do not."""
    by_entrez = index.resolve_gene("wrongsymbol", entrez="53335")
    assert by_entrez.symbol == "BCL11A"
    by_ensembl = index.resolve_gene(None, ensembl="ENSG00000119866")
    assert by_ensembl.symbol == "BCL11A"


def test_genes_without_an_approval_date_are_excluded_not_dated(index: OntologyIndex):
    _ = index.genes
    assert index.exclusions, "expected some HGNC rows to lack an approval date"
    assert all(x.reason == "unresolvable_date" for x in index.exclusions)


def test_every_gene_carries_an_approval_date(index: OntologyIndex):
    """The slice filters reference nodes on this date, so it cannot be missing."""
    assert all(g.approved is not None for g in index.genes.values())


def test_primary_cells_are_classified_from_their_name(index: OntologyIndex):
    """Primary human cells have no Cellosaurus accession, so they match by name."""
    rec = index.resolve_cell(None, "human CD34+ HSPC")
    assert rec is not None
    assert rec.system_class == "primary_human_hspc"


def test_an_unknown_cell_line_resolves_to_nothing(index: OntologyIndex):
    assert index.resolve_cell(None, "some line nobody registered") is None
