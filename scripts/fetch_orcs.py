"""Fetch BioGRID ORCS screen metadata into data/raw/orcs/.

ORCS bulk releases ship per-screen hit tables but no screen-level index, and the
REST webservice requires a registered access key. The public screen pages carry
the metadata this project needs: PMID, cell line with Cellosaurus accession,
perturbation type, phenotype and significance rule.

Only identifiers, structured metadata and numeric fields are kept. No article
text is stored. Run once; the parsed result is snapshotted by
scripts/build_snapshot.py and the raw cache stays gitignored.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

import httpx

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "orcs"
BASE = "https://orcs.thebiogrid.org/Screen/{sid}"
UA = "crispr-hindcast/0.1 (research benchmark; contact via repository)"


def strip_tags(page: str) -> str:
    page = re.sub(r"<script.*?</script>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<style.*?</style>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def field(text: str, label: str, stops: list[str]) -> str | None:
    stop = "|".join(re.escape(s) for s in stops)
    m = re.search(rf"{re.escape(label)}\s*:\s*(.*?)(?=\s*(?:{stop})\s*:|$)", text)
    if not m:
        return None
    val = m.group(1).strip(" |")
    return val or None


# Labels that appear as "Label : value" on their own, in page order. "Type",
# "Format", "Enzyme" and "Methodology" are NOT here: they appear only inside the
# pipe-delimited library line, and a bare "Type" search would match "Cell Type".
LABELS = [
    "Screen Rationale", "Cell Type", "Cell Line", "Phenotype", "Condition",
    "Library", "Analysis Method", "Number of Hits", "Full Dataset Size",
    "Experimental Setup", "Duration", "Significance", "Notes",
    "Score Distribution", "Title", "Screen Details",
]

# The library line reads:
#   Library : <name> [ <source> ] | Type : CRISPRn | Format : Pool |
#   Enzyme : Cas9 | Methodology : Knockout
LIBRARY_KEYS = ("Type", "Format", "Enzyme", "Methodology")

# Everything from here on is site chrome, not screen content.
NOTES_CUTS = (
    "View More Screens", "Score Distribution", "CRISPR Screen Results",
    "Download Screen", "A BioGRID Project",
)


def parse_library_line(raw: str | None) -> tuple[str | None, dict]:
    """Split the library line into the library name and its pipe-delimited keys."""
    out: dict = {k.lower(): None for k in LIBRARY_KEYS}
    if not raw:
        return None, out
    parts = [p.strip() for p in raw.split("|")]
    name = parts[0].strip() or None
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, _, val = part.partition(":")
        key = key.strip()
        if key in LIBRARY_KEYS:
            out[key.lower()] = val.strip() or None
    return name, out


def parse(sid: int, page: str) -> dict:
    text = strip_tags(page)
    head = re.search(r"CRISPR Screen Dataset (.*?) (?:H\.|M\.|S\.|D\.|C\.) ", text)
    banner = head.group(1).strip() if head else None
    pmid = None
    if banner:
        pm = re.search(r"PMID(\d+)", banner)
        pmid = pm.group(1) if pm else None
    if pmid is None:
        pm = re.search(r"PMID(\d+)", text[:400])
        pmid = pm.group(1) if pm else None

    rec: dict = {"screen_id": sid, "banner": banner, "pmid": pmid}
    for label in LABELS:
        rec[label.lower().replace(" ", "_")] = field(text, label, LABELS)

    lib_name, lib_fields = parse_library_line(rec.get("library"))
    rec["library_name"] = re.sub(r"\[.*?\]", "", lib_name or "").strip(" |") or None
    rec["library_source"] = (
        m.group(1) if (m := re.search(r"\[\s*([^\]]+?)\s*\]", lib_name or "")) else None
    )
    rec.update(lib_fields)

    notes = rec.get("notes")
    if notes:
        for cut in NOTES_CUTS:
            notes = notes.split(cut)[0]
        rec["notes"] = notes.strip(" |") or None

    title = rec.get("title")
    if title:
        rec["title"] = re.sub(r"\s*Screen Details\s*:?\s*$", "", title).strip() or None
    rec.pop("screen_details", None)

    cl = rec.get("cell_line") or ""
    cvcl = re.search(r"CELLOSAURUS:(CVCL_\w+)", cl)
    rec["cellosaurus_id"] = cvcl.group(1) if cvcl else None
    bto = re.search(r"(BTO:\d+)", cl)
    rec["bto_id"] = bto.group(1) if bto else None
    rec["cell_line_name"] = re.sub(r"\[.*?\]", "", cl).strip(" |") or None
    ct = rec.get("cell_type") or ""
    rec["cell_type_name"] = re.sub(r"\[.*?\]", "", ct).strip(" |") or None
    for key in ("number_of_hits", "full_dataset_size"):
        raw = (rec.get(key) or "").replace(",", "")
        m = re.match(r"(\d+)", raw)
        rec[key + "_n"] = int(m.group(1)) if m else None
    rec.pop("score_distribution", None)
    return rec


def main(start: int, end: int, delay: float = 0.4) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": UA}, timeout=60.0, follow_redirects=True) as c:
        for sid in range(start, end + 1):
            out = RAW / f"screen_{sid}.json"
            if out.exists():
                continue
            try:
                r = c.get(BASE.format(sid=sid))
            except httpx.HTTPError as exc:
                print(f"{sid} ERROR {exc}", flush=True)
                time.sleep(3.0)
                continue
            if r.status_code != 200:
                out.write_text(json.dumps({"screen_id": sid, "http_status": r.status_code}))
                time.sleep(delay)
                continue
            rec = parse(sid, r.text)
            rec["http_status"] = 200
            out.write_text(json.dumps(rec, indent=1, sort_keys=True))
            if sid % 100 == 0:
                print(f"{sid} ok pmid={rec.get('pmid')}", flush=True)
            time.sleep(delay)


if __name__ == "__main__":
    a = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    b = int(sys.argv[2]) if len(sys.argv) > 2 else 2600
    main(a, b)
