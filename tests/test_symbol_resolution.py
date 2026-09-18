"""Symbol resolution precedence.

This is a regression test for a bug that silently corrupted the whole forecast.
HGNC lists "hBG1" among the aliases of ACSBG1, an acyl-CoA synthetase. A lookup
of "HBG1" therefore matched two genes: HBG1, where it is the approved symbol,
and ACSBG1, where it is an alias. The resolver picked between them with
`ORDER BY id LIMIT 1`, which compares "gene:HGNC:29567" against "gene:HGNC:4831"
as strings, so ACSBG1 won. Every publication naming gamma globin was credited to
it, and it came out top of the forecast with 509 supporting publications and a
confidence of 0.955.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from hindcast.models import Node, NodeType, Provenance, TimeScope
from hindcast.store import Store


def _gene(hgnc: str, symbol: str, aliases: list[str]) -> Node:
    return Node(
        id=f"gene:HGNC:{hgnc}",
        type=NodeType.GENE,
        label=symbol,
        attrs={"hgnc_id": f"HGNC:{hgnc}", "symbol": symbol, "aliases": aliases},
        prov=Provenance(
            source_id=f"hgnc:{hgnc}",
            license="CC0 1.0",
            time_scope=TimeScope.REFERENCE,
            effective_date=date(2001, 1, 1),
        ),
    )


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "genes.db")
    store.add_nodes(
        [
            # The real collision, with the real HGNC identifiers, so the
            # string-ordering trap is reproduced exactly.
            _gene("4831", "HBG1", ["HBGA", "HBGR"]),
            _gene("29567", "ACSBG1", ["BGM", "BG1", "hBG1", "hsBG"]),
            # A genuinely ambiguous alias: LRF belongs to neither as a symbol.
            _gene("18078", "ZBTB7A", ["LRF", "TIP21", "pokemon"]),
            _gene("25858", "CREBRF", ["LRF", "C5orf41"]),
            _gene("29079", "KDM1A", ["LSD1", "AOF2"]),
        ]
    )
    return store


def test_approved_symbol_beats_another_genes_alias(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.gene_by_symbol("HBG1").label == "HBG1"
    assert store.gene_by_symbol("hbg1").label == "HBG1"


def test_alias_still_resolves_when_unambiguous(tmp_path: Path) -> None:
    """The adversary's older-symbol attacks depend on this still working."""
    store = _store(tmp_path)
    assert store.gene_by_symbol("LSD1").label == "KDM1A"
    assert store.gene_by_symbol("BGM").label == "ACSBG1"


def test_ambiguous_alias_resolves_to_nothing(tmp_path: Path) -> None:
    """Refuse rather than guess, the same policy the curator applies."""
    store = _store(tmp_path)
    assert store.gene_by_symbol("LRF") is None


def test_unknown_symbol_resolves_to_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.gene_by_symbol("NOT_A_GENE") is None


def test_precedence_holds_inside_a_slice(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sliced = store.open_slice(date(2017, 12, 31))
    assert sliced.gene_by_symbol("HBG1").label == "HBG1"
    assert sliced.gene_by_symbol("LRF") is None
