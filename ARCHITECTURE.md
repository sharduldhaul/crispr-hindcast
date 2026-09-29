# Architecture

Three diagrams, from simple to medium detail. The Mermaid sources live in
`diagrams/` and import directly into Excalidraw (More tools, Mermaid to
Excalidraw). Each section explains the idea in ML terms, because the biology is
the domain and not the method.

## The biology in five lines

You need very little of it to follow the system.

| Term | What it means here | ML analogy |
| --- | --- | --- |
| Fetal hemoglobin (HbF) | A form of the oxygen-carrying protein that treats sickle cell disease if switched back on | The target variable |
| Gene | A unit of DNA; the thing being ranked | One candidate in a ranking task |
| CRISPR screen | Knock out thousands of genes one at a time and measure the effect | Feature ablation at genome scale |
| Genetic association (GWAS) | A DNA variant that correlates with a trait across many people | Correlation, not causation; can be a nearby bystander |
| Essential gene | A gene every cell needs to survive | A feature whose removal breaks everything, so it looks important in every screen |

## 1. System architecture

The whole pipeline in one line: public data is cleaned into a graph, cut at a
date, reasoned over, and graded against what was published afterwards.

![System architecture](diagrams/system_architecture.png)

Drawn in Excalidraw from the Mermaid source in
[`diagrams/system_architecture.mmd`](diagrams/system_architecture.mmd).

## 2. Evaluation design: a leak-proof time split

What makes the benchmark worth trusting is not the forecaster but the
evaluation around it. Read it as a time-based train/test split where the split
is enforced by infrastructure rather than by convention.

```mermaid
flowchart TB
    subgraph data["All evidence, every row timestamped"]
        pre["Rows dated before T<br/><i>the only inputs</i>"]
        post["Publications dated on or after T<br/><i>used only to build labels</i>"]
    end

    subgraph guard["Leak guard, enforced by the database"]
        materialize["Copy pre-T rows into a<br/>separate slice database"]
        lock["Open it read-only,<br/>block ATTACH to other DBs"]
        leaktest["test_slice_leak.py<br/>tries every leak route"]
    end

    subgraph labels["Labels, fixed before any run"]
        rule["Title rule: first paper<br/>asserting the gene regulates HbF"]
        frozen["Answer key + all thresholds<br/>committed and git-tagged<br/><i>like a preregistration</i>"]
    end

    system["System under test<br/>no learned parameters"]
    out["Ranked forecast + refusals"]

    subgraph adv["Adversarial test cases"]
        decoy["Decoys: near the right locus,<br/>no plausible function"]
        essential["Essential-everywhere genes:<br/>look like hits, not therapies"]
        canary["Post-T genes: must be refused,<br/><i>a canary for leakage</i>"]
    end

    grader["Blind grader<br/>never sees the slice<br/>or the reasoning"]
    metrics["Metrics: P@5, P@10, MRR,<br/>trap pass rate, refusal accuracy,<br/>calibration error, untraceable numbers"]
    ablate["Ablations: remove one component,<br/>re-run, compare"]
    repeat["Repeat at three cutoffs:<br/>2014, 2017, 2020"]

    pre --> materialize --> lock --> system
    leaktest -.-> lock
    post --> rule --> frozen --> grader
    system --> out --> grader
    decoy --> grader
    essential --> grader
    canary --> grader
    grader --> metrics
    metrics --> ablate
    metrics --> repeat
```

The ideas that carry over to any ML evaluation:

- **The split is physical, not logical.** A `WHERE date < T` filter can be
  forgotten in one query. Here the pre-T rows are copied into their own
  database, opened read-only, with `ATTACH` denied, so the reasoning code cannot
  reach post-T data even by mistake. A test tries each leak route and asserts it
  fails.
- **Labels and thresholds are preregistered.** The answer key comes from a
  stated rule over real publications, and every threshold was committed and
  git-tagged before the first run. The tag's timestamp is the proof that nothing
  was tuned on the test set. The cost of that is visible in the results: two
  correct genes sit at 0.240 against a 0.25 threshold, and the threshold was not
  moved.
