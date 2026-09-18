"""Fetch the complete HGNC gene set.

The full release is fetched rather than a per-gene lookup, for the reason given
in SCHEMA.md: gene nodes must reflect the gene universe and not the corpus, or
the presence of a node would leak post-T information. `date_approved_reserved`
from this file becomes the reference node's `effective_date`.

HGNC is released under CC0 1.0.
"""

from __future__ import annotations

import csv
import io

from _fetchlib import RAW, UA, client

URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
KEEP = (
    "hgnc_id",
    "symbol",
    "name",
    "locus_group",
    "locus_type",
    "status",
    "date_approved_reserved",
    "date_symbol_changed",
    "date_name_changed",
    "alias_symbol",
    "prev_symbol",
    "ensembl_gene_id",
    "entrez_id",
    "uniprot_ids",
    "location",
    # Gene family. The cost lens needs a protein class to infer a therapeutic
    # modality, and it must be a class that was knowable before T. A gene's
    # membership of the protein kinase superfamily is that kind of fact.
    "gene_group",
    "gene_group_id",
    "enzyme_id",
)


def main() -> None:
    out = RAW / "hgnc" / "hgnc_complete_set.tsv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with client(timeout=300.0) as c:
        r = c.get(URL)
        r.raise_for_status()
        text = r.text
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    rows = [{k: (row.get(k) or "") for k in KEEP} for row in reader]
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KEEP, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    approved = sum(1 for r in rows if r["status"] == "Approved")
    dated = sum(1 for r in rows if r["date_approved_reserved"])
    print(f"hgnc rows={len(rows)} approved={approved} with_approval_date={dated} -> {out}")


if __name__ == "__main__":
    main()
