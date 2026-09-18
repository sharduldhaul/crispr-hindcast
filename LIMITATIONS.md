# Limitations

Written plainly. Where a limitation weakens the central claim, that is said
rather than softened.

## The answer key is the published record

The forecast is graded against what was published after the cutoff, so the key
inherits every bias the literature has. A gene that raises HbF but that nobody
wrote a paper about is scored as a wrong forecast. A gene that got a paper
because a large lab was already working on it is scored as a right one. The
benchmark measures agreement with what the field went on to publish, which is
not the same as agreement with what is true.

## Absence of a post-cutoff finding does not make a forecast wrong

If the system ranks a gene highly and no later paper establishes it, the
scorecard counts that as a miss. It is not a miss. It is unconfirmed. The
precision figures should be read as a lower bound on correctness, and the gap
between them and the truth cannot be measured from inside this benchmark.

## The establishment dates come from a blunt rule over titles

A gene's HbF role is dated by the first primary article whose title names the
gene, a regulatory verb and an HbF or globin term. Titles only, because article
text cannot be redistributed and a human reading of full texts would not be
reproducible.

The rule is wrong at the edges and two of its failure modes were found during
the build and fixed before freezing. Greek-letter typography hid both the 2012
and 2013 CHD4 papers, whose titles name the protein as Mi2β, and the rule dated
CHD4 to 2019 until the matcher folded Greek letters. The absence of negation
handling credited MBD3 with an establishing record from the paper titled
"Disruption of the MBD2-NuRD complex but not MBD3-NuRD induces high fetal
hemoglobin", which is the paper that ruled MBD3 out.

Two failure modes remain and are not fixed:

*   A title that asserts a role the article did not establish will date a gene
    too early. Reviews and commentaries are filtered by title pattern and by
    publication type, which catches many and not all.
*   A paper that established a role without saying so in its title dates the
    gene too late, or not at all. NFIX is the clearest case in scope. The 2022
    article "Dual function NFI factors control fetal hemoglobin silencing in
    adult erythroid cells" names the family and not the gene, so the rule dates
    NFIX from a 2023 paper instead. Both are after every cutoff used here, so the
    classification is unaffected, but the date is wrong.

Every entry in `eval/rulebook/gene_establishment.json` carries its PMID and
title, and the candidates the rule rejected are written out beside it, so any
reader can check a call without rerunning anything.

## Three slices in one disease area is a first measurement

This is not a benchmark yet. It is three cutoffs in one phenotype family, with a
candidate set of 66 genes and a post-cutoff answer key of roughly fifteen genes
at the primary cutoff. The ranking metrics are computed over small numbers and
move a lot when one gene moves. Precision at 5 changes by 0.2 for a single
position change. Nothing here should be read as an estimate of how a system
would do on a different disease, a different phenotype, or a different decade.

## Temporal holdout reduces contamination without eliminating it

The slice is enforced at the data layer and the leak tests attempt each route,
so no post-cutoff row reaches the reasoning through this repository. That is the
part this project controls.

It does not control what a model already knows. If a language model were placed
in this pipeline, it would have read the 2018 HRI paper during training, and no
data-layer enforcement can remove that. This particular system contains no
language model, so the specific contamination channel is absent here, but the
general point stands for anyone extending it: a temporal holdout controls the
evidence and not the reader.

There is also a subtler channel that this project does control and that is worth
naming because it is easy to miss. If gene nodes were created only for genes the
corpus mentions, the presence of a node would itself carry post-cutoff
information: a node for EIF2AK1 in a 2017 slice would hand over the answer.
Gene nodes are therefore built from the full HGNC release and dated by HGNC
approval date, so presence reflects the gene universe and a symbol coined after
the cutoff is absent. `tests/test_slice_leak.py` checks this.

A third channel is the author's own knowledge. The scope gene list, the
phenotype vocabulary and the weighting coefficients were written by someone who
knows what was found after 2017. Two places where that shows are stated
explicitly: the ordering of checks in the cost lens was chosen with BCL11A's
approved therapy in view, and EIF2AK1 is in the scope list because the question
about it must be askable, not because pre-2017 evidence pointed at it. The
weighting coefficients were frozen and tagged before the first evaluation run,
which is evidence about timing, not about the author's mind.

