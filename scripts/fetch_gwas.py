"""Fetch GWAS Catalog studies and associations for the HbF trait family.

This is the human genetic support term in the weighting function. A gene with a
genome-wide significant association to fetal hemoglobin level in people is
evidence of a different kind from a gene that scored in a cell line, and the
method signature treats it as such.

GWAS Catalog is EMBL-EBI and NHGRI. Terms are recorded in DATA_SOURCES.md.
"""

from __future__ import annotations

import time

from _fetchlib import client, get_json, write

API = "https://www.ebi.ac.uk/gwas/rest/api"

#: EFO traits covering the HbF phenotype family as the catalog names them.
TRAITS = (
    "fetal hemoglobin measurement",
    "F-cell distribution",
    "fetal hemoglobin levels",
    "hemoglobin measurement",
    "HbF",
)

KEEP_ASSOC = (
    "pvalue",
    "pvalueMantissa",
    "pvalueExponent",
    "pvalueDescription",
    "betaNum",
    "betaUnit",
    "betaDirection",
    "orPerCopyNum",
    "standardError",
    "riskFrequency",
    "snpType",
    "multiSnpHaplotype",
    "snpInteraction",
)


def study_meta(study: dict) -> dict:
    pub = study.get("publicationInfo") or {}
    return {
        "accessionId": study.get("accessionId"),
        "publicationDate": pub.get("publicationDate"),
        "pubmedId": pub.get("pubmedId"),
        "title": pub.get("title"),
        "journal": pub.get("publication"),
        "author": (pub.get("author") or {}).get("fullname"),
        "diseaseTrait": (study.get("diseaseTrait") or {}).get("trait"),
        "initialSampleSize": study.get("initialSampleSize"),
        "platforms": [p.get("manufacturer") for p in study.get("platforms") or []],
        "ancestries": [
            {
                "type": a.get("type"),
                "n": a.get("numberOfIndividuals"),
                "groups": [g.get("ancestralGroup") for g in a.get("ancestralGroups") or []],
            }
            for a in study.get("ancestries") or []
        ],
    }


def trim_assoc(a: dict) -> dict:
    out = {k: a.get(k) for k in KEEP_ASSOC}
    out["efoTraits"] = [t.get("trait") for t in a.get("efoTraits") or []]
    out["efoShortForms"] = [t.get("shortForm") for t in a.get("efoTraits") or []]
    loci = []
    for locus in a.get("loci") or []:
        genes, rsids = [], []
        for rag in locus.get("strongestRiskAlleles") or []:
            rsids.append(rag.get("riskAlleleName"))
        for gene in locus.get("authorReportedGenes") or []:
            genes.append(gene.get("geneName"))
        loci.append({"reportedGenes": genes, "riskAlleles": rsids})
    out["loci"] = loci
    study = a.get("study") or {}
    out["study"] = study_meta(study)
    return out


def main() -> None:
    with client() as c:
        studies: dict[str, dict] = {}
        for trait in TRAITS:
            page, total = 0, 1
            while page < total:
                data = get_json(
                    c,
                    f"{API}/studies/search/findByEfoTrait",
                    params={"efoTrait": trait, "size": 50, "page": page},
                )
                for st in (data.get("_embedded") or {}).get("studies") or []:
                    acc = st.get("accessionId")
                    if acc:
                        meta = study_meta(st)
                        meta["matched_trait"] = trait
                        studies.setdefault(acc, meta)
                total = (data.get("page") or {}).get("totalPages", 0)
                page += 1
                time.sleep(0.2)
            print(f"{trait}: corpus now {len(studies)} studies", flush=True)

        write("gwas/studies.json", list(studies.values()))

        # Association pages are fetched with an explicit size, and a study whose
        # associations cannot be retrieved is recorded rather than skipped
        # silently. Those failures land in the exclusions table, because an
        # unfetched study is a gap in "records available" and the ingestion
        # metric has to be able to see it.
        associations: list[dict] = []
        failed: list[dict] = []
        for i, acc in enumerate(sorted(studies), 1):
            page, total = 0, 1
            while page < total:
                try:
                    data = get_json(
                        c,
                        f"{API}/studies/{acc}/associations",
                        params={"projection": "associationByStudy", "size": 100, "page": page},
                        tries=3,
                    )
                except RuntimeError as exc:
                    failed.append({"studyAccession": acc, "page": page, "error": str(exc)[:200]})
                    print(f"  {acc} page {page} FAILED", flush=True)
                    break
                for a in (data.get("_embedded") or {}).get("associations") or []:
                    rec = trim_assoc(a)
                    rec["studyAccession"] = acc
                    associations.append(rec)
                total = (data.get("page") or {}).get("totalPages", 0) or 1
                page += 1
                time.sleep(0.2)
            if i % 20 == 0:
                print(f"  {i}/{len(studies)} studies, {len(associations)} associations", flush=True)

        write("gwas/associations.json", associations)
        write("gwas/fetch_failures.json", failed)
        print(f"association fetch failures: {len(failed)}")
        genes = sorted({g for a in associations for lo in a["loci"] for g in lo["reportedGenes"] if g})
        print(f"studies={len(studies)} associations={len(associations)} reported_genes={len(genes)}")


if __name__ == "__main__":
    main()
