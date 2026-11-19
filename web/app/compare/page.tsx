import type { Metadata } from "next";

import { type AblationRow, AblationView } from "@/components/viz/AblationView";
import { ABLATION_PLAIN } from "@/lib/format";
import { ABLATIONS, PRIMARY_SLICE, SLICES, isSlice, loadSlice } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Ablations" };

type Search = Promise<{ cutoff?: string }>;

export default async function ComparePage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const cutoff = sp.cutoff && isSlice(sp.cutoff) ? sp.cutoff : PRIMARY_SLICE;

  // Every cutoff's variants go to the client, so switching cutoff animates
  // the dots instead of reloading the page.
  const byCutoff: Record<string, AblationRow[]> = {};
  for (const s of SLICES) {
    byCutoff[s] = ABLATIONS.map((ablation) => {
      const r = loadSlice(s, ablation);
      const card = r?.scorecard;
      return {
        ablation,
        plain: ABLATION_PLAIN[ablation],
        values: card
          ? {
              forecast: card.forecast_size,
              p5: card.ranking_by_confidence?.precision_at_5 ?? null,
              mrr: card.ranking_by_confidence?.mean_reciprocal_rank ?? null,
              traps: card.judgement_traps_total ? card.judgement_traps_passed / card.judgement_traps_total : null,
              ece: card.expected_calibration_error,
            }
          : null,
      };
    });
  }

  return (
    <div className="wrap page">
      <h1>Ablations</h1>
      <p className="lede" style={{ marginTop: 18 }}>
        Each row removes one component of the rule-based system and re-runs the whole test.
      </p>
      <AblationView byCutoff={byCutoff} slices={SLICES} initial={cutoff} primary={PRIMARY_SLICE} />
    </div>
  );
}
