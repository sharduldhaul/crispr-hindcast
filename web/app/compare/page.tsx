import type { Metadata } from "next";
import Link from "next/link";

import { BarRow } from "@/components/Charts";
import { ABLATION_PLAIN, num, year } from "@/lib/format";
import { ABLATIONS, PRIMARY_SLICE, SLICES, isSlice, loadSlice } from "@/lib/repo";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Ablations" };

type Search = Promise<{ cutoff?: string }>;

export default async function ComparePage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const cutoff = sp.cutoff && isSlice(sp.cutoff) ? sp.cutoff : PRIMARY_SLICE;
  const rows = ABLATIONS.map((ablation) => ({ ablation, result: loadSlice(cutoff, ablation) }));
  const present = rows.filter((r) => r.result);

  const metric = (
    title: string,
    explain: string,
    get: (r: NonNullable<(typeof rows)[number]["result"]>) => number | null,
    fmt: (v: number) => string,
    max?: number,
  ) => {
    const values = present.map((r) => get(r.result!) ?? 0);
    const top = max ?? Math.max(1e-9, ...values);
    return (
      <div className="card lift">
        <h3>{title}</h3>
        <p className="small muted">{explain}</p>
        {present.map((r) => {
          const v = get(r.result!);
          return (
            <BarRow
              key={r.ablation}
              label={r.ablation}
              value={v ?? 0}
              max={top}
              display={v === null ? "n/a" : fmt(v)}
              emphasis={r.ablation === "full system"}
            />
          );
        })}
      </div>
    );
  };

  return (
    <div className="wrap page">
      <div className="eyebrow">Ablations · what each part is worth</div>
      <h1>Switch a part off. Watch what breaks.</h1>
      <p className="lede" style={{ marginTop: 18 }}>
        An ablation removes one component and re-runs the whole test. If the score drops, that part
        was doing real work. If nothing changes, it earned nothing here, and that is reported too.
      </p>

      <nav className="segmented" aria-label="Cutoff" style={{ marginTop: 26 }}>
        {SLICES.map((s) => (
          <Link key={s} href={`/compare?cutoff=${s}`} aria-current={s === cutoff ? "true" : undefined}>
            Cutoff {year(s)}
          </Link>
        ))}
      </nav>

      <section className="section" style={{ marginTop: 36 }}>
        <div className="grid grid-2">
          {metric(
            "Correct in the top five",
            "Precision at 5, ranked by confidence. Higher is better.",
            (r) => r.scorecard.ranking_by_confidence?.precision_at_5 ?? 0,
            (v) => num(v),
            1,
          )}
          {metric(
            "How soon the first right answer appears",
            "Mean reciprocal rank: 1.0 means the top pick was right, 0.5 the second.",
            (r) => r.scorecard.ranking_by_confidence?.mean_reciprocal_rank ?? 0,
            (v) => num(v, 3),
            1,
          )}
          {metric(
            "Decoy genes avoided",
            "Share of judgement traps passed. A system that endorses decoys is guessing.",
            (r) =>
              r.scorecard.judgement_traps_total
                ? r.scorecard.judgement_traps_passed / r.scorecard.judgement_traps_total
                : null,
            (v) => `${Math.round(v * 100)}%`,
            1,
          )}
          {metric(
            "Genes put forward",
            "Size of the forecast. Bigger is not better: the baseline names everything.",
            (r) => r.scorecard.forecast_size,
            (v) => String(v),
          )}
          {metric(
            "Calibration error",
            "How far stated confidence is from reality. Lower is better.",
            (r) => r.scorecard.expected_calibration_error,
            (v) => num(v, 3),
          )}
          {metric(
            "Refusals",
            "Genes where the variant declined to make a claim.",
            (r) => r.scorecard.refusal_count,
            (v) => String(v),
          )}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>The variants</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Variant</th>
                <th>What changes</th>
                <th className="num">Forecast</th>
                <th className="num">P@5</th>
                <th className="num">MRR</th>
                <th className="num">Traps</th>
                <th className="num">ECE</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ ablation, result }) => (
                <tr key={ablation} className={ablation === "full system" ? "highlight" : undefined}>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <Link href={`/slices/${cutoff}${ablation === "full system" ? "" : `?ablation=${encodeURIComponent(ablation)}`}`}>
                      {ablation}
                    </Link>
                  </td>
                  <td className="small" style={{ color: "var(--ink-2)", minWidth: 240 }}>
                    {ABLATION_PLAIN[ablation]}
                  </td>
                  {result ? (
                    <>
                      <td className="num">{result.scorecard.forecast_size}</td>
                      <td className="num">{num(result.scorecard.ranking_by_confidence?.precision_at_5)}</td>
                      <td className="num">{num(result.scorecard.ranking_by_confidence?.mean_reciprocal_rank, 3)}</td>
                      <td className="num">
                        {result.scorecard.judgement_traps_passed}/{result.scorecard.judgement_traps_total}
                      </td>
                      <td className="num">{num(result.scorecard.expected_calibration_error, 3)}</td>
                    </>
                  ) : (
                    <td colSpan={5} className="small muted">
                      not run
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {cutoff === PRIMARY_SLICE && (
        <div className="callout neutral" style={{ marginTop: 20 }}>
          <p className="small">
            <b>What the primary slice shows.</b> Belief revision carries the result: without it the
            forecast is empty and every decoy slips through. The no-graph baseline, which just counts
            papers, names sixty genes and finds its first right answer far down the list. Removing
            the method signature or name normalization changes nothing, because the pre-2018 data
            holds no functional fetal hemoglobin measurement for them to weigh.
          </p>
        </div>
        )}
      </section>
    </div>
  );
}
