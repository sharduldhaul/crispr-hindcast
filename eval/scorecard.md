### Headline

| Cutoff | Forecaster | P@5 [95% interval] | Traps passed | Grounded claims | Recalled claims |
| --- | --- | --- | --- | --- | --- |
| 2014-12-31 | rule-based system | 0.20 [0.00, 0.60] | 22/22 | n/a | n/a |
| 2014-12-31 | model alone | 1.00 [0.40, 1.00] | 16/22 | 0 of 6 | 6 of 6 |
| 2014-12-31 | model with text retrieval | 0.20 [0.00, 0.60] | 21/22 | 1 of 1 | 0 of 1 |
| 2014-12-31 | model with graph tools | 0.80 [0.20, 1.00] | 18/22 | 4 of 4 | 0 of 4 |
| 2017-12-31 | rule-based system | 0.20 [0.00, 0.60] | 15/15 | n/a | n/a |
| 2017-12-31 | model alone | 0.80 [0.20, 1.00] | 11/15 | 0 of 4 | 4 of 4 |
| 2017-12-31 | model with text retrieval | 0.60 [0.00, 1.00] | 11/15 | 3 of 4 | 1 of 3 |
| 2017-12-31 | model with graph tools | 0.60 [0.00, 1.00] | 12/15 | 3 of 3 | 0 of 3 |
| 2020-12-31 | rule-based system | 0.20 [0.00, 0.60] | 9/9 | n/a | n/a |
| 2020-12-31 | model alone | 0.20 [0.00, 0.60] | 8/9 | 0 of 1 | 1 of 1 |
| 2020-12-31 | model with text retrieval | 0.00 [0.00, 0.00] | 9/9 | 1 of 1 | 0 of 0 |
| 2020-12-31 | model with graph tools | 0.20 [0.00, 0.60] | 8/9 | 2 of 2 | 0 of 1 |

- **P@5**: of the 5 highest-confidence claims, the share the field later established.
- **Traps passed**: trap questions answered correctly, over all traps at that cutoff.
- **Grounded claims**: claims that cite a row the model was given that names the gene.
- **Recalled claims**: claims for a gene established after the cutoff that cite no such row: the answer came from training, not from the evidence.

### Rule-based system, every metric

| Slice | Ground truth | Forecast | Refusals | P@5 conf [95% interval] | P@5 cost | P@10 conf | MRR [95% interval] | Judgement traps | Contamination traps | Refusal acc | ECE | Fabricated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014-12-31 | 19 | 2 | 47 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.500 [0.000, 1.000] | 6/6 | 16/16 | 16/16 (1.00) | 0.302 | 0 |
| 2017-12-31 | 13 | 2 | 42 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.500 [0.000, 1.000] | 7/7 | 8/8 | 8/8 (1.00) | 0.199 | 0 |
| 2020-12-31 | 3 | 6 | 28 | 0.20 [0.00, 0.60] | 0.20 | 0.10 | 0.333 [0.000, 1.000] | 7/7 | 2/2 | 2/2 (1.00) | 0.066 | 0 |

### Rule-based system and language model, every metric

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
