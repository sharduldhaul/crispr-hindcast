# Data sources

Every source used, with its license and required attribution, and every source
considered and excluded, with the reason. All were accessed on **2026-09-17**.

The repository's code is MIT licensed. Each dataset keeps its own license.

## What is committed

Identifiers, structured metadata, numeric measurements and publication titles.
No abstracts and no article text: per-article licenses vary and many do not
permit redistribution. Where the pipeline needs article text it stores the PMID
and a fetch script, and caches the text in a gitignored directory.
`tests/test_redistribution.py` scans `data/snapshot/` for fields that would
mean article text is present and fails the build if it finds any.

## Included

| Source | Institution | License | Used for |
| --- | --- | --- | --- |
| [BioGRID ORCS](https://orcs.thebiogrid.org/) 2.0.18, human set | BioGRID, TyersLab, Mount Sinai Hospital and University of Montreal | MIT | CRISPR screen metadata, per-gene screen scores, PMIDs |
| [DepMap](https://depmap.org/portal/) 24Q4 Public | Broad Institute | CC BY 4.0 | Gene-effect values per cell line, for the pan-essentiality trap |
| [Open Targets Platform](https://platform.opentargets.org/) | Open Targets, EMBL-EBI and partners | CC0 1.0 | Target-disease evidence for sickle cell disease and beta-thalassemia, and the DepMap values |
| [NHGRI-EBI GWAS Catalog](https://www.ebi.ac.uk/gwas/) | EMBL-EBI and NHGRI | EMBL-EBI terms of use: no restriction; attribution and citation of the originating studies required | Human genetic association evidence for the HbF trait family |
| [Europe PMC](https://europepmc.org/) | EMBL-EBI | Bibliographic metadata; per-article licenses vary | Publication metadata and the resolved publication date the time slice turns on |
| [ClinicalTrials.gov](https://clinicaltrials.gov/) | US National Library of Medicine | Public domain, US Government work | Registered trials, which anchor the cost lens in what has been built |
| [HGNC](https://www.genenames.org/) | HUGO Gene Nomenclature Committee, EMBL-EBI | CC0 1.0 | Gene identity, aliases, withdrawn symbols, protein family, and the approval date that dates every gene node |
| [Cellosaurus](https://www.cellosaurus.org/) | SIB Swiss Institute of Bioinformatics | CC BY 4.0 | Cell line identity and category, a term in the weighting function |

## Attributions

Written out in full, as each license asks. Open Targets, ClinicalTrials.gov and
HGNC require none and are attributed anyway.

> CRISPR screen data from BioGRID ORCS (Open Repository of CRISPR Screens),
> https://orcs.thebiogrid.org/. BioGRID is distributed under the MIT License.

> DepMap, Broad (2024). DepMap 24Q4 Public. Figshare+. Dataset.
> https://doi.org/10.25452/figshare.plus.27993248.v1. Licensed CC BY 4.0.

> Target-disease evidence from the Open Targets Platform,
> https://platform.opentargets.org/, released under CC0 1.0.

> Genetic association data from the NHGRI-EBI GWAS Catalog,
> https://www.ebi.ac.uk/gwas/. EMBL-EBI data are available without restriction
> under its terms of use, which require attribution and citation of the
> originating studies. Study accessions and PubMed IDs are recorded on every
> association row in this repository.

> Publication metadata and resolved publication dates from Europe PMC,
> https://europepmc.org/.

> Trial records from ClinicalTrials.gov, US National Library of Medicine.

> Gene symbols, identifiers and approval dates from the HUGO Gene Nomenclature
> Committee, https://www.genenames.org/, released under CC0.

> Cell line identifiers and metadata from Cellosaurus,
> https://www.cellosaurus.org/, SIB Swiss Institute of Bioinformatics, licensed
> CC BY 4.0.

## Notes on three sources

### BioGRID ORCS

Bulk file SHA-256:
`39222a9650eed083edf193debe45eedc4aabc779ca04ea70107b6bd1efd9b8d7`.

The bulk release ships one hit table per screen and no screen-level index, and
the REST webservice requires a registered access key. The screen-level metadata
this project needs (PMID, cell line with Cellosaurus accession, perturbation
type and the stated significance rule) is on the public screen pages, and
`scripts/fetch_orcs.py` reads it from there.

The human release contains no fetal hemoglobin screen. Of 1,952 human screens,
none names fetal hemoglobin, gamma globin or F-cells in its phenotype,
rationale, notes, title or condition, and none is in an HUDEP-2 or CD34+
system. 138 are in K-562. ORCS therefore contributes fitness and proliferation
evidence, which the pan-essentiality trap depends on, and no direct HbF
measurement.
[LIMITATIONS.md](LIMITATIONS.md#biogrid-orcs-has-no-hbf-screens) states what
that costs.

### DepMap

The license was confirmed through the figshare API for the release record,
which returns `CC BY 4.0` with the citation above. The DepMap portal's terms of
use add conditions on portal use that the figshare release does not, so the
figshare release is treated as the licensing record and is what is cited.

Gene-effect values reach this project through the Open Targets Platform, which
redistributes them. Both are attributed. These rows carry the DepMap release
date, the only date the source supports, so they fall after every evaluation
cutoff and no slice can see them. They are ground truth for the adversary and
the grader. Pre-cutoff essentiality evidence comes from the dated BioGRID ORCS
screens.

### Europe PMC

Only identifiers, dates, journal names, author strings and titles are
committed. This is the source the rule under
[What is committed](#what-is-committed) was written for.

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
a public MIT-licensed repository, so the source is not ingested. Essentiality
evidence comes from BioGRID ORCS and from DepMap instead, and the loss is that
European cell line coverage is thinner than it would otherwise be.

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

Had ENCODE been included, it would have contributed no row dated before the
primary cutoff.

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
produce the same bytes and the hash is a real check.
`hindcast verify` checks the hashes, and `tests/test_redistribution.py` checks
both the hashes and the field names.
