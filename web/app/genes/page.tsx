import type { Metadata } from "next";

import { GeneSearch } from "@/components/GeneSearch";
import type { ScatterPoint } from "@/components/viz/EvidenceScatter";
import { PRIMARY_SLICE, SLICES, geneIndex, loadPolicy, loadSlice } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Genes" };

export default function GenesPage() {
  // Every claim the full system formed at each cutoff, for the scatter.
  const scatter: Record<string, ScatterPoint[]> = {};
  for (const cutoff of SLICES) {
    const result = loadSlice(cutoff);
    if (!result) continue;
    const truth = new Set(result.scorecard.ground_truth_symbols);
    scatter[cutoff] = [
      ...result.forecast.items.map((i) => ({
        symbol: i.gene_symbol,
        confidence: i.confidence,
        evidence: i.evidence_count,
        kind: truth.has(i.gene_symbol) ? ("hit" as const) : ("forecast" as const),
      })),
      ...result.forecast.refusals.map((r) => ({
        symbol: r.gene_symbol,
        confidence: r.confidence,
        evidence: r.evidence_count,
        kind: truth.has(r.gene_symbol) ? ("missed" as const) : ("refused" as const),
      })),
    ];
  }

  return (
    <div className="wrap page">
      <div className="eyebrow">Genes</div>
      <h1>Look up a gene.</h1>
      <p className="lede" style={{ marginTop: 18, marginBottom: 36 }}>
        Every gene weighed, planted as a trap, or in an answer key.
      </p>
      <GeneSearch
        genes={geneIndex()}
        slices={SLICES}
        primary={PRIMARY_SLICE}
        scatter={scatter}
        threshold={loadPolicy()?.refusal.confidence_threshold ?? 0.25}
      />
    </div>
  );
}
