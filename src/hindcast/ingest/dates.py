"""Publication date resolution. One rule, one place.

Hard rule 2 turns on `publication_date`, so every dated row in the graph gets
its date from here and nowhere else. The rule is stated in SCHEMA.md: prefer
Europe PMC's `firstPublicationDate` over the journal issue date, because the
field's knowledge of a result begins when the result becomes readable.

A record whose date cannot be resolved is excluded and counted. It is never
given a guessed date, and it is never defaulted to the start or end of a year,
because a January default would pull a December result across a year-end
cutoff and that is exactly the error this project cannot afford.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ResolvedDate:
    resolved: date
    online: date | None
    issue: date | None
    rule: str


def _parse(raw: object) -> date | None:
    if not raw:
        return None
    text = str(raw).strip()
    for length, fmt in ((10, "%Y-%m-%d"),):
        if len(text) >= length:
            try:
                return date.fromisoformat(text[:10])
            except ValueError:
                pass
    return None


class DateIndex:
    """PMID to resolved dates, built from the Europe PMC payloads."""

    def __init__(self) -> None:
        self._by_pmid: dict[str, ResolvedDate] = {}
        self._meta: dict[str, dict] = {}

    @classmethod
    def from_raw(cls, raw_dir: Path) -> DateIndex:
        idx = cls()
        for name in ("europepmc/scope_literature.json", "europepmc/orcs_publications.json"):
            path = raw_dir / name
            if not path.exists():
                continue
            for rec in json.loads(path.read_text()):
                idx.add(rec)
        return idx

    def add(self, rec: dict) -> None:
        pmid = (rec.get("pmid") or "").strip()
        if not pmid:
            return
        online = _parse(rec.get("firstPublicationDate"))
        issue = _parse(rec.get("print_publication_date"))
        resolved, rule = None, ""
        if online:
            resolved, rule = online, "europepmc.firstPublicationDate"
        elif issue:
            resolved, rule = issue, "europepmc.printPublicationDate"
        if resolved is None:
            return
        self._by_pmid[pmid] = ResolvedDate(
            resolved=resolved, online=online, issue=issue, rule=rule
        )
        self._meta[pmid] = rec

    def get(self, pmid: str | None) -> ResolvedDate | None:
        if not pmid:
            return None
        return self._by_pmid.get(str(pmid).strip())

    def meta(self, pmid: str | None) -> dict:
        return self._meta.get(str(pmid).strip(), {}) if pmid else {}

    def __len__(self) -> int:
        return len(self._by_pmid)

    def pmids(self) -> set[str]:
        return set(self._by_pmid)
