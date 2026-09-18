"""The committed snapshot: what ships in the repository, and what must not.

Hard rule 5 says the demo never depends on a live third-party API, so the
normalized graph rows are committed as gzipped JSON Lines and the offline build
reads them. Hard rule 6 and the redistribution rule say what may be committed:
identifiers, structured metadata, numeric measurements and extracted facts, and
never full-text articles or abstracts whose license does not permit
redistribution.

`FORBIDDEN_FIELDS` is the enforcement point. Any field whose name suggests
article text fails the build, and `tests/test_redistribution.py` scans the
committed files for them. Titles are kept: a title is bibliographic metadata,
it is what makes a record identifiable to a reader, and it is distributed by
every bibliographic database and citation manager. Bodies and abstracts are not
kept, and where the pipeline needs text it fetches it to a gitignored cache by
PMID.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from pydantic import BaseModel, ConfigDict, Field

from hindcast.models import Edge, Exclusion, Node

#: Field names that would mean article text is being committed. A snapshot
#: containing any of these is a build failure, not a warning.
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "abstract",
        "abstracttext",
        "abstract_text",
        "fulltext",
        "full_text",
        "body",
        "bodytext",
        "body_text",
        "text",
        "content",
        "articletext",
        "article_text",
        "paragraph",
        "paragraphs",
        "sections",
        "textmininsentences",
        "textminingsentences",
        "sentences",
        "snippet",
        "excerpt",
        "pdf",
        "supplementary_text",
    }
)

#: Longest string any snapshot field may hold. A field longer than this is
#: almost certainly prose that was not meant to ship. Titles and the stated
#: rationale strings are comfortably inside it; two fields that legitimately
#: run long are listed as exceptions.
MAX_FIELD_LENGTH = 600
LONG_FIELD_EXCEPTIONS: frozenset[str] = frozenset(
    {
        # ORCS states its significance rule as a sentence, and the rule is a
        # fact about how the screen was analyzed that the weighting depends on.
        "significance_rule",
        # The screen's own notes, which name the readout. Truncated on ingest.
        "notes",
        "rationale",
        "modality_rationale",
        "note",
        "detail",
        "statement",
        "caveat",
    }
)

SNAPSHOT_FILES = ("nodes.jsonl.gz", "edges.jsonl.gz", "exclusions.jsonl.gz")


class RedistributionViolation(RuntimeError):
    """A field that may not be committed was found in the snapshot."""


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created_at: str
    hindcast_version: str
    files: dict[str, dict[str, Any]] = Field(default_factory=dict)
    counts: dict[str, int] = Field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_payload(payload: Any, path: str = "") -> list[str]:
    """Find forbidden fields and over-long strings. Returns violation messages."""
    out: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).strip().lower().replace("-", "_") in FORBIDDEN_FIELDS:
                out.append(f"{here}: field name is forbidden in a committed snapshot")
            if (
                isinstance(value, str)
                and len(value) > MAX_FIELD_LENGTH
                and str(key).lower() not in LONG_FIELD_EXCEPTIONS
            ):
                out.append(
                    f"{here}: string of {len(value)} characters exceeds the "
                    f"{MAX_FIELD_LENGTH} limit and may be article text"
                )
            out.extend(scan_payload(value, here))
    elif isinstance(payload, list):
        for i, value in enumerate(payload[:50]):
            out.extend(scan_payload(value, f"{path}[{i}]"))
    return out


def write_jsonl_gz(path: Path, rows: Iterable[BaseModel]) -> int:
    """Write rows, scanning each for redistribution violations first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    violations: list[str] = []
    # GzipFile with mtime=0 rather than gzip.open, because gzip.open cannot set
    # the header timestamp. Without a fixed timestamp the same rows produce
    # different bytes on every run, the manifest hash changes, and hard rule 4's
    # deterministic replay is not checkable.
    # The gzip header carries both a timestamp and the source filename, and
    # either one changing makes the same rows produce different bytes. So the
    # file object is opened here and the header name is blanked, leaving the
    # compressed content as the only thing the hash depends on.
    handle = path.open("wb")
    raw = gzip.GzipFile(filename="", fileobj=handle, mode="wb", compresslevel=9, mtime=0)
    with handle, io.TextIOWrapper(raw, encoding="utf-8") as fh:
        for row in rows:
            payload = row.model_dump(mode="json")
            found = scan_payload(payload)
            if found:
                violations.extend(f"{path.name}: {v}" for v in found[:3])
                if len(violations) > 20:
                    break
                continue
            fh.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            n += 1
    if violations:
        raise RedistributionViolation(
            "snapshot build refused, "
            + f"{len(violations)} violation(s):\n  " + "\n  ".join(violations[:20])
        )
    return n


def read_jsonl_gz(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_snapshot(
    directory: Path,
    *,
    nodes: list[Node],
    edges: list[Edge],
    exclusions: list[Exclusion],
    sources: dict[str, dict[str, Any]] | None = None,
    notes: list[str] | None = None,
) -> SnapshotManifest:
    from hindcast import __version__

    directory.mkdir(parents=True, exist_ok=True)
    counts = {
        "nodes": write_jsonl_gz(directory / "nodes.jsonl.gz", nodes),
        "edges": write_jsonl_gz(directory / "edges.jsonl.gz", edges),
        "exclusions": write_jsonl_gz(directory / "exclusions.jsonl.gz", exclusions),
    }
    manifest = SnapshotManifest(
        created_at=datetime.now(UTC).isoformat(),
        hindcast_version=__version__,
        counts=counts,
        sources=sources or {},
        notes=notes or [],
    )
    for name in SNAPSHOT_FILES:
        path = directory / name
        manifest.files[name] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    (directory / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2, sort_keys=True)
    )
    return manifest


def read_snapshot(directory: Path) -> tuple[list[Node], list[Edge], list[Exclusion]]:
    nodes = [Node.model_validate(r) for r in read_jsonl_gz(directory / "nodes.jsonl.gz")]
    edges = [Edge.model_validate(r) for r in read_jsonl_gz(directory / "edges.jsonl.gz")]
    exclusions = [
        Exclusion.model_validate(r) for r in read_jsonl_gz(directory / "exclusions.jsonl.gz")
    ]
    return nodes, edges, exclusions


def verify_snapshot(directory: Path) -> list[str]:
    """Check the committed files against the manifest hashes. Returns problems."""
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return [f"no manifest at {manifest_path}"]
    manifest = SnapshotManifest.model_validate_json(manifest_path.read_text())
    problems: list[str] = []
    for name, meta in manifest.files.items():
        path = directory / name
        if not path.exists():
            problems.append(f"{name}: listed in the manifest but missing")
            continue
        actual = sha256_file(path)
        if actual != meta["sha256"]:
            problems.append(
                f"{name}: sha256 {actual[:16]} does not match manifest {meta['sha256'][:16]}"
            )
    return problems