- **The test set includes adversarial cases.** Decoys check that the system does
  not confuse correlation with cause. Post-T genes work as leakage canaries: a
  system that claims one has seen the future.
- **The grader is blind.** It receives only the forecast and the answer key, so
  it cannot be influenced by the reasoning it is scoring.
- **Ablations and multiple cutoffs** show which component earns its keep, and
  whether a result holds across time rather than on one lucky split.

Source: [`diagrams/evaluation_design.mmd`](diagrams/evaluation_design.mmd).

## 3. Scoring: from evidence to a prediction or an abstention

The forecaster is a hand-specified log-odds model, close in spirit to naive
Bayes with fixed, documented weights instead of fitted ones. There is no
training step, because the only labels that could be trained on are the answer
key.

```mermaid
flowchart TB
    rec["Evidence record about a gene<br/>genetic association, screen hit,<br/>essentiality score, paper, protein complex"]

    subgraph weight["1. Quality weight: how it was measured, never what it found"]
        terms["w = system x perturbation x readout<br/>x replication x human genetics"]
        clamp["clamped to a fixed range"]
    end

    subgraph update["2. Belief update in log-odds"]
        prior["start at prior 0.05<br/>log-odds -2.94"]
        delta["measurement: +/- 0.85 x w"]
        lit["papers: ln(1 + n), diminishing returns"]
        ess["essential everywhere: capped penalty"]
        sum["running log-odds<br/>sum of all updates"]
        audit["every update written to an<br/>append-only audit table"]
    end

    conf["confidence = sigmoid(log-odds)"]

    subgraph gate["3. Abstention gate"]
        thresh{"confidence at least 0.25<br/>AND one route of substance:<br/>measurement w at least 0.3,<br/>5+ HbF papers, or a complex link"}
    end

    forecast["Forecast"]
    refuse["Refusal, with the reason<br/><i>scored as correct when the answer<br/>was not yet knowable</i>"]

    subgraph cost["4. Cost lens"]
        route["Infer likely treatment route<br/>from protein family"]
        rerank["score x route weight<br/>pill 10, in-body edit 4,<br/>cell therapy 1, multi-edit 0.4"]
        two["Report both rankings side by side"]
    end

    rec --> terms --> clamp --> delta
    rec --> lit
    rec --> ess
    prior --> sum
    delta --> sum
    lit --> sum
    ess --> sum
    sum -.-> audit
    sum --> conf
    conf --> thresh
    thresh -- yes --> forecast
    thresh -- no --> refuse
    forecast --> route --> rerank --> two
```

The design choices, in ML terms:

- **Weights judge the measurement process, not the outcome.** The quality weight
  reads how an experiment was run (which cell type, which perturbation, how
  direct the readout) and never its result. Two identical screens get the same
  weight whether they found an effect or not, which prevents the model from
  rewarding the results it already expects. The terms multiply, so a poor
  experimental system discounts everything measured in it.
- **Correlated evidence is dampened.** A hundred papers about one gene are not a
  hundred independent observations, so literature adds `ln(1 + n)` rather than
  `n`. Five HbF papers alone reach exactly 0.240.
- **Abstention is a first-class output.** Below the gate the system returns a
  refusal naming what is missing. This is selective prediction: a refusal on a
  question whose answer did not yet exist counts as correct. The second
  condition stops a pile of weak co-mentions from carrying a claim over the
  confidence line.
- **Every number is auditable.** Each update is a row in an append-only table,
  enforced by SQLite triggers. A provenance check traces every number in the
  output back to a source record and the scorecard reports any it cannot; the
  count is zero in every run.
- **The ranking objective is explicit.** Confidence alone would favour
  expensive cell therapies. Multiplying by a stated cost weight per treatment
  route produces a second ranking, shown next to the first so the effect of the
  objective is visible.

Every coefficient and its justification is in [METHODOLOGY.md](METHODOLOGY.md).

Source: [`diagrams/scoring_pipeline.mmd`](diagrams/scoring_pipeline.mmd).
