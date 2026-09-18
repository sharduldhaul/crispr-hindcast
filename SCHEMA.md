# Schema

Two decisions were made in the first hour of the build and are recorded here with
their reasons. Neither is abstracted over an alternative.

## Storage: SQLite

SQLite, with recursive CTEs for path queries. Not Neo4j.

The reason is hard rule 4, deterministic replay. Someone cloning this repo in
2027 must reproduce the exact scorecard offline, with no API keys, no network
and no running services. A Neo4j container adds a service to start, a version of
the server and of its query planner to pin, and an import step whose output is
not byte-reproducible. SQLite is a file. The file can be rebuilt from the
committed snapshot by one command, hashed, and compared.

The second reason is hard rule 2, the time slice enforced at the data layer.
The enforcement used here materializes a separate database holding only the rows
visible at T, then hands out a read-only connection to it with an authorizer
that denies `ATTACH`. Post-T rows are not merely filtered out of queries, they
are absent from every database the connection can reach. That construction is
possible because SQLite databases are files that can be built, detached and
reopened under restriction. It has no clean equivalent in a shared server.

The graph is small: tens of thousands of nodes. Recursive CTEs are adequate at
this size, and the traversals this project needs are shallow, mostly
gene to measurement to screen to publication.

## One node table, one edge table

Nodes live in a single `node` table with a `type` column and a JSON `attrs`
column. Edges live in a single `edge` table the same way.

The reason is the time slice again. Every node and every edge carries the same
`effective_date` column in the same place, so the slice filter is one predicate
applied once, in one function, rather than a predicate per table that a later
contributor could forget on the eleventh table. Typed access is recovered above
the storage layer by the Pydantic models in `hindcast.models`, which validate
per-type attributes on the way in and on the way out. The database enforces
provenance and time. Python enforces shape.

## Node types

Exactly these ten. Adding one requires a reason written into this file.

| Type | What one row is | Why it is separate |
| --- | --- | --- |
| `Gene` | A human gene, keyed by HGNC ID | The stable identity that screen hits, genetic associations and claims all attach to. Symbols change, so the HGNC ID is the key and symbols are aliases. |
| `Perturbation` | A way of altering a gene, for example CRISPR knockout, CRISPRi, base edit | Evidential weight depends on how a gene was perturbed, not only on which gene. Separating this from `Screen` lets one screen carry one perturbation class and lets the weighting function read it directly. |
| `Screen` | One CRISPR screen, keyed by BioGRID ORCS screen ID | The unit of experiment that ORCS publishes and that a PMID attaches to. A publication can report several screens, so this cannot be folded into `Publication`. |
| `CellContext` | A cell system, keyed by Cellosaurus accession where one exists | The single largest term in the weighting function. Primary human CD34+ cells and an immortalized line are not interchangeable evidence, so the system has to be a first-class node that weights can key on. |
| `Phenotype` | A measured trait, for example HbF protein level, F-cell percentage, HBG mRNA | Readout directness is a weighting term. Keeping phenotype separate from measurement lets many measurements of differing directness point at one trait family. |
| `Measurement` | One number, for one gene, in one screen or dataset, against one phenotype | This is the row that hard rule 1 refers to. Every quantitative claim in every output traces to a `Measurement` ID. Nothing else in the schema holds a number that an output may quote. |
| `Publication` | One article, keyed by PMID | Carries the date that the whole time slice turns on, and the license that governs whether its text may be redistributed. |
| `Claim` | A proposition about a gene, phenotype and direction that evidence can move | The object belief revision acts on. Claims are generated from evidence and vocabulary, never free-written, and their confidence history is the audit log. |
| `Modality` | A therapeutic route with a cost class, for example small molecule, ex vivo multi-edit | The cost lens. Separate from `Claim` because one modality is implied by many claims, and because the cost class is frozen project vocabulary rather than evidence. |
| `Trial` | One registered clinical study, keyed by NCT ID | Clinical outcome evidence, which the weighting function treats differently from preclinical evidence and which anchors the cost lens in what has actually been built. |

## Edge types

Exactly these nine.

| Type | From to | Why it is separate |
| --- | --- | --- |
| `SCREEN_TESTED` | `Screen` to `Gene` | Records that a gene was in the library and could have been found. Absence of a hit only means something if the gene was tested, so this edge is what makes a negative result readable. |
| `PERTURBS` | `Perturbation` to `Gene` | Ties the perturbation class to the gene, so the weighting function can ask how a gene was altered without walking through the screen. |
| `MEASURED_IN` | `Measurement` to `CellContext` | The system a number came from. Carries the largest weight term. |
| `REPORTS` | `Publication` to `Screen`, `Measurement` or `Trial` | Provenance, and the path by which a date and a license reach a number. |
| `SUPPORTS` | `Measurement` or `Claim` to `Claim` | A confidence increase. Weighted by method signature, never unweighted. |
| `CONTRADICTS` | `Measurement` or `Claim` to `Claim` | A confidence decrease. Kept distinct from a negative-weight `SUPPORTS` so that contested claims can be found by edge type alone, which is what the frontend renders as unsettled. |
| `SUPERSEDES` | `Claim` to `Claim` | A later claim replacing an earlier one, for example a mechanism refined from "acts on HbF" to "acts solely through CHD4". Distinct from `CONTRADICTS` because the earlier claim was not wrong, it was coarse. |
| `IMPLIES_MODALITY` | `Claim` to `Modality` | The cost lens. Separate edge because one claim can imply more than one route at different confidences. |
| `ACTS_THROUGH` | `Gene` to `Gene` | Mechanistic dependency, for example ZNF410 acting through CHD4. This is the edge the primary evaluation is trying to forecast, so it is explicit rather than encoded in claim text. |

