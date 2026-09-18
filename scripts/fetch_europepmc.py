"""Fetch publication metadata and resolved dates from Europe PMC.

publication_date is load bearing for this whole benchmark, so it comes from one
place and one rule: prefer `firstPublicationDate` over the journal issue date.
Both are kept. See SCHEMA.md, "Date resolution rule".

Only bibliographic metadata is stored: PMID, DOI, title, journal, dates, author
string, and the license Europe PMC reports. No abstracts and no full text, per
the redistribution rule in DATA_SOURCES.md. Titles are bibliographic metadata
and are kept so a reader can identify a record; article bodies are not.

Two design points worth stating, because both were wrong in earlier versions of
this script and both silently corrupted the evidence base.

The cap. An early version capped each gene at 400 records. Europe PMC returns
newest first, so that truncation removed almost the whole pre-2018 window:
BCL11A came back with 400 records of which one predated 2018. For a benchmark
whose entire method is a temporal holdout, that is not a performance detail. The
cap now exceeds the largest hit count in scope and the hit count is recorded so
truncation is reported rather than hidden.

The query. An early version searched the current HGNC symbol only. That found
three pre-2018 records for EIF2AK1, which would have made the primary
evaluation's known answer look unreachable from the pre-T record. The gene is
called HRI in most of the literature that matters. Queries now expand each gene
to its HGNC aliases, its withdrawn symbols and the informal names in
`hindcast.scope`, all of which were standard usage long before any slice used
here. Searching for a 2018 discovery under a name coined in 2018 would be the
contamination this project exists to avoid; searching for it under the name the
field actually used in 2010 is just competent retrieval.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from _fetchlib import RAW, client, get_json, write

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hindcast.scope import ALL_SCOPE_GENES, INFORMAL_NAMES  # noqa: E402

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

KEEP = (
    "id",
    "source",
    "pmid",
    "pmcid",
    "doi",
    "title",
    "journalTitle",
    "pubYear",
    "firstPublicationDate",
    "journalIssn",
    "authorString",
    "pubType",
    "isOpenAccess",
    "license",
    "citedByCount",
)

#: The HbF phenotype family, as the literature names it. A record matching this
#: is evidence about fetal hemoglobin specifically.
HBF_QUERY = (
    '("fetal hemoglobin" OR "fetal haemoglobin" OR "HbF" OR "F-cell" OR '
    '"gamma-globin" OR "gamma globin" OR "HBG1" OR "HBG2" OR "globin switching")'
)

#: The wider erythroid context. A record matching this but not the above is
#: evidence that a gene operates in the right tissue, which is weaker and is
#: tagged as such so the axiom extractor can tell the two apart.
ERYTHROID_QUERY = (
    '("erythroid" OR "erythropoiesis" OR "erythroblast" OR "globin" OR '
    '"hematopoietic stem cell" OR "haematopoietic stem cell")'
)

#: Aliases that are too short or too common to search on without drowning the
#: result set in unrelated records. Excluded from query expansion by name.
UNSEARCHABLE_ALIASES = {
    "hri", "lrf", "tr2", "tr4", "hel", "mi2b", "apa-1", "p66", "dnmt",
    "kmt5a", "set8", "pr-set7", "cll", "bcl", "hbf",
}


def trim(rec: dict) -> dict:
    out = {k: rec.get(k) for k in KEEP}
    jinfo = rec.get("journalInfo") or {}
    out["issue_year"] = jinfo.get("yearOfPublication")
    out["print_publication_date"] = jinfo.get("printPublicationDate")
    return out


def gene_terms(symbol: str, hgnc: dict[str, dict]) -> list[str]:
    """The names this gene has actually been called, for query expansion."""
    terms = {symbol}
    row = hgnc.get(symbol.upper())
    if row:
        for field in ("alias_symbol", "prev_symbol"):
            for alias in (row.get(field) or "").split("|"):
                alias = alias.strip()
                if len(alias) >= 3 and alias.lower() not in UNSEARCHABLE_ALIASES:
                    terms.add(alias)
    for informal, symbols in INFORMAL_NAMES.items():
        if symbol in symbols and len(informal) >= 4:
            terms.add(informal)
    # A long informal name is safe to search even if a short alias was dropped.
    if symbol == "EIF2AK1":
        terms.update({"heme-regulated inhibitor", "heme-regulated eIF2alpha kinase"})
    if symbol == "ZBTB7A":
        terms.add("leukemia/lymphoma related factor")
    return sorted(terms)


def search_all(c, query: str, cap: int = 12000) -> tuple[list[dict], int]:
    """Page through a query with cursorMark, which is complete pagination."""
    cursor, seen, out = "*", set(), []
    hit_count = 0
    while len(out) < cap:
        data = get_json(
            c,
            SEARCH,
            params={
                "query": query,
                "format": "json",
                "pageSize": 100,
                "cursorMark": cursor,
                "resultType": "core",
            },
        )
        hit_count = data.get("hitCount", hit_count)
        results = (data.get("resultList") or {}).get("result") or []
        if not results:
            break
        for rec in results:
            key = rec.get("pmid") or rec.get("id")
            if key and key not in seen:
                seen.add(key)
                out.append(trim(rec))
        nxt = data.get("nextCursorMark")
        if not nxt or nxt == cursor:
            break
        cursor = nxt
    return out, hit_count


def fetch_by_pmids(c, pmids: list[str]) -> list[dict]:
    out: list[dict] = []
    batch = 40
    for i in range(0, len(pmids), batch):
        chunk = [p for p in pmids[i : i + batch] if p]
        if not chunk:
            continue
        query = " OR ".join(f"EXT_ID:{p}" for p in chunk)
        data = get_json(
            c,
            SEARCH,
            params={"query": query, "format": "json", "pageSize": batch, "resultType": "core"},
        )
        out.extend(trim(r) for r in (data.get("resultList") or {}).get("result") or [])
    return out


def load_hgnc() -> dict[str, dict]:
    path = RAW / "hgnc" / "hgnc_complete_set.tsv"
    if not path.exists():
        return {}
    with path.open() as fh:
        return {r["symbol"].upper(): r for r in csv.DictReader(fh, delimiter="\t")}


def main() -> None:
    hgnc = load_hgnc()
    with client() as c:
        lit: dict[str, dict] = {}
        coverage: list[dict] = []

        def absorb(records: list[dict], gene: str, tier: str) -> None:
            for rec in records:
                key = rec.get("pmid") or rec["id"]
                entry = lit.setdefault(key, rec)
                entry["matched_genes"] = sorted(set(entry.get("matched_genes", [])) | {gene})
                entry["matched_tiers"] = sorted(set(entry.get("matched_tiers", [])) | {tier})

        for gene in ALL_SCOPE_GENES:
            terms = gene_terms(gene, hgnc)
            gene_clause = "(" + " OR ".join(f'"{t}"' for t in terms) + ")"
            row = {"gene": gene, "terms": terms}
            for tier, pheno in (("hbf", HBF_QUERY), ("erythroid", ERYTHROID_QUERY)):
                records, hit_count = search_all(c, f"{gene_clause} AND {pheno}")
                absorb(records, gene, tier)
                row[f"{tier}_hits"] = hit_count
                row[f"{tier}_retrieved"] = len(records)
                row[f"{tier}_truncated"] = hit_count > len(records)
            coverage.append(row)
            flag = " TRUNCATED" if row["hbf_truncated"] or row["erythroid_truncated"] else ""
            print(
                f"{gene}: hbf {row['hbf_retrieved']}/{row['hbf_hits']} "
                f"erythroid {row['erythroid_retrieved']}/{row['erythroid_hits']} "
                f"(corpus {len(lit)}){flag}",
                flush=True,
            )

        write("europepmc/scope_literature.json", list(lit.values()))
        write("europepmc/coverage.json", coverage)

        orcs_dir = RAW / "orcs"
        pmids = set()
        if orcs_dir.exists():
            import json as _json

            for path in orcs_dir.glob("screen_*.json"):
                rec = _json.loads(path.read_text())
                if rec.get("pmid"):
                    pmids.add(rec["pmid"])
        missing = sorted(pmids - set(lit))
        print(f"resolving {len(missing)} ORCS PMIDs not already in the corpus", flush=True)
        write("europepmc/orcs_publications.json", fetch_by_pmids(c, missing))
        print(f"scope_literature={len(lit)}")


if __name__ == "__main__":
    main()
