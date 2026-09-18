"""Build the frozen rule book: when each gene's HbF role was established.

The answer key for this benchmark is the published record, so it has to be
derived by a stated rule rather than assembled from memory. The rule is:

    A gene's HbF-regulator role is established on the first publication date of
    the earliest primary article whose TITLE contains all three of: one of the
    gene's names, a regulatory verb, and an HbF or globin term.

The requirement that the title name the gene is not decoration. Without it the
rule dated EIF2AK1 to May 2013, on the strength of an article titled
"Eukaryotic initiation factor 2alpha phosphorylation mediates fetal hemoglobin
induction through a post-transcriptional mechanism". That article is about
eIF2alpha, the substrate, and matched only because the kinase is named
somewhere in its text. Requiring the title to name the gene moves EIF2AK1 to
July 2018 and the article that actually identified it.

Titles only. Not abstracts, because their licenses vary and the redistribution
rule forbids committing them, and not a human reading of the full text, because
that would not be reproducible. A title is a claim the authors chose to make in
the one line everybody reads.

The rule is blunt and it will be wrong at the edges. Two known failure modes are
reported in LIMITATIONS.md: a review article whose title asserts a role it did
not establish will date a gene too early, and a paper that established a role
without saying so in the title will date it too late. Every entry carries its
PMID and title so any reader can check the call, and the candidates that the
rule rejected are written out alongside for the same reason.

Run once, review the output, tag it. The git tag is the proof it was frozen
before the first evaluation run.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _fetchlib import ROOT, client, get_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hindcast.scope import ALL_SCOPE_GENES, INFORMAL_NAMES, SCOPE_GENES  # noqa: E402
from hindcast.textmatch import fold, names_gene, usable_terms  # noqa: E402

SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

#: A verb that asserts the gene does something to the phenotype.
REGULATORY_VERB = re.compile(
    r"\b(regulat\w*|silenc\w*|repress\w*|induc\w*|activat\w*|control\w*|"
    r"modulat\w*|derepress\w*|reactivat\w*|elevat\w*|increas\w*|suppress\w*|"
    r"switch\w*|de-?repress\w*)\b",
    re.I,
)

#: The phenotype, as a title would name it.
PHENOTYPE_TERM = re.compile(
    r"(fetal h[ae]moglobin|hbf\b|f-cells?\b|gamma-?globin|γ-?globin|"
    r"fetal globin|globin switch\w*|globin gene)",
    re.I,
)

#: Titles that assert a role the article did not establish. Reviews and
#: commentaries are excluded, because dating a discovery to a review that
#: summarises it would place the establishment date years early.
NON_PRIMARY = re.compile(
    r"\b(review|overview|perspective|commentary|editorial|news and views|"
    r"progress and prospects|a survey|current (status|understanding)|"
    r"therapeutic (target|approach)es? (in|for)|potential (diagnostic|therapeutic))\b",
    re.I,
)

NON_PRIMARY_TYPES = {"review", "editorial", "comment", "letter", "news"}


def gene_query_terms(symbol: str) -> list[str]:
    terms = {symbol}
    for informal, symbols in INFORMAL_NAMES.items():
        if symbol in symbols and len(informal) >= 4:
            terms.add(informal)
    if symbol == "EIF2AK1":
        terms.update({"HRI", "heme-regulated inhibitor", "heme-regulated eIF2alpha kinase"})
    if symbol == "ZBTB7A":
        terms.add("LRF")
    if symbol == "KDM1A":
        terms.add("LSD1")
    if symbol == "CHD4":
        terms.update({"Mi-2beta", "Mi2beta", "Mi-2b", "Mi2b", "CHD4/NuRD"})
    return sorted(terms)


def is_primary_claim(rec: dict, terms: list[str]) -> tuple[bool, str]:
    title = (rec.get("title") or "").strip()
    if not title:
        return False, "no title"
    if not names_gene(title, terms):
        return False, "title does not name the gene"
    if not REGULATORY_VERB.search(fold(title)):
        return False, "title has no regulatory verb"
    if not PHENOTYPE_TERM.search(fold(title)):
        return False, "title does not name the HbF phenotype"
    if NON_PRIMARY.search(title):
        return False, "title reads as a review or commentary"
    ptypes = {p.strip().lower() for p in (rec.get("pubType") or "").split(";") if p.strip()}
    if ptypes & NON_PRIMARY_TYPES:
        return False, f"publication type {sorted(ptypes)} is not a primary report"
    return True, "title asserts a regulatory role over an HbF readout"


def main() -> None:
    entries: dict[str, dict] = {}
    with client() as c:
        for symbol in ALL_SCOPE_GENES:
            query_terms = gene_query_terms(symbol)
            # Search with every name, including the short ones, so nothing is
            # missed at retrieval. Match titles with the curated subset, so a
            # three-letter alias cannot credit an unrelated article.
            terms = usable_terms(symbol, query_terms)
            clause = "(" + " OR ".join(f'"{t}"' for t in query_terms) + ")"
            query = (
                f"{clause} AND (\"fetal hemoglobin\" OR \"fetal haemoglobin\" OR \"HbF\" OR "
                f"\"gamma-globin\" OR \"gamma globin\" OR \"globin switching\")"
            )
            cursor, records = "*", []
            while True:
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
                page = (data.get("resultList") or {}).get("result") or []
                if not page:
                    break
                records.extend(page)
                nxt = data.get("nextCursorMark")
                if not nxt or nxt == cursor:
                    break
                cursor = nxt
                if len(records) >= 6000:
                    break

            dated = [
                r
                for r in records
                if (r.get("firstPublicationDate") or "") and len(r["firstPublicationDate"]) >= 10
            ]
            dated.sort(key=lambda r: (r["firstPublicationDate"], str(r.get("pmid") or "")))

            accepted, rejected_examples, near_misses = None, [], []
            for rec in dated:
                ok, why = is_primary_claim(rec, terms)
                if ok:
                    accepted = {
                        "pmid": rec.get("pmid"),
                        "doi": rec.get("doi"),
                        "date": rec["firstPublicationDate"],
                        "title": rec.get("title"),
                        "journal": rec.get("journalTitle"),
                        "reason": why,
                    }
                    break
                title = rec.get("title") or ""
                # A near miss asserts a regulatory role over an HbF readout but
                # does not name this gene in its title. These are where the rule
                # is most likely to be wrong, so they are written out in full for
                # a reader to check rather than discarded.
                if (
                    REGULATORY_VERB.search(title)
                    and PHENOTYPE_TERM.search(title)
                    and not names_gene(title, terms)
                    and len(near_misses) < 6
                ):
                    near_misses.append(
                        {
                            "pmid": rec.get("pmid"),
                            "date": rec["firstPublicationDate"],
                            "title": title,
                            "rejected_because": why,
                        }
                    )
                elif REGULATORY_VERB.search(title) and len(rejected_examples) < 3:
                    rejected_examples.append(
                        {
                            "pmid": rec.get("pmid"),
                            "date": rec["firstPublicationDate"],
                            "title": title[:160],
                            "rejected_because": why,
                        }
                    )

            entries[symbol] = {
                "symbol": symbol,
                "core_scope": symbol in SCOPE_GENES,
                "query_terms": terms,
                "records_considered": len(dated),
                "established": accepted is not None,
                "establishing_record": accepted,
                "rejected_candidates": rejected_examples,
                "near_misses": near_misses,
            }
            state = accepted["date"] if accepted else "not established"
            print(f"{symbol:10} {len(dated):>5} records -> {state}", flush=True)

    out = ROOT / "eval" / "rulebook" / "gene_establishment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=1, sort_keys=True, default=str))
    print(f"wrote {out}")
    est = sum(1 for e in entries.values() if e["established"])
    print(f"\n{est}/{len(entries)} genes have an establishing record by the stated rule")


if __name__ == "__main__":
    main()
