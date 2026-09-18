# Methodology

Two things in this system assign numbers that are not measurements: the method
signature, which decides how much a measurement is worth, and the belief
reviser, which decides how much a measurement moves a claim. Both are stated
policies. Neither is fitted to anything. This file gives the reason for every
coefficient.

Both were frozen before the first evaluation run and committed under a git tag.
The commit timestamp is the evidence that they were not tuned against the
answers. Where a choice was made for a reason that involved looking at a known
case, that is said so explicitly below rather than hidden.

## Method signature

The module is `src/hindcast/agents/method_signature.py`. It reads how a
measurement was produced and returns a weight. It never reads what the
measurement concluded. Two screens run identically in the same system, one
finding a strong effect and one finding nothing, receive the same weight.

Five terms, combined multiplicatively and then clamped.

### Why multiplicative

These are not independent contributions that add up. A direct HbF protein
readout, measured in a cell line that does not perform the fetal-to-adult
globin switch, is not worth the sum of its parts. A weak system has to discount
everything measured in it, and multiplication is what does that. Under addition,
a perfect readout would partly rescue a meaningless system, which is the error
this term exists to prevent.

### Term 1: the system

| System | Weight |
| --- | --- |
| Human population, meaning a genetic association measured in people | 1.00 |
| Primary human CD34+ HSPCs, erythroid differentiated | 1.00 |
| Human erythroid progenitor line, HUDEP-2 class | 0.75 |
| Human cancer line, K-562 class | 0.35 |
| Human immortalized line, not erythroid | 0.30 |
| Mouse model, in vivo | 0.30 |
| Mouse cell line | 0.20 |
| Non-human other | 0.10 |
| Cell-free, or the source does not say | 0.10 |

This is the largest term and the one most often glossed over when screen
results are compared across papers.

Primary human CD34+ cells differentiated down the erythroid pathway perform the
fetal-to-adult switch that the disease is about. HUDEP-2 is an immortalized
human erythroid progenitor line that also performs the switch, so it sits close
behind. K-562 is an erythroleukemia line that expresses fetal and embryonic
globins and never silences them. A result showing more HbF in K-562 may
therefore be showing nothing about silencing at all, which is why the gap
between 0.75 and 0.35 is the largest in the table.

A mouse carries a different globin locus with a different developmental switch.
The cases where mouse and human globin regulation disagree are the reason this
term dominates the others.

Human population is placed at the top, level with primary human cells, because
a genetic association is measured in the only system that has to work. It is
not placed above them, because an association identifies a locus rather than a
mechanism, and the penalty for an unresolved causal gene is applied separately.

### Term 2: the perturbation

| Perturbation | Weight |
| --- | --- |
| Base edit, or knock-in of a defined allele | 1.00 |
| Naturally occurring human genetic variant | 1.00 |
| CRISPRi | 0.85 |
| CRISPRa | 0.70 |
| Nuclease knockout | 0.70 |
| RNAi | 0.40 |
| Overexpression | 0.30 |
| The source does not say | 0.35 |

A defined allele is the strongest perturbation available, because the sequence
change is known and its consequence can be reasoned about. A natural human
variant is equally strong for a different reason: it is the experiment that has
already been run at population scale, in the right species, without a vector.

CRISPRi represses transcription without cutting, so it avoids both the indel
heterogeneity of a pooled knockout and the DNA damage response that a cut
provokes. It is incomplete, which is why it is not at 1.00, but it is cleaner
than a knockout and is placed above it.

Overexpression is weakest. Forcing a factor above its physiological range
routinely produces effects that do not occur at native levels, and the globin
regulation literature contains several findings of that kind that did not hold.

"The source does not say" is set at 0.35, below knockout. An unstated method is
treated as somewhat worse than the most common method, because the cases where
authors do not state it are not a random sample of the cases where they do.

### Term 3: readout directness

| Readout | Weight |
| --- | --- |
| HbF protein, or F-cell percentage | 1.00 |
| HBG1/HBG2 transcript | 0.65 |
| Reporter, sorted population, or other proxy | 0.35 |

The endpoint that matters clinically is HbF protein per red cell and its
distribution across cells, because a given mean HbF protects far better when
spread evenly than when concentrated in a few F-cells.

Transcript is one step removed, and the step is not free. Gamma-globin mRNA and
HbF protein come apart through translational control. That is not a hypothetical
concern here: translational control is the mechanism the EIF2AK1 result turns
on, and a system that treated mRNA and protein as interchangeable would be
blind to the class of finding this benchmark is built around.

### Term 4: independent replication