## BioGRID ORCS has no HbF screens, which constrains the whole evaluation

This is the largest practical limitation and it was discovered during the build.
The human ORCS release contains no fetal hemoglobin screen. The screens that
produced the field's key HbF results, including the domain-focused CRISPR screen
that identified HRI, are not curated there, and their supplementary tables are
not open, redistributable, dated data.

So the pre-cutoff evidence base in this repository is not the screen record. It
is genetic association evidence from the GWAS Catalog, essentiality and fitness
evidence from dated ORCS screens, target-disease evidence from Open Targets, and
dated bibliographic metadata from Europe PMC. That is a thinner base than the
project description implies, and the forecast rests more heavily on human
genetics and on literature structure than on functional screen data.

A reader should weigh the results accordingly. The benchmark measures what an
honest system could conclude from the open, redistributable, dated record. It
does not measure what a system could conclude from all the evidence that existed
before the cutoff, because much of that evidence is in supplementary tables that
cannot be committed here.

## The model comparison row was not run

The ablation table's last row, a general model given the same prompt and no
graph, is the row that answers whether the structure earns its place against a
model's own knowledge. It is reported as not run.

The reason is hard rule 4: a clone must reproduce the scorecard offline with no
API keys, so the pipeline makes no live model calls and there are no cached
responses committed. The prompt is committed, the cache format is documented in
`eval/model_cache/README.md`, and anyone with a key can populate it and have the
row replay offline afterwards.

What is reported instead is a no-graph baseline that ranks genes by pre-cutoff
publication count. That answers a narrower question, whether the structure beats
counting papers, and it does not answer whether the structure beats a model that
has read the literature.

## The cost lens is a stated policy, not a measurement

The route weights, 10.0 for a small molecule down to 0.0 for mechanistic
insight, are an ordering chosen to make a point about where value lies. They are
not prices and not predictions of prices. Casgevy at about $2.2M and Lyfgenia at
about $3.1M are real list prices and are the anchors, but the ratio between the
small-molecule weight and the multi-edit weight is a judgement.

The modality inference is also coarse. It reads the HGNC protein family and asks
whether the effect runs through a cis-regulatory element. A kinase is called
small-molecule tractable because kinases have a track record of oral inhibitors,
which says nothing about whether a selective inhibitor of this kinase can be
made. A reader should treat the cost ranking as a way of surfacing cheap routes
for attention, not as a claim that any of them will work.

## Calibration is measured on few points

The expected calibration error is computed over the claims the system put a
confidence on at each cutoff, which is tens of points spread over five bins.
Several bins hold very few claims or none. An ECE computed this way is a
description of this run rather than an estimate of the system's calibration, and
the reliability diagram should be read with the bin counts visible, which is why
the scorecard reports them.

## What the store does not model

The graph has no concept of effect size comparability across assays. A
measurement's value is stored with its assay and its meaning, and the weighting
function reads how it was produced, but nothing converts an ORCS screen score
and a GWAS negative log p-value onto a common scale, because they are not
comparable and pretending otherwise would be the sort of invented number this
project forbids. The consequence is that belief revision uses the direction and
the method weight of each measurement, and not its magnitude. A gene with a
large effect and a gene with a small but real effect, measured the same way,
move a claim by the same amount.

## The two headline findings were not recovered

EIF2AK1 and ZNF410 are the two post-2017 results this benchmark was built
around, and the system refuses both.

After the title rule is applied, EIF2AK1 has two pre-2018 publications naming it
with fetal hemoglobin, and ZNF410 has none. Neither has a functional measurement
in any ingested source. Both sit at the prior or just above it, and both are
refused for want of evidence of substance.

The refusal is correct on the evidence available, and it is also a missed
forecast. Those are not in tension: the system is right that the pre-2018 record
it can see does not support a claim, and the field nonetheless found the answer
within three years. Both facts are reported. EIF2AK1 and ZNF410 appear in the
scorecard as passed contamination checks and as absent from the forecast, and
neither entry is suppressed in favour of the other.

