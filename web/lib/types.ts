// Shapes of the JSON files the Python pipeline writes to eval/results and
// eval/rulebook. Only the fields the interface reads are typed.

export interface ForecastItem {
  claim_id: string;
  gene_symbol: string;
  gene_id: string;
  confidence: number;
  cost_impact: number;
  cost_weight: number;
  evidence_count: number;
  implied_modality: string;
  modality_rationale: string;
  rank_by_confidence: number;
  rank_by_cost_impact: number;
  statement: string;
  supporting_record_ids: string[];
  contradicting_record_ids: string[];
  max_supporting_weight: number;
}

export interface Refusal {
  claim_id: string;
  gene_symbol: string;
  gene_id: string;
  confidence: number;
  evidence_count: number;
  max_supporting_weight: number;
  reason: string;
}

export interface Ranking {
  ranking: string;
  precision_at_5: number;
  precision_at_10: number;
  mean_reciprocal_rank: number;
  hits_at_5: string[];
  hits_at_10: string[];
  first_hit_rank: number | null;
  n_ground_truth: number;
  n_ranked: number;
}

export interface Trap {
  trap_id: string;
  gene_symbol: string;
  kind: string;
  correct_answer: string;
  system_answer: string;
  passed: boolean;
  vacuous: boolean;
  detail: string;
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  n: number;
  mean_confidence: number;
  observed_frequency: number;
}

export interface Scorecard {
  run_id: string;
  cutoff: string;
  forecast_size: number;
  refusal_count: number;
  ground_truth_symbols: string[];
  ranking_by_confidence: Ranking | null;
  ranking_by_cost_impact: Ranking | null;
  traps: Trap[];
  traps_passed: number;
  traps_total: number;
  judgement_traps_passed: number;
  judgement_traps_total: number;
  contamination_traps_passed: number;
  contamination_traps_total: number;
  refusal_correct: number;
  refusal_total: number;
  refusal_accuracy: number | null;
  expected_calibration_error: number | null;
  calibration_bins: CalibrationBin[];
  fabricated_numbers: number;
  cost_lens_reordered: number;
  cost_lens_top_route_by_confidence: string | null;
  cost_lens_top_route_by_cost_impact: string | null;
  cost_lens_surfaces_small_molecule: boolean | null;
  notes: string[];
}

export interface SliceResult {
  run_id: string;
  cutoff: string;
  ablation: string;
  axiom_count: number;
  claim_count: number;
  revision_count: number;
  trap_count: number;
  scorecard: Scorecard;
  forecast: {
    cutoff: string;
    items: ForecastItem[];
    refusals: Refusal[];
    already_established: string[];
    ranking_note: string;
  };
  slice_manifest: Record<string, string>;
  provenance_report: {
    checked_objects: number;
    checked_record_ids: number;
    untraceable: number;
    missing_license: number;
  };
}

export interface Holdout {
  gene_symbol: string;
  gene_id: string;
  measurements_hidden: number;
  confidence_with_measurements: number;
  confidence_without_measurements: number;
  recovered: boolean;
  reportable_with: boolean;
  reportable_without: boolean;
  remaining_evidence_count: number;
  note: string;
}

export interface HeldoutReport {
  cutoff: string;
  genes_tested: number;
  holdouts: Holdout[];
  recovered: number;
  recovery_rate: number | null;
}

export interface Ingestion {
  nodes_loaded: number;
  edges_loaded: number;
  records_available: number;
  excluded: number;
  spurious: number;
  exclusions_by_reason: Record<string, number>;
  exclusions_by_source: Record<string, number>;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
}

export interface PubRecord {
  date: string;
  pmid: string | null;
  doi?: string | null;
  title: string;
  reason?: string;
  rejected_because?: string;
}

export interface Establishment {
  symbol: string;
  established: boolean;
  core_scope: boolean;
  establishing_record: PubRecord | null;
  near_misses: PubRecord[];
  rejected_candidates: PubRecord[];
  records_considered: number;
  query_terms: string[];
}

export interface Policy {
  frozen_at: string;
  note: string;
  refusal: {
    confidence_threshold: number;
    min_hbf_publications: number;
    min_supporting_weight: number;
    rationale: string;
  };
  belief_revision: { prior_confidence: number };
  cost_lens: {
    weights: Record<string, number>;
    price_anchors: Record<
      string,
      { brand: string; list_price_usd: number; modality: string; note: string; target: string }
    >;
  };
}