### Which edge types actually carry rows

The nine types above are the schema. Five of them are populated by the current
build, and saying which is more useful than leaving a reader to assume all nine
are:

| Edge type | Rows | Producer |
| --- | --- | --- |
| `REPORTS` | 58,823 | A publication reporting a screen or a measurement |
| `PERTURBS` | 57,514 | A perturbation applied to a gene in a screen |
| `MEASURED_IN` | 57,514 | A measurement made in a cell context |
| `SCREEN_TESTED` | 57,484 | A screen that tested a gene, including where it found nothing |
| `IMPLIES_MODALITY` | 236 | The cost lens, from a claim to a route |
| `ACTS_THROUGH` | 180 | HGNC gene groups whose name ends "complex subunits" |
| `SUPPORTS` | 0 | No producer. Support is carried as belief revision entries. |
| `CONTRADICTS` | 0 | No producer. |
| `SUPERSEDES` | 0 | No producer. |

`SUPPORTS` has no rows because support is recorded in the append-only
`belief_revision` table instead, where each entry carries the evidence
identifier, the prior and posterior log-odds, the weight applied and the
rationale. That is strictly more information than an edge would hold, and
duplicating it as edges would create two places where the same fact could
disagree. The edge type is kept in the vocabulary because the frontend needs to
draw the relation and because a future build that materialises it should not
have to change the schema.

`CONTRADICTS` and `SUPERSEDES` have no rows because nothing in the ingested
sources states a contradiction or a refinement in machine-readable form.
Detecting either from titles would require asserting that one paper refutes
another, which the title rule cannot support. Both remain specified, and
METHODOLOGY.md states how belief revision would treat them, but no row is
invented to fill them.

`SCREEN_TESTED` is the one that records negative evidence: a screen that tested
a gene and found nothing still produces an edge, so absence of a hit is
distinguishable from absence of a test.

## Provenance columns, on every row of both tables

| Column | Rule |
| --- | --- |
| `source_id` | Dataset name plus that dataset's own record key. Never generated. |
| `accession` | The source's stable public identifier, where one exists. |
| `pmid` | PubMed ID, where the row descends from an article. |
| `publication_date` | Resolved date, preferring first online publication. See below. |
| `publication_date_online` | First online date as reported by Europe PMC. |
| `publication_date_issue` | Issue date as reported by Europe PMC. |
| `license` | The license of the source this row came from. Not nullable. A row with no license cannot be loaded, which is what makes the redistribution test enforceable. |
| `ingest_hash` | SHA-256 over the normalized source record. Changes if the upstream record changes. |
| `effective_date` | The one column the time slice filters on. See below. |
| `time_scope` | `DATED`, `REFERENCE` or `VOCABULARY`. See below. |

## effective_date and time_scope

The slice filters one column, `effective_date`, on every node and every edge.
What fills that column depends on `time_scope`.

`DATED` rows are evidence: measurements, screens, publications, trials, and the
edges between them. Their `effective_date` is the resolved publication date.
These are the rows the slice hides.

`REFERENCE` rows are ontology entities: genes from HGNC, cell lines from
Cellosaurus, diseases from MONDO. Their `effective_date` is the date the
ontology approved the term, for genes the HGNC `date_approved_reserved`.

Filtering reference rows by approval date closes a leak that is easy to miss. If
gene nodes were created only for genes that some article in the corpus mentions,
then the presence of a gene node would itself carry post-T information. A node
for EIF2AK1 appearing in a 2017 slice would hand the system the answer to the
primary evaluation. Two things prevent that. Gene nodes are drawn from the full
HGNC release rather than from the corpus, so presence reflects the gene
universe and not the evidence. And they are filtered by HGNC approval date, so a
symbol coined after T is absent.

`VOCABULARY` rows are this project's own frozen terms: the phenotype families
and the modality cost classes. They are committed to the repository and tagged
before the first evaluation run, so they predate every slice. Their
`effective_date` is `0001-01-01`, which makes the uniform filter pass them.

A row whose `effective_date` cannot be resolved is not loaded. It is written to
the exclusions table with a reason and reported in the scorecard, per the
ingestion metric. It is never given a guessed date.

## Date resolution rule

`publication_date` is resolved from Europe PMC, preferring `firstPublicationDate`
over the journal issue date, because the field's knowledge of a result begins
when the result becomes readable, not when the issue was bound. Both dates are
stored. Where the two disagree the online date is earlier, so this choice makes
the slice strictly more conservative: an article is visible to the forecast from
the earliest date on which anyone could have read it.

Preprints are treated as publications with their own date. Where a preprint and
its journal version are both in the corpus, the preprint's PMID carries the
earlier date and the journal version is linked by `SUPERSEDES`.
