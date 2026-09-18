"""Fetch registered trials for sickle cell disease and beta-thalassemia.

Trials anchor the cost lens in what has actually been built. An ex vivo edited
autologous graft is a real manufacturing pathway with a real price, and the
trial record is where the modality, the conditioning regimen and the dates come
from.

ClinicalTrials.gov records are United States government work in the public
domain.
"""

from __future__ import annotations

import time

from _fetchlib import client, get_json, write

API = "https://clinicaltrials.gov/api/v2/studies"

QUERIES = (
    {"query.cond": "sickle cell disease"},
    {"query.cond": "beta-thalassemia"},
    {"query.cond": "sickle cell disease", "query.intr": "gene therapy OR gene editing"},
    {"query.cond": "sickle cell disease", "query.intr": "hydroxyurea"},
    {"query.term": "fetal hemoglobin"},
)

FIELDS = ",".join(
    (
        "NCTId",
        "BriefTitle",
        "OfficialTitle",
        "OverallStatus",
        "StartDate",
        "PrimaryCompletionDate",
        "StudyFirstSubmitDate",
        "StudyFirstPostDate",
        "LastUpdatePostDate",
        "Phase",
        "StudyType",
        "Condition",
        "InterventionType",
        "InterventionName",
        "LeadSponsorName",
        "LeadSponsorClass",
        "EnrollmentCount",
        "PrimaryOutcomeMeasure",
        "ResultsFirstPostDate",
        "ReferencePMID",
        "ReferenceType",
    )
)


def main() -> None:
    studies: dict[str, dict] = {}
    with client() as c:
        for q in QUERIES:
            token = None
            while True:
                params = dict(q, fields=FIELDS, pageSize=100, format="json")
                if token:
                    params["pageToken"] = token
                data = get_json(c, API, params=params)
                for st in data.get("studies") or []:
                    nct = (
                        ((st.get("protocolSection") or {}).get("identificationModule") or {})
                        .get("nctId")
                    )
                    if nct:
                        studies.setdefault(nct, st)
                token = data.get("nextPageToken")
                time.sleep(0.2)
                if not token:
                    break
            print(f"{q}: corpus now {len(studies)} trials", flush=True)
    write("ctgov/studies.json", list(studies.values()))
    print(f"trials={len(studies)}")


if __name__ == "__main__":
    main()
