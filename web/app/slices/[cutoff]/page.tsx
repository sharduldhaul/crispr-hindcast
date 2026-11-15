import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Meter } from "@/components/Charts";
import { RefusalTable } from "@/components/RefusalTable";
import { Calibration } from "@/components/viz/Calibration";
import { CountUp } from "@/components/viz/CountUp";
import { DecisionSwarm } from "@/components/viz/DecisionSwarm";
import { HeldoutDumbbell } from "@/components/viz/HeldoutDumbbell";
import { RankSlope } from "@/components/viz/RankSlope";
import { ABLATION_PLAIN, MODALITY, TRAP_KIND, VERDICT, int, longDate, modalityLabel, num, recordLink, year } from "@/lib/format";
import { PRIMARY_SLICE, SLICES, isAblation, isSlice, loadHeldout, loadPolicy, loadSlice } from "@/lib/repo";
import type { VerdictKind } from "@/lib/types";

export const dynamic = "force-dynamic";

type Params = Promise<{ cutoff: string }>;
type Search = Promise<{ ablation?: string; rank?: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { cutoff } = await params;
  return { title: `Cutoff ${cutoff}` };
}

function href(cutoff: string, ablation: string, rank: string) {
  const q = new URLSearchParams();
  if (ablation !== "full system") q.set("ablation", ablation);
  if (rank !== "confidence") q.set("rank", rank);
  const s = q.toString();
  return `/slices/${cutoff}${s ? `?${s}` : ""}`;
}