What would have been needed to reach them is worth stating, because it says what
the benchmark is actually measuring. ZNF410 acts through CHD4, and the pre-2018
evidence for that link is ChIP-seq occupancy at the CHD4 promoter, which lives
in ENCODE. ENCODE was excluded from this build on relevance grounds, with the
query and counts recorded in DATA_SOURCES.md, and that exclusion is the reason
the link is unreachable here. EIF2AK1 requires connecting heme-regulated
translational control to gamma-globin output, which no ingested source states.

## Two correct answers sit just below the refusal threshold

LIN28B and HDAC2 both reach confidence 0.240 at the 2017 cutoff, on exactly five
HbF-specific publications each, against a frozen refusal threshold of 0.25. A
threshold of 0.24 would have forecast both, taking the forecast from two items
to four and roughly tripling P@5.

The threshold was committed and tagged before the run and has not been moved.
This is the most concrete illustration in the repository of what freezing a
policy costs, and of why the tag is worth having: a reader has no way to
distinguish a threshold chosen for good reasons from one chosen because it
worked, except by the order of the commits.

It also means the reported precision is sensitive to a threshold sitting
accidentally close to a cluster of claims. Two genes at 0.240 and a threshold at
0.25 is not a robust measurement, and the number should be read as one draw
rather than as the system's accuracy.

## The composition route never fires at the primary slice

`ACTS_THROUGH` is derived and present in the graph: 180 edges over 90 gene pairs
that HGNC curates into the same protein complex. It produces zero axioms at the
2017 cutoff.

The reason is the data. The composition rule requires the partner's support to
be a measurement, and every HbF-family measurement in that slice is a genetic
association at the globin locus, at BCL11A, at MYB or at HBS1L. None of those
genes shares a curated protein complex with another gene in scope, so there is
no partner to transfer from. The NuRD subunits, which do share a complex, are
supported in the pre-2018 record only by literature.

Five of the thirteen ground-truth genes at that slice are NuRD subunits: MBD2,
MTA2, GATAD2A, RBBP4 and HDAC2. A rule that admitted literature-established
partners would have reached several of them. That rule was not adopted, because
it would have been adopted after seeing the answer key, and because there is no
defensible coefficient for transferring a co-mention count along a complex edge.
The consequence is that the system's only composition step is inert here, and
the forecast rests almost entirely on the literature route.

## Two ablations change nothing

Removing the method signature and removing ontology normalization leave the
forecast, both rankings, the traps and the refusals identical at every slice.
ECE moves by less than 0.002.

This is an honest negative result about this evidence base rather than about the
ideas. The method signature weights measurements, and the pre-2018 slice
contains thirty HbF-family measurements, all of them genetic associations of
similar standing. There is nothing for it to discriminate between. Ontology
normalization matters for ingestion correctness, which the exclusion counts
reflect, but the genes that survive normalization are the same genes either way.

Anyone reading the ablation table should take from it that belief revision and
the graph carry the result here, and that two of the five components are
unevidenced by this experiment in either direction.

## Held-out recovery is close to vacuous

The held-out test hides a gene's measurement rows inside the pre-cutoff window
and asks whether the gene is still reportable. It reports recovery of 1 of 1 at
the 2014 and 2017 cutoffs and 5 of 5 at 2020.

A rate of 1.00 over a single gene is not evidence of anything. Only BCL11A
clears reportability on measurement evidence alone in the early windows, so the
denominator is one by construction. The test also hides measurements and not
publications, so for most genes the confidence with and without their rows is
identical, and the test is measuring nothing for them.

One side effect is worth recording because it shows the sign conventions are
working. Hiding CHD4's measurements at the 2017 cutoff *raises* its confidence,
from 0.098 to 0.240, because its measurements are fitness hits and therefore
evidence against it as a target. That is correct behaviour and it is also a sign
that the recovery rate is not measuring what its name suggests.

## Four genes have a truncated erythroid literature tier

The Europe PMC fetch caps retrieval per query. Four genes exceeded the cap on
the erythroid tier: HBB, TET2, NFE2 and MAPK1. Their erythroid counts are
floors, not totals, and `data/raw/europepmc/coverage.json` records the hit count
alongside the retrieved count for every gene so the shortfall is visible.

No gene was truncated on the HbF tier, which is the tier that drives
reportability, so the effect on the forecast is limited to the quarter-weight
erythroid increments. The published counts for those four genes should still be
read as lower bounds.
