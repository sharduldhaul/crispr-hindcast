"""Fetch Cellosaurus records for the cell lines appearing in the corpus.

The cell system is the largest term in the weighting function, so it has to be
resolved to a stable accession rather than matched by name. BioGRID ORCS already
reports a Cellosaurus accession for most screens; this script fetches the record
behind each one so the system class (primary cells, immortalized line, cancer
line) is read from the ontology rather than guessed from the name.

Cellosaurus is released under CC BY 4.0 by the SIB Swiss Institute of
Bioinformatics.
"""

from __future__ import annotations

import json

from _fetchlib import RAW, client, get_json, write

API = "https://api.cellosaurus.org/cell-line/{acc}"

#: Cell systems named in the brief that must resolve whether or not a screen in
#: the corpus happens to mention them.
EXTRA = {
    "HUDEP-2": "CVCL_VI06",
    "HUDEP-1": "CVCL_VI05",
    "K-562": "CVCL_0004",
    "HEL": "CVCL_0001",
    "KU812": "CVCL_0379",
    "TF-1": "CVCL_0559",
    "OCI-AML3": "CVCL_1844",
    "HEK293": "CVCL_0045",
    "HeLa": "CVCL_0030",
}


def flatten(rec: dict) -> dict:
    accs = rec.get("accession-list") or []
    names = rec.get("name-list") or []
    species = rec.get("species-list") or []
    xrefs = rec.get("xref-list") or []
    diseases = rec.get("disease-list") or []
    return {
        "accession": next((a["value"] for a in accs if a.get("type") == "primary"), None),
        "name": next((n["value"] for n in names if n.get("type") == "identifier"), None),
        "synonyms": [n["value"] for n in names if n.get("type") == "synonym"],
        "category": rec.get("category"),
        "sex": rec.get("sex"),
        "age": rec.get("age"),
        "species": [s.get("name") or s.get("accession") for s in species],
        "diseases": [
            {"term": d.get("term") or d.get("value"), "accession": d.get("accession")}
            for d in diseases
        ],
        "xrefs": [
            {"db": x.get("database"), "acc": x.get("accession")} for x in xrefs if x.get("database")
        ],
        "derived_from_site": rec.get("derived-from-site-list"),
        "comments": [c.get("category") for c in rec.get("comment-list") or []],
    }


def main() -> None:
    wanted = dict(EXTRA)
    orcs_dir = RAW / "orcs"
    if orcs_dir.exists():
        for path in orcs_dir.glob("screen_*.json"):
            rec = json.loads(path.read_text())
            acc = rec.get("cellosaurus_id")
            if acc:
                wanted.setdefault(rec.get("cell_line_name") or acc, acc)

    by_acc = {acc: name for name, acc in wanted.items()}
    out, missing = {}, []
    with client() as c:
        for i, (acc, name) in enumerate(sorted(by_acc.items()), 1):
            try:
                data = get_json(c, API.format(acc=acc), params={"format": "json"}, tries=3)
            except RuntimeError:
                missing.append({"accession": acc, "name": name})
                continue
            lines = ((data.get("Cellosaurus") or {}).get("cell-line-list")) or []
            if not lines:
                missing.append({"accession": acc, "name": name})
                continue
            out[acc] = flatten(lines[0])
            if i % 50 == 0:
                print(f"  {i}/{len(by_acc)} resolved", flush=True)
    write("cellosaurus/cell_lines.json", out)
    write("cellosaurus/unresolved.json", missing)
    print(f"cell_lines={len(out)} unresolved={len(missing)}")


if __name__ == "__main__":
    main()
