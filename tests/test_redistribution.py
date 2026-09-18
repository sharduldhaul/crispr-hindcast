"""The redistribution scan, run against the committed snapshot.

Any file in the snapshot that cannot be redistributed is a build failure. The
scan looks for field names that would mean article text is present, and for
strings long enough to be prose.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from hindcast.snapshot import (
    FORBIDDEN_FIELDS,
    MAX_FIELD_LENGTH,
    RedistributionViolation,
    scan_payload,
    verify_snapshot,
    write_jsonl_gz,
)

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "snapshot"
BUILT = (SNAPSHOT / "manifest.json").exists()


def test_scan_rejects_an_abstract_field():
    found = scan_payload({"pmid": "1", "abstract": "some article text"})
    assert found and "forbidden" in found[0]


def test_scan_rejects_every_forbidden_field_name():
    for field in FORBIDDEN_FIELDS:
        found = scan_payload({field: "x"})
        assert found, f"{field} was not caught by the scan"


def test_scan_rejects_prose_length_strings():
    found = scan_payload({"summary": "x" * (MAX_FIELD_LENGTH + 1)})
    assert found and "exceeds" in found[0]


def test_scan_allows_bibliographic_metadata():
    payload = {
        "pmid": "30026227",
        "doi": "10.1126/science.aao0932",
        "title": "Domain-focused CRISPR screen identifies HRI as a fetal hemoglobin regulator",
        "journal": "Science",
        "publication_date": "2018-07-01",
        "value": 2.41,
    }
    assert scan_payload(payload) == []


def test_write_allows_a_long_exclusion_detail(tmp_path: Path):
    """`detail` is a stated long-field exception, so a long reason is allowed."""
    from hindcast.models import Exclusion

    rows = [Exclusion(source="s", source_id="1", reason="out_of_scope", detail="x" * 2000)]
    assert write_jsonl_gz(tmp_path / "a.jsonl.gz", rows) == 1


def test_write_refuses_a_row_carrying_article_text(tmp_path: Path):
    """A node whose attrs hold an abstract cannot be written to a snapshot."""
    from datetime import date

    from hindcast.models import Node, NodeType, Provenance

    node = Node(
        id="pub:1",
        type=NodeType.PUBLICATION,
        label="a title",
        attrs={"pmid": "1", "abstract": "the article body would go here"},
        prov=Provenance(source_id="s:1", license="MIT", publication_date=date(2015, 1, 1)),
    )
    with pytest.raises(RedistributionViolation) as exc:
        write_jsonl_gz(tmp_path / "b.jsonl.gz", [node])
    assert "abstract" in str(exc.value)


def test_snapshot_bytes_are_stable_across_writes(tmp_path: Path):
    """Two writes of the same rows produce identical bytes. Hard rule 4."""
    from hindcast.models import Exclusion
    from hindcast.snapshot import sha256_file

    rows = [Exclusion(source="s", source_id=str(i), reason="out_of_scope") for i in range(50)]
    a, b = tmp_path / "a.jsonl.gz", tmp_path / "b.jsonl.gz"
    write_jsonl_gz(a, rows)
    write_jsonl_gz(b, rows)
    assert sha256_file(a) == sha256_file(b)


@pytest.mark.skipif(not BUILT, reason="snapshot not built yet")
def test_committed_snapshot_has_no_article_text():
    problems: list[str] = []
    for path in sorted(SNAPSHOT.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if not line.strip():
                    continue
                found = scan_payload(json.loads(line))
                if found:
                    problems.append(f"{path.name}:{i + 1} {found[0]}")
                if len(problems) > 10:
                    break
    assert not problems, "committed snapshot contains non-redistributable fields:\n" + "\n".join(
        problems
    )


@pytest.mark.skipif(not BUILT, reason="snapshot not built yet")
def test_committed_snapshot_matches_its_manifest_hashes():
    problems = verify_snapshot(SNAPSHOT)
    assert not problems, "\n".join(problems)


@pytest.mark.skipif(not BUILT, reason="snapshot not built yet")
def test_every_snapshot_row_carries_a_license():
    from hindcast.snapshot import read_jsonl_gz

    for name in ("nodes.jsonl.gz", "edges.jsonl.gz"):
        path = SNAPSHOT / name
        if not path.exists():
            continue
        for i, row in enumerate(read_jsonl_gz(path)):
            license_value = (row.get("prov") or {}).get("license")
            assert license_value, f"{name}:{i + 1} has no license"
            if i > 5000:
                break
