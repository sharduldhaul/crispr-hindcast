# Limitations

Where a limitation weakens the central claim, that is said rather than
softened.

| Limit | What it means for the results |
| --- | --- |
| [The answer key](#the-answer-key) is the published record, dated by a rule over titles | Precision is agreement with what the field published, and a lower bound on correctness |
| [The evidence](#the-evidence) is the open, redistributable, dated record | No HbF screen data; the forecast rests on human genetics and literature counts |
| [The time split](#the-time-split) controls the evidence, not the reader | A model's training knowledge and the author's hindsight are outside it |
| [The language-model track](#the-language-model-track) is one sample from one model | Recall is measured as a lower bound, and nothing generalizes to another model |
| [The measurement](#the-measurement) is three cutoffs in one disease area | Wide intervals; one gene moves a metric by 0.2 |
| [The results](#the-results) include misses and components that did nothing | Both headline findings were refused; two ablations change nothing |

## The answer key

### It is the published record

The forecast is graded against what was published after the cutoff, so the key
inherits every bias the literature has. A gene that raises HbF but that nobody
wrote a paper about is scored as a wrong forecast. A gene that got a paper
because a large lab was already working on it is scored as a right one. The
benchmark measures agreement with what the field went on to publish, which is
not the same as agreement with what is true.

### An unconfirmed forecast is counted as a miss

If the system ranks a gene highly and no later paper establishes it, the
scorecard counts a miss. The forecast is unconfirmed, not wrong. The precision
figures are a lower bound on correctness, and the gap between them and the
truth cannot be measured from inside this benchmark.

### The establishment dates come from a blunt rule over titles

A gene's HbF role is dated by the first primary article whose title names the
gene, a regulatory verb and an HbF or globin term. Titles only, because article
text cannot be redistributed and a human reading of full texts would not be
reproducible.

Two failure modes were found during the build and fixed before freezing:

- **Greek letters.** The 2012 and 2013 CHD4 papers name the protein as Mi2β,
  and the rule dated CHD4 to 2019 until the matcher folded Greek letters.
- **Negation.** The rule credited MBD3 with an establishing record from
  "Disruption of the MBD2-NuRD complex but not MBD3-NuRD induces high fetal
  hemoglobin", the paper that ruled MBD3 out.

Two remain:

- **Dated too early.** A title can assert a role the article did not
  establish. Reviews and commentaries are filtered by title pattern and by
  publication type, which catches many and not all.
- **Dated too late, or not at all.** A paper can establish a role without
  saying so in its title. NFIX is the clearest case in scope: the 2022 article
  "Dual function NFI factors control fetal hemoglobin silencing in adult
  erythroid cells" names the family and not the gene, so the rule dates NFIX
  from a 2023 paper. Both are after every cutoff used here, so the
  classification is unaffected, but the date is wrong.

Every entry in `eval/rulebook/gene_establishment.json` carries its PMID and
title, and the candidates the rule rejected are written out beside it, so a
reader can check a call without rerunning anything.

## The evidence

### BioGRID ORCS has no HbF screens

This is the largest practical limitation, and it was found during the build.
The human ORCS release contains no fetal hemoglobin screen. The screens that
produced the field's key HbF results, including the domain-focused CRISPR screen
that identified HRI, are not curated there, and their supplementary tables are
not open, redistributable, dated data.

So the pre-cutoff evidence base is genetic association evidence from the GWAS
Catalog, essentiality and fitness evidence from dated ORCS screens,
target-disease evidence from Open Targets, and dated bibliographic metadata
from Europe PMC. That is a thinner base than the project description implies,
and the forecast rests more on human genetics and on literature structure than
on functional screen data.

The benchmark measures what a system could conclude from the open,
redistributable, dated record. It does not measure what a system could conclude
from all the evidence that existed before the cutoff, because much of that
evidence is in supplementary tables that cannot be committed here.

### Effect sizes are not compared across assays

A measurement's value is stored with its assay and its meaning, and the
weighting function reads how it was produced. Nothing converts an ORCS screen
score and a GWAS negative log p-value onto a common scale, because they are not
comparable, and a conversion would be an invented number. Belief revision
therefore uses the direction and the method weight of each measurement, not its
magnitude. A gene with a large effect and a gene with a small but real effect,
measured the same way, move a claim by the same amount.

### Four genes have a truncated erythroid literature tier

The Europe PMC fetch caps retrieval per query. HBB, TET2, NFE2 and MAPK1
exceeded the cap on the erythroid tier, so their erythroid counts are floors,
not totals. `data/raw/europepmc/coverage.json` records the hit count beside the
retrieved count for every gene.

No gene was truncated on the HbF tier, which drives reportability, so the
effect on the forecast is limited to the quarter-weight erythroid increments.

## The time split

The slice is enforced at the data layer and the leak tests attempt each route,
so no post-cutoff row reaches the reasoning through this repository. Three
channels remain, one of them closed.

- **What a model already knows: open.** A language model has read the 2018 HRI
  paper during training, and no data-layer enforcement can remove that. The
  rule-based system contains no language model, so this channel is absent from
  its rows. It is present in every row of the language-model track
  (`src/hindcast/llm/`), whose prompt asks the model to disregard what it
  recalls from after the cutoff and cannot verify that it did.
- **The presence of a gene node: closed.** If gene nodes were created only for
  genes the corpus mentions, a node for EIF2AK1 in a 2017 slice would hand over
  the answer. Gene nodes are built from the full HGNC release and dated by HGNC
  approval date, so presence reflects the gene universe and a symbol coined
  after the cutoff is absent. `tests/test_slice_leak.py` checks this.
- **The author's own knowledge: open.** The scope gene list, the phenotype
  vocabulary and the weighting coefficients were written by someone who knows
  what was found after 2017. Two places where that shows: the ordering of
  checks in the cost lens was chosen with BCL11A's approved therapy in view,
  and EIF2AK1 is in the scope list because the question about it must be
  askable, not because pre-2017 evidence pointed at it. The coefficients were
  frozen and tagged before the first evaluation run, which is evidence about
  timing, not about the author's mind.

## The language-model track

### The memorization signal is a lower bound

A claim counts as recalled when its gene was established on or after the cutoff
and the claim is not grounded
([METHODOLOGY.md](METHODOLOGY.md#memorization-signal)). The count misses recall
in four ways.

- **Recall backed by weak pre-cutoff evidence.** A model that remembers a later
  result can cite a pre-cutoff title that names the gene. The claim is grounded
  and is not counted, although the title may say nothing about fetal hemoglobin.
  Grounding checks that a cited row names the gene, not that it supports the
  claim.
- **Recall that sets the confidence.** A grounded claim can carry a confidence
  the cited rows do not justify. The signal is per claim and does not look at
  the number.
- **Recall behind a refusal or a wrong answer.** Only claims for genes in the
  answer key are examined. What the model recalled and chose not to claim, or
  recalled about a gene the rule book does not list as established, is not seen.
- **Recall the answer key cannot date.** A gene the
  [title rule](#the-establishment-dates-come-from-a-blunt-rule-over-titles)
  dates too late moves its claims into the post-cutoff set, and one it dates
  too early removes them.

The grounding check shares the first gap, and it reads only the IDs the model
chose to cite. Evidence the model used and did not cite, and knowledge it
brought from training, are invisible to it.

In the other direction, a recalled claim is not proof of memorization. A model
can reason to a correct gene from general biology and cite nothing. Neither the
`none` condition nor this signal can separate that from recall.

### A model row is one committed sample

Hard rule 4 requires a clone to reproduce the scorecard offline with no API
keys, so the pipeline makes no live call by default, and a row with no response
in `eval/model_cache/` is reported as not run. The scorecard states how many
rows that is. A row is never estimated.

The API is not deterministic, so a second live run of the same request could
return a different answer. The committed response is the result that is
reported, and the bootstrap intervals describe variation over genes, not over
repeated runs of the model.

The flat literature baseline, which ranks genes by pre-cutoff publication
count, is always present. It answers a narrower question: whether the structure
beats counting papers, not whether it beats a model that has read the
literature.

### One model from one provider

Every model row uses one pinned model
([METHODOLOGY.md](METHODOLOGY.md#fixed-parameters)). Nothing here says how
another model, another provider or a later version of the same model would
answer. The training cutoff of the pinned model is later than all three
evaluation cutoffs, so every model row is exposed to recall. The prompts and
the tool definitions were written before this model was chosen, were not tuned
to it, and were not tested on another.

## The measurement

### Three slices in one disease area is a first measurement

This is three cutoffs in one phenotype family, with a candidate set of 66 genes
and a post-cutoff answer key of roughly fifteen genes at the primary cutoff.
The ranking metrics are computed over small numbers: precision at 5 changes by
0.2 for a single position change. Nothing here estimates how a system would do
on a different disease, a different phenotype or a different decade.

The scorecard gives a bootstrap interval over genes for the ranking metrics and
the grounded-claim rate ([METHODOLOGY.md](METHODOLOGY.md#bootstrap-intervals)).
The intervals are wide. A difference between a model row and the rule-based row
that lies inside the intervals is not evidence that one is better. The
grounded-claim rate has the same problem at a smaller size: its denominator is
the claims of one run.

### Calibration is measured on few points

The expected calibration error is computed over the claims the system put a
confidence on at each cutoff: tens of points spread over five bins, several of
which hold very few claims or none. It describes this run and does not estimate
the system's calibration. The scorecard reports the bin counts for that reason.

### The cost lens is a stated policy, not a measurement

The route weights, 10.0 for a small molecule down to 0.0 for mechanistic
insight, are an ordering chosen to make a point about where value lies. They are
not prices and not predictions of prices. Casgevy at about $2.2M and Lyfgenia at
about $3.1M are real list prices and are the anchors, but the ratio between the
small-molecule weight and the multi-edit weight is a judgement.

The modality inference is coarse. It reads the HGNC protein family and asks
whether the effect runs through a cis-regulatory element. A kinase is called
small-molecule tractable because kinases have a track record of oral inhibitors,
which says nothing about whether a selective inhibitor of this kinase can be
made. The cost ranking surfaces cheap routes for attention. It does not claim
that any of them will work.

## The results

### The two headline findings were not recovered

EIF2AK1 and ZNF410 are the two post-2017 results this benchmark was built
around, and the system refuses both.

After the title rule is applied, EIF2AK1 has two pre-2018 publications naming it
with fetal hemoglobin, and ZNF410 has none. Neither has a functional measurement
in any ingested source. Both sit at the prior or just above it.

The refusal is correct on the evidence available, and it is also a missed
forecast: the pre-2018 record the system can see does not support a claim, and
the field found the answer within three years. Both appear in the scorecard as
passed contamination checks and as absent from the forecast.

What would have reached them:

- **ZNF410** acts through CHD4. The pre-2018 evidence for that link is ChIP-seq
  occupancy at the CHD4 promoter, and no such ZNF410 experiment is in ENCODE,
  which was excluded from this build
  ([DATA_SOURCES.md](DATA_SOURCES.md#encode)).
- **EIF2AK1** requires connecting heme-regulated translational control to
  gamma-globin output, which no ingested source states.

### Two correct answers sit just below the refusal threshold

LIN28B and HDAC2 both reach confidence 0.240 at the 2017 cutoff, on exactly five
HbF-specific publications each, against a frozen refusal threshold of 0.25. A
threshold of 0.24 would have forecast both, taking the forecast from two items
to four and roughly tripling P@5.

The threshold was committed and tagged before the run and has not been moved.
A reader can distinguish a threshold chosen for good reasons from one chosen
because it worked only by the order of the commits.

It also means the reported precision is sensitive to a threshold that happens
to sit close to a cluster of claims. The number is one draw, not the system's
accuracy.

### The composition route never fires at the primary slice

`ACTS_THROUGH` is derived and present in the graph: 180 edges over 90 gene pairs
that HGNC curates into the same protein complex. It produces zero axioms at the
2017 cutoff.

The composition rule requires the partner's support to be a measurement, and
every HbF-family measurement in that slice is a genetic association at the
globin locus, at BCL11A, at MYB or at HBS1L. None of those genes shares a
curated protein complex with another gene in scope. The NuRD subunits, which do
share a complex, are supported in the pre-2018 record only by literature.

Five of the thirteen ground-truth genes at that slice are NuRD subunits: MBD2,
MTA2, GATAD2A, RBBP4 and HDAC2. A rule that admitted literature-established
partners would have reached several of them. It was not adopted, because it
would have been adopted after seeing the answer key, and because there is no
defensible coefficient for transferring a co-mention count along a complex edge.
The system's only composition step is inert here, and the forecast rests almost
entirely on the literature route.

### Two ablations change nothing

Removing the method signature and removing ontology normalization leave the
forecast, both rankings, the traps and the refusals identical at every slice.
ECE moves by less than 0.002.

This is a negative result about this evidence base, not about the ideas. The
method signature weights measurements, and the pre-2018 slice contains thirty
HbF-family measurements, all genetic associations of similar standing, so there
is nothing for it to discriminate between. Ontology normalization matters for
ingestion correctness, which the exclusion counts reflect, but the genes that
survive normalization are the same genes either way.

Belief revision and the graph carry the result here. Two of the five components
are unevidenced by this experiment in either direction.

### Held-out recovery is close to vacuous

The held-out test hides a gene's measurement rows inside the pre-cutoff window
and asks whether the gene is still reportable. It reports recovery of 1 of 1 at
the 2014 and 2017 cutoffs and 5 of 5 at 2020.

A rate of 1.00 over a single gene is not evidence of anything. Only BCL11A
clears reportability on measurement evidence alone in the early windows, so the
denominator is one by construction. The test also hides measurements and not
publications, so for most genes the confidence with and without their rows is
identical.

Hiding CHD4's measurements at the 2017 cutoff *raises* its confidence, from
0.098 to 0.240, because its measurements are fitness hits and therefore
evidence against it as a target. The sign conventions are working, and the
recovery rate is not measuring what its name suggests.
