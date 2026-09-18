"""Fetch Open Targets Platform data for the scope genes.

Two things come from here:

1.  Target-disease association evidence for sickle cell disease and the
    beta-thalassemias, with the data type and the source of each piece of
    evidence. This is where human genetic support enters the weighting function.
2.  DepMap gene-effect values per cell line, which Open Targets redistributes.
    These are what the adversary's pan-essentiality trap is built from: a gene
    whose knockout kills the cell is not a therapeutic target however well it
    raises HbF.

Open Targets Platform data is CC0 1.0. The DepMap values it carries remain
Broad Institute data under CC BY 4.0 and are attributed as such in
DATA_SOURCES.md and the README.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from _fetchlib import client, post_json, write

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hindcast.scope import ALL_SCOPE_GENES  # noqa: E402

API = "https://api.platform.opentargets.org/api/v4/graphql"

#: Sickle cell disease and the beta-thalassemias, by EFO/MONDO ID.
DISEASES = {
    "EFO_0000697": "sickle cell disease",
    "MONDO_0019402": "beta-thalassemia",
    "EFO_0009749": "hemoglobinopathy",
}

RESOLVE = """
query Resolve($q: String!) {
  search(queryString: $q, entityNames: ["target"], page: {index: 0, size: 5}) {
    hits { id name entity object { ... on Target { id approvedSymbol biotype } } }
  }
}
"""

TARGET = """
query T($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    biotype
    isEssential
    dbXrefs { id source }
    tractability { label modality value }
    depMapEssentiality {
      tissueName
      screens { depmapId cellLineName diseaseFromSource geneEffect expression }
    }
  }
}
"""

ASSOC = """
query A($id: String!, $efos: [String!]) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    associatedDiseases(Bs: $efos, page: {index: 0, size: 25}) {
      count
      rows {
        disease { id name }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""

EVIDENCE = """
query E($id: String!, $efo: String!) {
  disease(efoId: $efo) {
    id
    name
    evidences(ensemblIds: [$id], size: 50) {
      count
      rows {
        id
        datasourceId
        datatypeId
        score
        literature
        publicationYear
        publicationDate
        releaseDate
        crisprScreenLibrary
        cellType
        resourceScore
        statisticalMethod
        targetModulation
        studyId
        variantRsId
        pValueMantissa
        pValueExponent
        beta
        oddsRatio
        confidence
        diseaseFromSource
        targetFromSourceId
      }
    }
  }
}
"""


def main() -> None:
    with client() as c:
        # Ensembl IDs for the scope symbols.
        ens: dict[str, str] = {}
        for sym in ALL_SCOPE_GENES:
            data = post_json(c, API, {"query": RESOLVE, "variables": {"q": sym}})
            for hit in ((data.get("data") or {}).get("search") or {}).get("hits") or []:
                obj = hit.get("object") or {}
                if (obj.get("approvedSymbol") or "").upper() == sym.upper():
                    ens[sym] = obj["id"]
                    break
            time.sleep(0.15)
        write("opentargets/ensembl_ids.json", ens)
        print(f"resolved {len(ens)}/{len(ALL_SCOPE_GENES)} symbols to Ensembl IDs", flush=True)

        targets, assocs, evidence = {}, {}, {}
        efos = list(DISEASES)
        for sym, eid in ens.items():
            targets[sym] = (
                post_json(c, API, {"query": TARGET, "variables": {"id": eid}}).get("data") or {}
            ).get("target")
            assocs[sym] = (
                post_json(c, API, {"query": ASSOC, "variables": {"id": eid, "efos": efos}}).get(
                    "data"
                )
                or {}
            ).get("target")
            per_disease = {}
            for efo in efos:
                got = (
                    post_json(c, API, {"query": EVIDENCE, "variables": {"id": eid, "efo": efo}}).get(
                        "data"
                    )
                    or {}
                ).get("disease")
                if got and (got.get("evidences") or {}).get("count"):
                    per_disease[efo] = got
                time.sleep(0.1)
            if per_disease:
                evidence[sym] = per_disease
            print(f"{sym}: target+assoc+evidence({len(per_disease)} diseases)", flush=True)
            time.sleep(0.15)

        write("opentargets/targets.json", targets)
        write("opentargets/associations.json", assocs)
        write("opentargets/evidence.json", evidence)
        print(f"targets={len(targets)} with_evidence={len(evidence)}")


if __name__ == "__main__":
    main()