export default async function SlicePage({ params, searchParams }: { params: Params; searchParams: Search }) {
  const { cutoff } = await params;
  const sp = await searchParams;
  if (!isSlice(cutoff)) notFound();
  const ablation = sp.ablation && isAblation(sp.ablation) ? sp.ablation : "full system";
  const rank = sp.rank === "cost" ? "cost" : "confidence";

  const result = loadSlice(cutoff, ablation);
  const policy = loadPolicy();
  const heldout = ablation === "full system" ? loadHeldout(cutoff) : null;
  const threshold = policy?.refusal.confidence_threshold ?? 0.25;

  const header = (
    <>
      <div className="eyebrow">Evidence frozen at {longDate(cutoff)}</div>
      <div className="page-head">
        <h1>
          Cutoff <span style={{ color: "var(--accent)" }}>{year(cutoff)}</span>
        </h1>
        <nav className="segmented lg" aria-label="Cutoff">
          {SLICES.map((s) => (
            <Link
              key={s}
              href={href(s, ablation, rank)}
              aria-current={s === cutoff ? "true" : undefined}
              title={s === PRIMARY_SLICE ? "The primary slice" : undefined}
            >
              {year(s)}
            </Link>
          ))}
        </nav>
      </div>
      {ablation !== "full system" && (
        <div className="callout future" style={{ marginTop: 24, display: "flex", gap: 16, justifyContent: "space-between", flexWrap: "wrap" }}>
          <span>
            <b>Ablation: {ablation}.</b> {ABLATION_PLAIN[ablation]}
          </span>
          <Link className="go" href={href(cutoff, "full system", rank)}>
            Back to the full system
          </Link>
        </div>
      )}
    </>
  );

  if (!result) {
    return (
      <div className="wrap page">
        {header}
        <div className="callout" style={{ marginTop: 32 }}>
          <p>
            No result file for this run yet. <Link href="/run">Run it from the pipeline page</Link>.
          </p>
        </div>
      </div>
    );
  }

  const card = result.scorecard;
  const ranking = rank === "cost" ? card.ranking_by_cost_impact : card.ranking_by_confidence;
  const truth = new Set(card.ground_truth_symbols);
  const items = [...result.forecast.items].sort((a, b) =>
    rank === "cost" ? a.rank_by_cost_impact - b.rank_by_cost_impact : a.rank_by_confidence - b.rank_by_confidence,
  );
  const hits = items.filter((i) => truth.has(i.gene_symbol)).length;
  const refusalBySymbol = new Map(result.forecast.refusals.map((r) => [r.gene_symbol, r]));
  const forecastBySymbol = new Map(result.forecast.items.map((i) => [i.gene_symbol, i]));

  const decision = [
    ...result.forecast.items.map((i) => ({
      symbol: i.gene_symbol,
      confidence: i.confidence,
      evidence: i.evidence_count,
      kind: (truth.has(i.gene_symbol) ? "hit" : "forecast") as VerdictKind,
    })),
    ...result.forecast.refusals.map((r) => ({
      symbol: r.gene_symbol,
      confidence: r.confidence,
      evidence: r.evidence_count,
      kind: (truth.has(r.gene_symbol) ? "missed" : "refused") as VerdictKind,
    })),
  ];
  const showSlope = card.cost_lens_reordered > 0 && items.length >= 2 && items.length <= 15;
  const closest = result.forecast.refusals
    .filter((r) => truth.has(r.gene_symbol))
    .sort((a, b) => b.confidence - a.confidence)
    .filter((r, i, all) => r.confidence === all[0].confidence);

  const trapKinds = Object.entries(TRAP_KIND)
    .map(([kind, meta]) => ({ kind, meta, traps: card.traps.filter((t) => t.kind === kind) }))
    .filter((g) => g.traps.length > 0);
  const tested = heldout?.holdouts.filter((h) => h.reportable_with) ?? [];
  const claimsCalibrated = card.calibration_bins.reduce((n, b) => n + b.n, 0);

  return (
    <div className="wrap page">
      {header}

      {/* ---------- headline ---------- */}
      <section className="bento" style={{ marginTop: 32 }}>
        <div className="tile half rise rise-1" style={{ "--span": 3 } as React.CSSProperties}>
          <div className="tile-label">Genes named</div>
          <div className="kpi foot">
            <CountUp value={card.forecast_size} />
          </div>
        </div>
        <div className="tile blue half rise rise-2" style={{ "--span": 3 } as React.CSSProperties}>
          <div className="tile-label">Came true</div>
          <div className="kpi foot">
            <CountUp value={hits} />
            <small>/ {card.forecast_size}</small>
          </div>
          <p className="sub mono">
            P@5 {num(ranking?.precision_at_5)} · MRR {num(ranking?.mean_reciprocal_rank)}
          </p>
        </div>
        <div className="tile half rise rise-3" style={{ "--span": 3 } as React.CSSProperties}>
          <div className="tile-label">Found after {year(cutoff)}</div>
          <div className="kpi foot">
            <CountUp value={card.ground_truth_symbols.length} />
          </div>
        </div>
        <a href="#traps" className="tile bone half rise rise-4" style={{ "--span": 3 } as React.CSSProperties}>
          <div className="tile-label">
            Traps avoided
            <span className="arrow" aria-hidden>
              ↓
            </span>
          </div>
          <div className="kpi foot">
            <CountUp value={card.traps_passed} />
            <small>/ {card.traps_total}</small>
          </div>
        </a>
      </section>

      {/* ---------- answer key ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Answer key</h2>
        </div>
        <div className="chips unseal">
          {card.ground_truth_symbols.map((s, i) => {
            const f = forecastBySymbol.get(s);
            const r = refusalBySymbol.get(s);
            const kind = f ? "v-hit" : r ? "v-missed" : "v-none";
            return (
              <Link key={s} href={`/genes/${s}`} className={`chip ${kind}`} style={{ animationDelay: `${120 + i * 45}ms` }}>
                <span className={`dot${f ? "" : " ring"}`} />
                <b>{s}</b>
                <span className="note">{f ? `#${f.rank_by_confidence}` : r ? r.confidence.toFixed(2) : "not weighed"}</span>
              </Link>
            );
          })}
        </div>
        <div className="legend">
          <span className="v-hit">
            <span className="dot" /> predicted, rank
          </span>
          <span className="v-missed">
            <span className="dot ring" /> refused, confidence
          </span>
          {card.ground_truth_symbols.some((s) => !forecastBySymbol.has(s) && !refusalBySymbol.has(s)) && (
            <span className="v-none">
              <span className="dot ring" /> no evidence before the cutoff
            </span>
          )}
        </div>
      </section>

      {/* ---------- forecast ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>The forecast</h2>
          <nav className="segmented" aria-label="Ranking">
            <Link href={href(cutoff, ablation, "confidence")} aria-current={rank === "confidence" ? "true" : undefined}>
              By confidence
            </Link>
            <Link href={href(cutoff, ablation, "cost")} aria-current={rank === "cost" ? "true" : undefined}>
              By affordable impact
            </Link>
          </nav>
        </div>
        {showSlope && (
          <div className="card" style={{ marginBottom: 28, padding: "18px 22px" }}>
            <RankSlope
              items={result.forecast.items.map((i) => ({
                symbol: i.gene_symbol,
                confidence: i.confidence,
                impact: i.cost_impact,
                weight: i.cost_weight,
                route: modalityLabel(i.implied_modality),
                rankConf: i.rank_by_confidence,
                rankCost: i.rank_by_cost_impact,
                hit: truth.has(i.gene_symbol),
              }))}
            />
          </div>
        )}
        {items.length === 0 ? (
          <div className="callout neutral">
            <p>Nothing cleared the bar for a claim at this cutoff.</p>
          </div>
        ) : (
          <ol className="forecast-list">
            {items.map((item) => {
              const hit = truth.has(item.gene_symbol);
              const r = rank === "cost" ? item.rank_by_cost_impact : item.rank_by_confidence;
              const shift = item.rank_by_confidence - item.rank_by_cost_impact;
              return (
                <li key={item.claim_id} className={`fc ${hit ? "v-hit" : "v-forecast"}`}>
                  <div className="rank">
                    {String(r).padStart(2, "0")}
                    {rank === "cost" && shift !== 0 && (
                      <span className={`shift ${shift > 0 ? "up" : "down"}`} title={`rank ${item.rank_by_confidence} by confidence`}>
                        {shift > 0 ? "↑" : "↓"}
                        {Math.abs(shift)} from {item.rank_by_confidence}
                      </span>
                    )}
                  </div>
                  <div>
                    <div className="fc-title">
                      <Link href={`/genes/${item.gene_symbol}`}>{item.gene_symbol}</Link>
                      {hit ? <span className="tag ok">came true</span> : <span className="tag plain">not confirmed</span>}
                    </div>
                    <p className="fc-claim">{item.statement}</p>
                    <details className="disclose">
                      <summary>Why this route, and the {item.supporting_record_ids.length} supporting records</summary>
                      <div className="body">
                        <p className="small" style={{ color: "var(--ink-2)" }}>
                          {item.modality_rationale}
                        </p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {item.supporting_record_ids.map((id) => {
                            const link = recordLink(id);
                            return link ? (
                              <a key={id} href={link} target="_blank" rel="noreferrer" className="tag plain">
                                {id} ↗
                              </a>
                            ) : (
                              <span key={id} className="tag plain">
                                {id}
                              </span>
                            );
                          })}
                        </div>
                      </div>
                    </details>
                  </div>
                  <div className="fc-side">
                    <div className="meter-row">
                      <Meter value={item.confidence} threshold={threshold} />
                      <span className="mono small">{item.confidence.toFixed(3)}</span>
                    </div>
                    <span title={MODALITY[item.implied_modality]?.plain}>
                      Route <b>{modalityLabel(item.implied_modality)}</b>
                      {rank === "cost" && (
                        <>
                          {" "}
                          · ×{item.cost_weight} = <b>{num(item.cost_impact, 2)}</b>
                        </>
                      )}
                    </span>
                    <span>
                      <b>{item.evidence_count}</b> pieces of evidence
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        {result.forecast.already_established.length > 0 && (
          <p className="small muted" style={{ marginTop: 18 }}>
            Not forecast because the field had already established them: {result.forecast.already_established.join(", ")}.
          </p>
        )}
      </section>

      {/* ---------- decision line ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Decision threshold</h2>
        </div>
        <DecisionSwarm points={decision} threshold={threshold} />
        <div className="legend">
          {(
            [
              ["hit", "came true"],
              ["forecast", "predicted, not confirmed"],
              ["missed", "refused, found later"],
              ["refused", "refused"],
            ] as const
          )
            .filter(([k]) => decision.some((p) => p.kind === k))
            .map(([k, label]) => (
              <span key={k} className={`v-${k}`} title={VERDICT[k].plain}>
                <span className={`dot${k === "refused" ? " ring" : ""}`} /> {label}
              </span>
            ))}
        </div>
        {closest.length > 0 && (
          <p className="small" style={{ marginTop: 16, maxWidth: "72ch" }}>
            Closest miss{closest.length > 1 ? "es" : ""}: <b className="mono">{closest.map((r) => r.gene_symbol).join(" and ")}</b> at{" "}
            {closest[0].confidence.toFixed(3)},{" "}
            {threshold - closest[0].confidence > 0
              ? `${(threshold - closest[0].confidence).toFixed(3)} under the line`
              : "on the line"}
            .
          </p>
        )}
        {result.forecast.refusals.length > 0 && (
          <details className="panel" style={{ marginTop: 20 }}>
            <summary>All {result.forecast.refusals.length} refusals</summary>
            <div className="body">
              <RefusalTable
                threshold={threshold}
                rows={result.forecast.refusals.map((r) => ({
                  gene_symbol: r.gene_symbol,
                  confidence: r.confidence,
                  evidence_count: r.evidence_count,
                  foundLater: truth.has(r.gene_symbol),
                }))}
              />
            </div>
          </details>
        )}
      </section>

      {/* ---------- traps ---------- */}
      <section className="section" id="traps">
        <div className="section-head">
          <h2>Traps</h2>
        </div>
        <div className="grid grid-3">
          {trapKinds.map(({ kind, meta, traps }) => {
            const passed = traps.filter((t) => t.passed).length;
            return (
              <div key={kind} className="card">
                <div className="small muted" style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <span>{meta.family === "judgement" ? "Judgement trap" : "Contamination check"}</span>
                  <span className="mono" style={{ color: passed === traps.length ? "var(--ok)" : "var(--accent)" }}>
                    {passed}/{traps.length} passed
                  </span>
                </div>
                <h3 style={{ marginTop: 6, marginBottom: 14 }} title={meta.plain}>
                  {meta.label}
                </h3>
                <div className="chips" style={{ gap: 6 }}>
                  {traps.map((t) => (
                    <Link
                      key={t.trap_id}
                      href={`/genes/${t.gene_symbol}`}
                      className={`chip ${!t.passed ? "v-forecast" : t.vacuous ? "v-warn" : "v-hit"}`}
                      title={`${t.detail}${t.vacuous ? ". Vacuous: passed only because the forecast was empty." : ""}`}
                    >
                      <span aria-hidden>{t.passed ? "✓" : "✕"}</span>
                      <b>{t.gene_symbol}</b>
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ---------- calibration and held-out ---------- */}
      <section className="section grid grid-2" style={{ alignItems: "start" }}>
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
            <h3>Calibration</h3>
            <span className="mono small muted">ECE {num(card.expected_calibration_error, 3)}</span>
          </div>
          <p className="small muted">{claimsCalibrated} claims; sparse bins.</p>
          <Calibration bins={card.calibration_bins} claims={decision} />
          <p className="viz-hint" style={{ margin: "10px 0 0" }}>
            Click a band to see its claims.
          </p>
        </div>
        {heldout && (
          <div className="card">
            <h3>Held-out recovery</h3>
            <p className="small muted">
              Lab measurements hidden: {heldout.recovered} of {heldout.genes_tested} genes still reached.
            </p>
            {tested.length > 0 && (
              <>
                <HeldoutDumbbell
                  threshold={threshold}
                  rows={tested.map((h) => ({
                    symbol: h.gene_symbol,
                    hidden: h.measurements_hidden,
                    with: h.confidence_with_measurements,
                    without: h.confidence_without_measurements,
                    recovered: h.recovered,
                  }))}
                />
                <div className="legend">
                  <span>
                    <span className="dot ring" style={{ ["--v" as string]: "var(--ink)" }} /> with its measurements
                  </span>
                  <span className="v-hit">
                    <span className="dot" /> without them, still reachable
                  </span>
                  {tested.some((h) => !h.recovered) && (
                    <span style={{ ["--v" as string]: "var(--bad)" }}>
                      <span className="dot" /> without them, lost
                    </span>
                  )}
                </div>
              </>
            )}
            {heldout.holdouts.length > tested.length && (
              <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
                {heldout.holdouts.length - tested.length} other genes were below the threshold even with their measurements.
              </p>
            )}
          </div>
        )}
      </section>

      {/* ---------- audit ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Audit trail</h2>
        </div>
        <div className="grid grid-2" style={{ alignItems: "start" }}>
          <div style={{ display: "grid", gap: 10 }}>
            {card.notes.map((n, i) => (
              <div key={i} className="callout future">
                <p className="small">{n}</p>
              </div>
            ))}
          </div>
          <div className="table-wrap">
            <table>
              <tbody>
                <tr><td>Rules extracted from evidence</td><td className="num">{int(result.axiom_count)}</td></tr>
                <tr><td>Candidate claims weighed</td><td className="num">{int(result.claim_count)}</td></tr>
                <tr><td>Belief updates, each audited</td><td className="num">{int(result.revision_count)}</td></tr>
                <tr><td>Graph nodes and edges visible</td><td className="num">{int(Number(result.slice_manifest.nodes))} · {int(Number(result.slice_manifest.edges))}</td></tr>
                <tr><td>Record IDs traced to a source</td><td className="num">{int(result.provenance_report.checked_record_ids)}</td></tr>
                <tr><td>Untraceable records</td><td className="num">{result.provenance_report.untraceable}</td></tr>
                <tr><td>Numbers with no source row</td><td className="num">{card.fabricated_numbers}</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
