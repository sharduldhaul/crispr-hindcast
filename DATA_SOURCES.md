# Data sources

Every source used, with its license, the attribution it requires written out in
full, the date it was accessed and the hash of what was committed. Sources that
were considered and excluded are listed too, with the reason, because an
unexplained absence looks like an oversight.

Access date for every source below: **2026-09-17**.

The repository's own code is MIT licensed. That license covers the code only.
Each dataset keeps its original license, listed here.

Redistribution rule, applied to everything in `data/snapshot/`: identifiers,
structured metadata, numeric measurements and extracted facts are committed.
Full-text articles and abstracts are not, because per-article licenses vary and
many do not permit redistribution. Titles are committed, as bibliographic
metadata. Where the pipeline needs article text it stores the PMID and a fetch
script and caches the text in a gitignored directory.
`tests/test_redistribution.py` scans the committed snapshot for fields that
would mean article text is present and fails the build if it finds any.

## Included

### BioGRID ORCS

| | |
| --- | --- |
| Institution | BioGRID, TyersLab, Mount Sinai Hospital and University of Montreal |
| License | MIT License, academic and commercial use permitted |
| URL | https://orcs.thebiogrid.org/ |
| Release | 2.0.18, human set |
| Used for | CRISPR screen metadata, per-gene screen scores, PMIDs |
| Bulk file sha256 | `39222a9650eed083edf193debe45eedc4aabc779ca04ea70107b6bd1efd9b8d7` |

Required attribution:

> CRISPR screen data from BioGRID ORCS (Open Repository of CRISPR Screens),
> https://orcs.thebiogrid.org/. BioGRID is distributed under the MIT License.

Two notes on how this source was accessed. The bulk release ships one hit table
per screen and no screen-level index, and the REST webservice requires a
registered access key. The screen-level metadata this project needs, meaning
PMID, cell line with Cellosaurus accession, perturbation type and the stated
significance rule, is on the public screen pages, and
`scripts/fetch_orcs.py` reads it from there.

The second note is a finding about the source rather than about the fetch. The
human release contains no fetal hemoglobin screen. Of 1,952 human screens, none
names fetal hemoglobin, gamma globin or F-cells in its phenotype, rationale,
notes, title or condition, and none is in an HUDEP-2 or CD34+ system. 138 are in
K-562. The HbF screens that the field's key results came from are not curated
here. ORCS therefore contributes fitness and proliferation evidence to this
project, which is load bearing for the pan-essentiality trap, and no direct HbF
measurements. This is stated in LIMITATIONS.md as well, because it constrains
what the benchmark can measure.

### DepMap

| | |
| --- | --- |
| Institution | Broad Institute |
| License | CC BY 4.0 |
| URL | https://depmap.org/portal/ |
| Release | DepMap 24Q4 Public |
| DOI | https://doi.org/10.25452/figshare.plus.27993248.v1 |
| Used for | Gene-effect values per cell line, for the pan-essentiality trap |

Required attribution:

> DepMap, Broad (2024). DepMap 24Q4 Public. Figshare+. Dataset.
> https://doi.org/10.25452/figshare.plus.27993248.v1. Licensed CC BY 4.0.

The license was confirmed through the figshare API for that release record,
which returns `CC BY 4.0` with the citation above. The DepMap portal's own terms
of use add conditions on portal use that the figshare release does not, so the
figshare release is treated as the licensing record and is what is cited.

Gene-effect values reach this project through the Open Targets Platform, which
redistributes them. Both are attributed. These rows carry the DepMap release
date rather than a per-experiment date, because that is the only date the source
supports, and the consequence is deliberate: dated at the release, they fall
after every evaluation cutoff used here and no slice can see them. They are
ground truth for the adversary and the grader. Pre-cutoff essentiality evidence
comes from the dated BioGRID ORCS screens instead.

### Open Targets Platform

| | |
| --- | --- |
| Institution | Open Targets, EMBL-EBI and partners |
| License | CC0 1.0 |
| URL | https://platform.opentargets.org/ |
| Used for | Target-disease evidence for sickle cell disease and beta-thalassemia, and the DepMap values above |

Attribution, not required by CC0 but given:

> Target-disease evidence from the Open Targets Platform,
> https://platform.opentargets.org/, released under CC0 1.0.

### NHGRI-EBI GWAS Catalog

| | |
| --- | --- |
| Institution | EMBL-EBI and NHGRI |
| License | EMBL-EBI terms of use: available without restriction, attribution and citation of the originating studies required |
| URL | https://www.ebi.ac.uk/gwas/ |
| Used for | Human genetic association evidence for the HbF trait family |

Required attribution:

