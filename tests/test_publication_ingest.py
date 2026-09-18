"""Publication ingestion records the tiers and trusts only the title.

Two regressions live here. The first is silent: `matched_tiers` was never
written onto the publication nodes at all, so every downstream consumer read an
empty list, the literature route could not distinguish an HbF record from an
erythroid one, and the forecast came out empty with every gene refused. Nothing
failed; a field was simply absent.

The second is the full-text tagging described in hindcast.textmatch.
"""

from __future__ import annotations

import json
from pathlib import Path

from hindcast.ingest.dates import DateIndex
from hindcast.ingest.sources import ingest_publications


def _raw(tmp_path: Path, records: list[dict], coverage: list[dict]) -> Path:
    root = tmp_path / "raw"
    (root / "europepmc").mkdir(parents=True)
    (root / "europepmc" / "scope_literature.json").write_text(json.dumps(records))
    (root / "europepmc" / "coverage.json").write_text(json.dumps(coverage))
    return root


COVERAGE = [
    {
        "gene": "EIF2AK1",
        "terms": ["EIF2AK1", "HCR", "hHRI", "heme-regulated inhibitor"],
    },
    {"gene": "BCL11A", "terms": ["BCL11A", "CTIP1"]},
]


def test_matched_tiers_reach_the_node(tmp_path: Path) -> None:
    records = [
        {
            "pmid": "30026227",
            "title": "Heme-regulated inhibitor kinase represses fetal hemoglobin",
            "firstPublicationDate": "2018-07-01",
            "matched_genes": ["EIF2AK1"],
            "matched_tiers": ["erythroid", "hbf"],
        }
    ]
    root = _raw(tmp_path, records, COVERAGE)
    result = ingest_publications(root, DateIndex.from_raw(root))
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node.attrs["matched_tiers"] == ["erythroid", "hbf"]
    assert node.attrs["matched_genes"] == ["EIF2AK1"]


def test_full_text_tag_is_not_trusted(tmp_path: Path) -> None:
    """The query matched on an alias in the body; the title is about a virus."""
    records = [
        {
            "pmid": "19193793",
            "title": (
                "The 30-amino-acid deletion in the Nsp2 of highly pathogenic "
                "porcine reproductive and respiratory syndrome virus"
            ),
            "firstPublicationDate": "2009-02-25",
            "matched_genes": ["EIF2AK1"],
            "matched_tiers": ["hbf"],
        }
    ]
    root = _raw(tmp_path, records, COVERAGE)
    node = ingest_publications(root, DateIndex.from_raw(root)).nodes[0]
    assert node.attrs["matched_genes"] == []
    # The retrieval tag is kept so the difference stays inspectable.
    assert node.attrs["query_matched_genes"] == ["EIF2AK1"]
    assert node.attrs["gene_match_rule"] == "title_names_gene"


def test_undated_record_is_excluded_not_dated(tmp_path: Path) -> None:
    records = [
        {
            "pmid": "1",
            "title": "BCL11A represses fetal hemoglobin",
            "matched_genes": ["BCL11A"],
            "matched_tiers": ["hbf"],
        }
    ]
    root = _raw(tmp_path, records, COVERAGE)
    result = ingest_publications(root, DateIndex.from_raw(root))
    assert result.nodes == []
    assert [x.reason for x in result.exclusions] == ["unresolvable_date"]


def test_record_with_no_pmid_is_excluded(tmp_path: Path) -> None:
    records = [
        {
            "id": "PPR123",
            "title": "BCL11A represses fetal hemoglobin",
            "firstPublicationDate": "2010-01-01",
            "matched_genes": ["BCL11A"],
            "matched_tiers": ["hbf"],
        }
    ]
    root = _raw(tmp_path, records, COVERAGE)
    result = ingest_publications(root, DateIndex.from_raw(root))
    assert result.nodes == []
    assert [x.reason for x in result.exclusions] == ["malformed_record"]
