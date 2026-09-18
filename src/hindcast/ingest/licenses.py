"""License strings, one per source, and the required attributions.

Every node and edge carries a license. These are the only values that field may
take, so a new source cannot be loaded without someone recording its license
here first. That is what makes the redistribution scan enforceable.

DATA_SOURCES.md holds the full record: institution, access date, snapshot hash
and the attribution text written out.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLicense:
    name: str
    license: str
    institution: str
    url: str
    attribution_required: bool
    redistributable: bool
    attribution: str = ""
    note: str = ""


SOURCES: dict[str, SourceLicense] = {
    "biogrid_orcs": SourceLicense(
        name="BioGRID ORCS",
        license="MIT License",
        institution="BioGRID, TyersLab, Mount Sinai Hospital and University of Montreal",
        url="https://orcs.thebiogrid.org/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "CRISPR screen data from BioGRID ORCS (Open Repository of CRISPR Screens), "
            "https://orcs.thebiogrid.org/. BioGRID is distributed under the MIT License."
        ),
    ),
    "depmap": SourceLicense(
        name="DepMap",
        license="CC BY 4.0",
        institution="Broad Institute",
        url="https://depmap.org/portal/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "DepMap, Broad (2024). DepMap 24Q4 Public. Figshare+. Dataset. "
            "https://doi.org/10.25452/figshare.plus.27993248.v1. Licensed CC BY 4.0."
        ),
        note=(
            "Gene-effect values reach this project through the Open Targets Platform, "
            "which redistributes them. Both are attributed. The figshare release is "
            "the licensing record, confirmed as CC BY 4.0 via the figshare API."
        ),
    ),
    "opentargets": SourceLicense(
        name="Open Targets Platform",
        license="CC0 1.0",
        institution="Open Targets, EMBL-EBI and partners",
        url="https://platform.opentargets.org/",
        attribution_required=False,
        redistributable=True,
        attribution=(
            "Target-disease evidence from the Open Targets Platform, "
            "https://platform.opentargets.org/, released under CC0 1.0."
        ),
    ),
    "gwas_catalog": SourceLicense(
        name="GWAS Catalog",
        license="EMBL-EBI terms of use, open access with attribution",
        institution="EMBL-EBI and NHGRI",
        url="https://www.ebi.ac.uk/gwas/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "Genetic association data from the NHGRI-EBI GWAS Catalog, "
            "https://www.ebi.ac.uk/gwas/. EMBL-EBI data are available without "
            "restriction under its terms of use, which require attribution and "
            "citation of the originating studies. Study accessions and PubMed IDs "
            "are recorded on every association row in this repository."
        ),
    ),
    "europepmc": SourceLicense(
        name="Europe PMC",
        license="Bibliographic metadata only; per-article licenses vary",
        institution="EMBL-EBI",
        url="https://europepmc.org/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "Publication metadata and resolved publication dates from Europe PMC, "
            "https://europepmc.org/."
        ),
        note=(
            "Only identifiers, dates, journal names, author strings and titles are "
            "committed. No abstracts and no full text, because per-article licenses "
            "vary and many do not permit redistribution. Where text is needed it is "
            "fetched to a gitignored cache by PMID."
        ),
    ),
    "clinicaltrials_gov": SourceLicense(
        name="ClinicalTrials.gov",
        license="Public domain (US Government work)",
        institution="US National Library of Medicine",
        url="https://clinicaltrials.gov/",
        attribution_required=False,
        redistributable=True,
        attribution="Trial records from ClinicalTrials.gov, US National Library of Medicine.",
    ),
    "hgnc": SourceLicense(
        name="HGNC",
        license="CC0 1.0",
        institution="HUGO Gene Nomenclature Committee, EMBL-EBI",
        url="https://www.genenames.org/",
        attribution_required=False,
        redistributable=True,
        attribution=(
            "Gene symbols, identifiers and approval dates from the HUGO Gene "
            "Nomenclature Committee, https://www.genenames.org/, released under CC0."
        ),
    ),
    "cellosaurus": SourceLicense(
        name="Cellosaurus",
        license="CC BY 4.0",
        institution="SIB Swiss Institute of Bioinformatics",
        url="https://www.cellosaurus.org/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "Cell line identifiers and metadata from Cellosaurus, "
            "https://www.cellosaurus.org/, SIB Swiss Institute of Bioinformatics, "
            "licensed CC BY 4.0."
        ),
    ),
    "encode": SourceLicense(
        name="ENCODE",
        license="Free to use without restriction, citation required",
        institution="ENCODE Consortium",
        url="https://www.encodeproject.org/",
        attribution_required=True,
        redistributable=True,
        attribution=(
            "Regulatory element annotations from the ENCODE Consortium, "
            "https://www.encodeproject.org/. ENCODE's data use policy states that "
            "external users may freely download, analyze and publish results based "
            "on any ENCODE data without restrictions, and asks that the Consortium "
            "and the accessions used be cited."
        ),
    ),
    "hindcast_vocabulary": SourceLicense(
        name="crispr-hindcast project vocabulary",
        license="MIT License",
        institution="this repository",
        url="https://github.com/",
        attribution_required=False,
        redistributable=True,
        attribution="Phenotype families and modality cost classes defined by this project.",
    ),
}

#: Sources deliberately excluded, with the reason. Recorded here and in
#: DATA_SOURCES.md, because an unexplained absence looks like an oversight.
EXCLUDED_SOURCES: dict[str, str] = {
    "project_score": (
        "Excluded. The Cancer Dependency Map at Sanger data usage policy grants "
        "users a 'non-exclusive, non-transferable right to use data files for "
        "internal proprietary research and educational purposes' and excludes "
        "'use of the data (in whole or any significant part) for resale either "
        "alone or in combination with additional data/product offerings, or for "
        "provision of commercial services'. A non-transferable right of internal "
        "use does not permit committing the data to a public MIT-licensed "
        "repository, so Project Score is not ingested. Essentiality evidence comes "
        "from BioGRID ORCS and from DepMap instead. Checked 2026-09-17 at "
        "https://depmap.sanger.ac.uk/documentation/data-usage-policy/."
    ),
}


def license_of(source_key: str) -> str:
    if source_key not in SOURCES:
        raise KeyError(
            f"no license recorded for source {source_key!r}; add it to "
            f"hindcast.ingest.licenses.SOURCES and to DATA_SOURCES.md before loading it"
        )
    return SOURCES[source_key].license