> Genetic association data from the NHGRI-EBI GWAS Catalog,
> https://www.ebi.ac.uk/gwas/. EMBL-EBI data are available without restriction
> under its terms of use, which require attribution and citation of the
> originating studies. Study accessions and PubMed IDs are recorded on every
> association row in this repository.

### Europe PMC

| | |
| --- | --- |
| Institution | EMBL-EBI |
| License | Bibliographic metadata; per-article licenses vary |
| URL | https://europepmc.org/ |
| Used for | Publication metadata and the resolved publication date that the whole time slice turns on |

Required attribution:

> Publication metadata and resolved publication dates from Europe PMC,
> https://europepmc.org/.

Only identifiers, dates, journal names, author strings and titles are committed.
No abstracts and no full text. This is the source the redistribution rule was
written for.

### ClinicalTrials.gov

| | |
| --- | --- |
| Institution | US National Library of Medicine |
| License | Public domain, United States Government work |
| URL | https://clinicaltrials.gov/ |
| Used for | Registered trials, which anchor the cost lens in what has been built |

> Trial records from ClinicalTrials.gov, US National Library of Medicine.

### HGNC

| | |
| --- | --- |
| Institution | HUGO Gene Nomenclature Committee, EMBL-EBI |
| License | CC0 1.0 |
| URL | https://www.genenames.org/ |
| Used for | Gene identity, aliases, withdrawn symbols, protein family, and the approval date that dates every gene reference node |

> Gene symbols, identifiers and approval dates from the HUGO Gene Nomenclature
> Committee, https://www.genenames.org/, released under CC0.

### Cellosaurus

| | |
| --- | --- |
| Institution | SIB Swiss Institute of Bioinformatics |
| License | CC BY 4.0 |
| URL | https://www.cellosaurus.org/ |
| Used for | Cell line identity and category, which sets the largest term in the weighting function |

Required attribution:

> Cell line identifiers and metadata from Cellosaurus,
> https://www.cellosaurus.org/, SIB Swiss Institute of Bioinformatics, licensed
> CC BY 4.0.

## Excluded, with reasons

### Project Score, the Cancer Dependency Map at Sanger

Excluded on licensing.

The data usage policy at https://depmap.sanger.ac.uk/documentation/data-usage-policy/,
checked on 2026-09-17, grants users

> a non-exclusive, non-transferable right to use data files for internal
> proprietary research and educational purposes, including target, biomarker and
> drug discovery

and excludes

> use of the data (in whole or any significant part) for resale either alone or
> in combination with additional data/product offerings, or for provision of
> commercial services.

A non-transferable right of internal use does not permit committing the data to
a public MIT-licensed repository. The brief's instruction was to check and
record the current terms, and having checked them, the source is not ingested
rather than ingested on a guess. Essentiality evidence comes from BioGRID ORCS
and from DepMap instead, and the loss is that European cell line coverage is
thinner than it would otherwise be.

### ENCODE

Excluded on relevance, not on licensing. The license is permissive and was
confirmed.

ENCODE's data use policy at https://www.encodeproject.org/help/citing-encode/
states that

> External data users may freely download, analyze and publish results based on
> any ENCODE data without restrictions

and asks that the Consortium's publications, the production laboratories and the
accessions used be cited.

It is excluded because it has nothing to contribute to this question at these
dates. Querying every TF ChIP-seq experiment whose target is a scope gene
returns 697 experiments, of which 176 are CTCF. Six are in an erythroid context,
meaning K-562, erythroblast, or CD36-positive erythrocyte precursor cells, and
all six were released in 2021 or later, after the primary cutoff. There is no
ZNF410 ChIP-seq experiment at all, which is the one that would have mattered:
binding of ZNF410 at the CHD4 promoter is the pre-cutoff observation from which
the 2020 finding is reachable, and it is not in ENCODE.

Had ENCODE been included, its contribution to every slice used here would have
been zero pre-cutoff rows. The query is recorded above so the claim is
checkable.

### Ontologies not used

MONDO, EFO and ChEBI were not ingested. Disease and trait normalization in this
project is carried by the EFO and MONDO identifiers that Open Targets and the
GWAS Catalog already attach to their own rows, so a separate ontology release
would have added a source to license and hash without changing any output.
ChEBI applies to compound conditions on screens, and no screen in scope carries
a compound condition that any axiom reads.

## Snapshot

`data/snapshot/` holds the normalized graph rows as gzipped JSON Lines, with
`manifest.json` recording a SHA-256 for each file and the counts. The files are
written with a fixed gzip timestamp and no stored filename, so the same rows
produce the same bytes and the hash is a real check rather than a formality.
`hindcast verify` checks the hashes, and `tests/test_redistribution.py` checks
both the hashes and the field names.