| Independent laboratories | Multiplier |
| --- | --- |
| 0 or 1 | 1.00 |
| 2 | 1.35 |
| 3 | 1.55 |
| 4 or more | 1.70, capped |

Replication by the same group in the same system is close to free and is not
counted. Replication by an unrelated group is the most informative thing that
can happen to a finding.

The multiplier saturates because the fourth independent replication adds less
than the second. It is capped so that no amount of replication can rescue a
weak system: the cap of 1.70 is smaller than the ratio between the strongest and
weakest system weights, so replication can never promote a mouse cell line
result above a primary human cell result.

### Term 5: human genetic support

| Condition | Multiplier |
| --- | --- |
| Genome-wide significant association to the HbF trait family | 1.30 |
| No such association | 1.00 |
| Gene is the author-reported gene at an associated locus | 0.55 |

The bonus is deliberately smaller than the system term. A genetic association
says that a gene matters. It does not say that a particular cell-line
experiment about that gene was well done.

The penalty is the geometry problem in its statistical form. A GWAS peak names
a region, and the author-reported gene at that region is an assignment made by
the study's authors, not a result. The standing example is in this repository's
own data: the olfactory receptor genes OR51B5 and OR51B6 are reported genes at
an HbF-associated locus with an association p-value of 3e-08, and they have no
plausible role in globin regulation. Without this penalty, a system reading the
GWAS Catalog would rank olfactory receptors as HbF regulators. The adversary
plants exactly that trap, and the penalty is why the system survives it.

### Clamping

The product is clamped to the range 0.01 to 2.00. The floor exists because
nothing in this corpus is worth exactly nothing, and a weight of zero would make
a measurement unable to move any belief even in principle. The ceiling exists so
that no single measurement dominates an accumulation.

The ceiling does bind. A base edit in primary human CD34+ cells with a protein
readout, three independent replications and genetic support computes to 2.015
and is clamped to 2.00. Information is lost there, and it is worth saying so
rather than pretending the range was chosen wide enough.

### Assay standing

A modifier for sources whose rows are not experiments in the usual sense. An
Open Targets text-mined literature co-mention is a statement that two terms
appeared in the same article. It is the weakest evidence in the corpus at 0.25.
An animal model row sits at 0.60. Genetic association, clinical, screen and
gene-effect rows are at 1.00, because their standing is already carried by the
five terms above and applying a second discount would double-count.

## Belief revision

The module is `src/hindcast/agents/belief_reviser.py`. No language model decides
any numeric update. The rule is log-odds accumulation.

Each claim carries a confidence in the open interval 0 to 1, held internally as
log odds. Each piece of evidence contributes

    delta = direction * weight * EVIDENCE_STRENGTH

where `direction` is +1 for support and -1 for contradiction, `weight` is the
method signature weight, and `EVIDENCE_STRENGTH` is a single global constant
converting a unit weight into log-odds. Evidence is applied in publication-date
order, and every application writes an immutable audit row recording the claim,
the prior, the posterior, the triggering record and the weight applied.

### Why log-odds

Log-odds accumulation is the form Bayesian updating takes when independent
pieces of evidence are combined, and it has the properties this problem needs.
Confidence cannot leave the interval however much evidence arrives. Evidence
order does not change the final value, which matters because publication order
is partly an accident of review times. And the audit row is legible: a reader can
see that one measurement moved a claim by a stated number of log-odds and can
check the arithmetic.

### The prior

Every claim starts at a confidence of 0.05, which is log-odds of about -2.94.
The prior is deliberately low and it is the same for every claim, because a
per-claim prior would be the place where knowledge of the answers could enter
without being visible. A uniform sceptical prior means a claim only rises
because evidence raised it.

### The strength constant

`EVIDENCE_STRENGTH` is 0.85 log-odds per unit weight. It sets how fast beliefs
move, and its value determines calibration more than any other single number
here.

The value was chosen so that the strongest available single measurement, at
weight 2.00, moves a claim from the 0.05 prior to 0.224, which is below the
refusal threshold of 0.25. One measurement, however good, cannot make a claim
reportable. Five measurements at weight 1.00 reach 0.787, and the sequence from
the prior runs 0.110, 0.224, 0.403, 0.612, 0.787. That is the behaviour wanted:
no single screen establishes a therapeutic claim, and agreement between several
independent measurements does.

It was not tuned against the evaluation. The calibration results reported in the
README are what this value produces, including where they are poor.

### Literature evidence is logarithmic, not linear

