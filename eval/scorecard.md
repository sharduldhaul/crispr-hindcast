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

| Slice | Ground truth | Forecast | Refusals | P@5 conf | P@5 cost | P@10 conf | MRR | Judgement traps | Contamination traps | Refusal acc | ECE | Fabricated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014-12-31 | 19 | 2 | 47 | 0.20 | 0.20 | 0.10 | 0.500 | 6/6 | 16/16 | 16/16 (1.00) | 0.302 | 0 |
| 2017-12-31 | 13 | 2 | 42 | 0.20 | 0.20 | 0.10 | 0.500 | 7/7 | 8/8 | 8/8 (1.00) | 0.199 | 0 |
| 2020-12-31 | 3 | 6 | 28 | 0.20 | 0.20 | 0.10 | 0.333 | 7/7 | 2/2 | 2/2 (1.00) | 0.066 | 0 |

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
