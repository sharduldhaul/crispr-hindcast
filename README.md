# CRISPR HINDCAST

[![CI](https://github.com/sharduldhaul/crispr-hindcast/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sharduldhaul/crispr-hindcast/actions/workflows/ci.yml)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/sharduldhaul/crispr-hindcast)

A benchmark that tests whether a system can forecast scientific discoveries
from past evidence alone, built so that a correct answer cannot come from
leaked data or a tuned answer key.

## The problem

When an AI system "predicts" a scientific result, it may only be repeating it.
Language models are trained on the published record, so a test built from
published findings cannot separate forecasting from recall. A high score is
then not evidence of reasoning, and most evaluations give no way to tell.

## The solution

A hindcast: pick a cutoff date T, remove every piece of evidence dated on or
after T, ask for a forecast, and grade it against what the field published
after T.

The test case is fetal hemoglobin, a therapeutic route for sickle cell disease:
which genes controlling it would the field establish next? Two forecasters
answer at three cutoffs (2014, 2017, 2020): a rule-based system with no
language model, and a language model (`gemini-3.8-flash`) as the comparison.

![System architecture: public data becomes an evidence graph that is cut at a date T; a rule-based system and a language model forecast from the earlier part, and a grader scores them against the answer key built from the later part, with trap questions mixed in](diagrams/system_architecture.png)

### How it solves the problem

Each way a forecasting test can be fooled has a control that is enforced by
code and checked by a test.

| Failure | Control | Checked by |
| --- | --- | --- |
| Later evidence leaks into the reasoning | Each cutoff gets its own database holding only earlier rows, served over a connection that can attach nothing else | `tests/test_slice_leak.py` |
| The answer key is tuned to the result | The answer key and every threshold were frozen and tagged ([`rulebook-frozen-v1`](https://github.com/sharduldhaul/crispr-hindcast/tree/rulebook-frozen-v1)) before the first run | Git history |
| Guessing is rewarded | Refusal is a scored outcome, and trap questions are mixed into the candidates | `tests/test_refusal.py` |
| The model recalls the answer from training | The model runs alone, with text retrieval and with graph tools, and each claim is checked against the evidence it was given. This measures recall; it cannot remove it | [LIMITATIONS.md](LIMITATIONS.md#the-memorization-signal-is-a-lower-bound) |
| A number cannot be verified | Every number traces to a source row, and a clone reproduces every result offline, byte for byte, with no API key | `tests/test_provenance_and_license.py`, `tests/test_determinism.py` |

## Results

Three cutoffs and five ranking slots give wide intervals. The full tables, with
intervals and definitions, are generated from `eval/results/` and sit in the
scorecard below.

- **Model alone scores highest, and the score is recall.** P@5 is 1.00, 0.80
  and 0.20 across the cutoffs with no evidence given, and every claim for a
  gene established after the cutoff is counted as recalled (6 of 6, 4 of 4,
  1 of 1). This is the problem above,
  measured.
- **Graph tools keep most of the score and ground it.** P@5 is 0.80, 0.60 and
  0.20, every claim cites a row the model was given (4 of 4, 3 of 3, 2 of 2),
  and no cited ID is fabricated in any model row.
- **The rule-based system is cautious.** P@5 is 0.20 (1 of 5) at every cutoff.
  It passes every trap (22 of 22, 15 of 15, 9 of 9); the model rows miss up to
  6 of 22.
- **Its misses are reported.** The two main findings after 2017, EIF2AK1 and
  ZNF410, were refused: the open data before 2018 holds no measurement for
  either. Two correct genes stopped at confidence 0.240 against the frozen
  threshold of 0.25, and the threshold was not moved.

[LIMITATIONS.md](LIMITATIONS.md) states what each number does and does not
show.

<details>
<summary>Full scorecard</summary>

<!-- SCORECARD:START -->

### Ingestion

| Measure | Value |
| --- | --- |
| Source records considered | 295,986 |
| Nodes loaded | 287,026 |
| Edges loaded | 231,751 |
| Excluded, with a recorded reason | 10,269 |
| Spurious records created | 0 |

Exclusions by reason:

| Reason | Records |
| --- | --- |
| out_of_scope | 6,341 |
| malformed_record | 3,345 |
| unresolved_symbol | 371 |
| unresolvable_date | 117 |
| unresolved_cell_line | 95 |

### Scorecard, full system

| Slice | Ground truth | Forecast | Refusals | P@5 conf [95% interval] | P@5 cost | P@10 conf | MRR [95% interval] | Judgement traps | Contamination traps | Refusal acc | ECE | Fabricated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014-12-31 | 19 | 2 | 47 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.500 [0.000, 1.000] | 6/6 | 16/16 | 16/16 (1.00) | 0.302 | 0 |
| 2017-12-31 | 13 | 2 | 42 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.500 [0.000, 1.000] | 7/7 | 8/8 | 8/8 (1.00) | 0.199 | 0 |
| 2020-12-31 | 3 | 6 | 28 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.333 [0.000, 1.000] | 7/7 | 2/2 | 2/2 (1.00) | 0.066 | 0 |

### Rule-based system and language model

| Slice | System | P@5 [95% interval] | MRR [95% interval] | Traps passed | Refusal acc | ECE | Grounded-claim rate [95% interval] | Fabricated IDs | Recalled claims |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014-12-31 | rule-based system | 0.20 [0.00, 0.60] | 0.500 [0.000, 1.000] | 22/22 | 16/16 (1.00) | 0.302 | n/a | n/a | n/a |
| 2014-12-31 | flat literature baseline | 0.00 [0.00, 0.00] | 0.071 [0.042, 0.111] | 8/22 | 0/16 (0.00) | 0.325 | n/a | n/a | n/a |
| 2014-12-31 | model alone | 1.00 [0.40, 1.00] | 1.000 [1.000, 1.000] | 16/22 | 10/16 (0.62) | 0.312 | 0.00 (0 of 6) [0.00, 0.00] | 0 | 6 of 6 |
| 2014-12-31 | model with text retrieval | 0.20 [0.00, 0.60] | 1.000 [0.000, 1.000] | 21/22 | 15/16 (0.94) | 0.388 | 1.00 (1 of 1) [1.00, 1.00] | 0 | 0 of 1 |
| 2014-12-31 | model with graph tools | 0.80 [0.20, 1.00] | 1.000 [1.000, 1.000] | 18/22 | 12/16 (0.75) | 0.340 | 1.00 (4 of 4) [1.00, 1.00] | 0 | 0 of 4 |
| 2017-12-31 | rule-based system | 0.20 [0.00, 0.60] | 0.500 [0.000, 1.000] | 15/15 | 8/8 (1.00) | 0.199 | n/a | n/a | n/a |
| 2017-12-31 | flat literature baseline | 0.00 [0.00, 0.00] | 0.062 [0.036, 0.100] | 8/15 | 0/8 (0.00) | 0.225 | n/a | n/a | n/a |
| 2017-12-31 | model alone | 0.80 [0.20, 1.00] | 1.000 [1.000, 1.000] | 11/15 | 4/8 (0.50) | 0.241 | 0.00 (0 of 4) [0.00, 0.00] | 0 | 4 of 4 |
| 2017-12-31 | model with text retrieval | 0.60 [0.00, 1.00] | 0.500 [0.000, 1.000] | 11/15 | 5/8 (0.62) | 0.287 | 0.75 (3 of 4) [0.25, 1.00] | 0 | 1 of 3 |
| 2017-12-31 | model with graph tools | 0.60 [0.00, 1.00] | 1.000 [0.000, 1.000] | 12/15 | 5/8 (0.62) | 0.260 | 1.00 (3 of 3) [1.00, 1.00] | 0 | 0 of 3 |
| 2020-12-31 | rule-based system | 0.20 [0.00, 0.60] | 0.333 [0.000, 1.000] | 9/9 | 2/2 (1.00) | 0.066 | n/a | n/a | n/a |
| 2020-12-31 | flat literature baseline | 0.00 [0.00, 0.00] | 0.034 [0.000, 0.045] | 7/9 | 0/2 (0.00) | 0.079 | n/a | n/a | n/a |
| 2020-12-31 | model alone | 0.20 [0.00, 0.60] | 1.000 [0.000, 1.000] | 8/9 | 1/2 (0.50) | 0.069 | 0.00 (0 of 1) [0.00, 0.00] | 0 | 1 of 1 |
| 2020-12-31 | model with text retrieval | 0.00 [0.00, 0.00] | 0.000 [0.000, 0.000] | 9/9 | 2/2 (1.00) | 0.124 | 1.00 (1 of 1) [1.00, 1.00] | 0 | 0 of 0 |
| 2020-12-31 | model with graph tools | 0.20 [0.00, 0.60] | 0.500 [0.000, 1.000] | 8/9 | 1/2 (0.50) | 0.102 | 1.00 (2 of 2) [1.00, 1.00] | 0 | 0 of 1 |

Model: `gemini-3.8-flash`.

| Column | Definition |
| --- | --- |
| P@5 | Precision at 5: genes later established among the 5 highest-confidence claims, over 5. |
| MRR | Reciprocal rank of the first established gene in the ranking. |
| Traps passed | Traps answered correctly, over all traps for the slice. |
| Refusal acc | Genes refused, over the genes the slice holds too little evidence to answer. |
| ECE | Expected calibration error over five confidence bins. |
| Grounded-claim rate | Claims citing at least one row the model was given that names the claimed gene, over all claims. A lower bar than the faithfulness metrics of RAG evaluation: it does not test that the row supports the claim. |
| Fabricated IDs | Cited IDs that no store holds. |
| Recalled claims | Claims for a gene established on or after the cutoff that are not grounded, over all claims for such genes. |
| n/a | The rule-based rows cite no IDs, so the column does not apply. |

### Ablations, primary slice

| Ablation | Forecast | Refusals | P@5 conf | P@10 conf | MRR | Judgement traps | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| full system | 2 | 42 | 0.20 | 0.10 | 0.500 | 7/7 | 0.199 |
| no belief revision | 0 | 44 | 0.00 | 0.00 | 0.000 | 0/7 | 0.245 |
| no graph | 60 | 0 | 0.00 | 0.00 | 0.062 | 7/7 | 0.225 |
| no method signature | 2 | 42 | 0.20 | 0.10 | 0.500 | 7/7 | 0.198 |
| no ontology normalization | 2 | 42 | 0.20 | 0.10 | 0.500 | 7/7 | 0.199 |

### Traps, primary slice, named individually

| Trap | Kind | Correct answer | System answer | Result |
| --- | --- | --- | --- | --- |
| HBBP1 | association_without_function | reject | refused | pass |
| OR51B5 | association_without_function | reject | refused | pass |
| OR51B6 | association_without_function | reject | refused | pass |
| EIF2S1 | pan_essential | reject | refused | pass |
| CTCF | pan_essential | reject | not forecast | pass |
| RBBP4 | pan_essential | reject | refused | pass |
| PRMT5 | pan_essential | reject | not forecast | pass |
| ATF4 | postdates_cutoff | refuse | refused | pass (contamination check) |
| EIF2AK1 | postdates_cutoff | refuse | refused | pass (contamination check) |
| GATAD2A | postdates_cutoff | refuse | refused | pass (contamination check) |
| HIC2 | postdates_cutoff | refuse | refused | pass (contamination check) |
| MTA2 | postdates_cutoff | refuse | refused | pass (contamination check) |
| NFIX | postdates_cutoff | refuse | refused | pass (contamination check) |
| RBBP4 | postdates_cutoff | refuse | refused | pass (contamination check) |
| ZNF410 | postdates_cutoff | refuse | refused | pass (contamination check) |

### Reliability, primary slice, full system

| Confidence bin | Claims | Mean confidence | Observed frequency |
| --- | --- | --- | --- |
| 0.0 to 0.2 | 38 | 0.091 | 0.237 |
| 0.2 to 0.4 | 5 | 0.253 | 0.800 |
| 0.4 to 0.6 | 1 | 0.486 | 0.000 |
| 0.6 to 0.8 | 0 | 0.000 | 0.000 |
| 0.8 to 1.0 | 0 | 0.000 | 0.000 |

### Cost lens, full system

| Slice | Forecast | Items reordered by cost weighting | Top by confidence | Top by cost impact | Surfaces a small molecule |
| --- | --- | --- | --- | --- | --- |
| 2014-12-31 | 2 | 2 | EX_VIVO_SINGLE_EDIT | SMALL_MOLECULE | yes |
| 2017-12-31 | 2 | 0 | EX_VIVO_SINGLE_EDIT | EX_VIVO_SINGLE_EDIT | no |
| 2020-12-31 | 6 | 5 | EX_VIVO_SINGLE_EDIT | SMALL_MOLECULE | yes |

### Held-out recovery

| Slice | Genes tested | Recovered | Rate | Mean confidence drop |
| --- | --- | --- | --- | --- |
| 2014-12-31 | 1 | 1 | 1.00 | 0.309 |
| 2017-12-31 | 1 | 1 | 1.00 | 0.192 |
| 2020-12-31 | 5 | 5 | 1.00 | 0.029 |

<!-- SCORECARD:END -->

</details>

## Launch the app

A local website that shows every result and re-runs the pipeline from the
browser. It works offline, with no API key. The Codespaces badge above opens
the same app with nothing to install.

Needs [Python 3.12+](https://www.python.org/downloads/),
[uv](https://docs.astral.sh/uv/getting-started/installation/) and
[Node.js 20.9+](https://nodejs.org/).

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
.venv/bin/hindcast build          # evidence graph from the committed snapshot
cd web && npm install && npm run dev
```

Open http://127.0.0.1:4100.

From the command line:

```bash
.venv/bin/hindcast slice --cutoff 2017-12-31   # one cutoff, about 20 seconds
.venv/bin/hindcast run-all                     # every cutoff and ablation
.venv/bin/hindcast scorecard                   # print the results table
.venv/bin/python -m pytest -q                  # the checks behind the table above
```

Model rows replay from `eval/model_cache/`. A new live run is opt-in and needs
your own key:

```bash
GEMINI_API_KEY=... .venv/bin/hindcast llm --cutoff 2017-12-31 --retrieval graph --live
```

In a codespace, set `GEMINI_API_KEY` as a
[Codespaces secret](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces)
instead.

## Documentation

| File | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Diagrams of the system, the evaluation and the scoring; the six agents |
| [METHODOLOGY.md](METHODOLOGY.md) | Every coefficient and rule with its reason; the language-model track and its design decisions |
| [LIMITATIONS.md](LIMITATIONS.md) | What the results do not show |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Sources, licenses, attributions and exclusions |
| [SCHEMA.md](SCHEMA.md) | Node and edge types |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The six hard rules and how each is enforced |

## Credit

The idea came from [Cortex Bio](https://cortexbiolabs.com) and their July 2026
case study,
[Designing molecules that have never been made](https://cortexbiolabs.com/post/designing-molecules-that-have-never-been-made),
which names the contamination problem and describes two controls for it. This
project follows that design and adds a temporal holdout as a complementary
control;
[METHODOLOGY.md](METHODOLOGY.md#temporal-holdout-as-a-complementary-contamination-control)
gives the comparison. It is an independent project, not affiliated with Cortex
Bio, not a reimplementation of their product, and makes no claim about it.

## License

Code: [MIT](LICENSE). Each dataset keeps its own license, recorded on every
node and edge and listed with its required attribution in
[DATA_SOURCES.md](DATA_SOURCES.md). Only identifiers, metadata, measurements
and publication titles are committed; no article text or abstracts.

Product and company names are used only to identify them and belong to their
owners. This is research software and not medical advice.