Publications are not independent experiments. Two hundred papers co-mentioning
BCL11A with fetal hemoglobin are two hundred correlated observations of one
literature, and an earlier version of this module treated each as an independent
update. The result was a confidence of 1.000 for any well-studied gene, which is
not a calibration problem so much as a category error: a pile of citations
became certainty.

A claim's entire literature therefore contributes

    LITERATURE_SCALE * ln(1 + number of HbF-specific publications)

with `LITERATURE_SCALE` at 1.0 log-odds. Each publication still writes its own
audit row, ordered by date: the k-th contributes the difference between ln(1+k)
and ln(k), so the rows sum to exactly the total above, the earliest paper
carries the largest increment, and the timeline still shows belief accumulating
as the field published. A record naming only the erythroid context rather than
HbF gets a quarter of the increment, because working in the right tissue is
weaker evidence than working on the trait.

The resulting curve, from the 0.05 prior:

| HbF-specific publications | Confidence |
| --- | --- |
| 1 | 0.095 |
| 3 | 0.174 |
| 5 | 0.240 |
| 10 | 0.367 |
| 20 | 0.525 |
| 50 | 0.729 |
| 100 | 0.842 |
| 200 | 0.914 |

A gene the field has written two hundred HbF papers about ends up believed and
not certain. A gene with three stays below the refusal threshold.

### Contradiction and supersession

A contradiction subtracts. It does not zero a claim, because a failure to
replicate is itself a measurement made in a system with its own weight, and a
weak contradiction of a strong claim should move it a little.

Supersession is separate from contradiction and does not subtract. When a
claim is refined rather than refuted, for example from "gene X affects HbF" to
"gene X affects HbF solely through gene Y", the earlier claim was coarse and not
wrong. The `SUPERSEDES` edge records the refinement and the earlier claim keeps
its confidence.

## Refusal

Refusal is a scored outcome, and the threshold is a policy.

A claim is reported as a forecast only if its confidence reaches 0.25 and it has
evidence of substance behind it. Evidence of substance means either of two
routes:

*   one supporting measurement with a method signature weight of at least 0.30,
    meaning a genetic association or a functional result in a system that
    matters; or
*   at least five publications naming the gene together with fetal hemoglobin
    specifically.

Two routes rather than one, because the open record contains both kinds of
evidence and recognising only the first makes the system unable to say anything
at all. There are almost no open, dated, redistributable functional HbF
measurements, as DATA_SOURCES.md and LIMITATIONS.md set out, so a
measurement-only rule refuses every gene and the benchmark measures nothing.

What neither route admits is a claim resting on a handful of co-mentions. Five
HbF-specific publications is a stated threshold, frozen with the rest, and the
logarithmic literature rule above means five of them only reach a confidence of
0.240, so a gene needs a little more than the bare minimum on both counts
before it is reported.

Below the threshold the system returns a refusal naming what is missing, not a
low-confidence guess. The refusal is graded: on questions whose answer genuinely
postdates the cutoff, a refusal is correct and scores.

One consequence is worth stating because it affects how the trap row should be
read. If the forecast is empty, every trap whose correct answer is "reject"
passes for free. The grader detects that case, marks those passes vacuous, and
reports `traps_passed_meaningfully` separately, so a system that refuses
everything cannot appear to have avoided every trap.

## Cost lens

The module is `src/hindcast/cost.py`, and its reasoning has to be makeable from
pre-T information or it is useless inside a forecast. It therefore uses two
pre-T facts: the protein class, taken from the HGNC gene family, and whether the
effect is exerted through a cis-regulatory element. Both were knowable decades
before any slice used here. Nothing in that module reads a tractability
annotation or a drug database, because those reflect what is known now.

The route weights are 10.0 for a small molecule, 4.0 for an in vivo edit, 1.0
for a single ex vivo edit, 0.4 for a multi-edit ex vivo product and 0.0 for
mechanistic insight implying no route. The gaps are chosen so that a moderately
confident small-molecule claim outranks a highly confident multi-edit claim,
which is the reordering the lens exists to produce. The anchors are the
approved products: Casgevy at about $2.2M and Lyfgenia at about $3.1M, neither
including the required inpatient stay, both requiring apheresis, GMP
manufacturing and myeloablative conditioning.

One ordering decision inside that module was made with a known case in view,
and it should be stated plainly. The cis-element check runs before the complex
check. BCL11A is listed by HGNC among BAF complex subunits, which would score it
as the most expensive route, while the approved therapy disrupts its erythroid
enhancer with a single edit. The ordering follows the established pathway rather
than the complex annotation. That is a judgement informed by knowing what was
approved, it is not derived from the pre-T record, and a reader should weigh it
as such.
