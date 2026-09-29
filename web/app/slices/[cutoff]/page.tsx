import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Calibration, Meter } from "@/components/Charts";
import { RefusalTable } from "@/components/RefusalTable";
import {
  ABLATION_PLAIN,
  MODALITY,
  TRAP_KIND,
  int,
  modalityLabel,
  num,
  recordLink,
  trapLabel,
  year,
} from "@/lib/format";
import {
  ABLATIONS,
  PRIMARY_SLICE,
  SLICES,
  isAblation,
  isSlice,
  loadHeldout,
  loadPolicy,
  loadSlice,
} from "@/lib/repo";

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
      <div className="eyebrow">Results · evidence frozen at {cutoff}</div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 24, flexWrap: "wrap", alignItems: "end" }}>
        <h1>
          Cutoff <span style={{ color: "var(--accent)" }}>{year(cutoff)}</span>
        </h1>
        <div style={{ display: "grid", gap: 10, justifyItems: "start" }}>
          <nav className="segmented" aria-label="Cutoff">
            {SLICES.map((s) => (
              <Link key={s} href={href(s, ablation, rank)} aria-current={s === cutoff ? "true" : undefined}>
                {year(s)}
                {s === PRIMARY_SLICE ? " ★" : ""}
              </Link>
            ))}
          </nav>
        </div>
      </div>
      <div style={{ marginTop: 22, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="small muted" style={{ marginRight: 4 }}>
          Variant:
        </span>
        {ABLATIONS.map((a) => (
          <Link
            key={a}
            href={href(cutoff, a, rank)}
            className={`tag ${a === ablation ? "bad" : "plain"}`}
            style={{ textDecoration: "none" }}
            aria-current={a === ablation ? "true" : undefined}
          >
            {a}
          </Link>
        ))}
      </div>
      <p className="lede" style={{ marginTop: 16, fontSize: "1.02rem" }}>
        {ABLATION_PLAIN[ablation]}
      </p>
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
  const truth = new Set(card.ground_truth_symbols);
  const ranking = rank === "cost" ? card.ranking_by_cost_impact : card.ranking_by_confidence;
  const items = [...result.forecast.items].sort((a, b) =>
    rank === "cost" ? a.rank_by_cost_impact - b.rank_by_cost_impact : a.rank_by_confidence - b.rank_by_confidence,
  );
  const refusalBySymbol = new Map(result.forecast.refusals.map((r) => [r.gene_symbol, r]));
  const forecastBySymbol = new Map(result.forecast.items.map((i) => [i.gene_symbol, i]));

  return (
    <div className="wrap page">
      {header}

      {/* ---------- headline ---------- */}
      <section className="grid" style={{ marginTop: 40, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 230px), 1fr))" }}>
        <div className="stat rise rise-1">
          <div className="value">{card.forecast_size}</div>
          <div className="label">genes predicted to matter for fetal hemoglobin</div>
        </div>
        <div className="stat future rise rise-2">
          <div className="value">{card.ground_truth_symbols.length}</div>
          <div className="label">genes the field actually established after {year(cutoff)}</div>
        </div>
        <div className="stat accent rise rise-3">
          <div className="value">
            {ranking?.hits_at_10.length ?? 0}
            <small>of {card.forecast_size}</small>
          </div>
          <div className="label">predictions that came true (precision@5 {num(ranking?.precision_at_5)})</div>
        </div>
        <div className="stat rise rise-4">
          <div className="value">
            {card.refusal_count}
          </div>
          <div className="label">genes where it declined to make a claim</div>
        </div>
        <div className="stat rise rise-2">
          <div className="value">
            {card.judgement_traps_passed}
            <small>/{card.judgement_traps_total}</small>
          </div>
          <div className="label">judgement traps avoided (decoy genes)</div>
        </div>
        <div className="stat rise rise-3">
          <div className="value">
            {card.contamination_traps_passed}
            <small>/{card.contamination_traps_total}</small>
          </div>
          <div className="label">contamination checks passed (no future leaked in)</div>
        </div>
        <div className="stat rise rise-4">
          <div className="value">{num(card.expected_calibration_error, 3)}</div>
          <div className="label">calibration error (0 means its confidence is perfectly honest)</div>
        </div>
        <div className="stat rise rise-5">
          <div className="value">{card.fabricated_numbers}</div>
          <div className="label">numbers that could not be traced to a source record</div>
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
        <p className="muted small" style={{ maxWidth: "75ch" }}>
          {rank === "cost"
            ? "Re-ranked by confidence times the cost weight of the likely treatment route, so a cheap pill outranks a multi-million-dollar cell therapy at similar confidence."
            : "Ranked by how strongly the pre-cutoff evidence supports each claim."}{" "}
          A red edge marks a prediction the field later confirmed.
        </p>
        {items.length === 0 ? (
          <div className="callout neutral">
            <p>Nothing cleared the bar for a claim at this cutoff.</p>
          </div>
        ) : (
          <ol className="forecast-list">
            {items.map((item) => {
              const hit = truth.has(item.gene_symbol);
              const r = rank === "cost" ? item.rank_by_cost_impact : item.rank_by_confidence;
              return (
                <li key={item.claim_id} className={`forecast-item${hit ? " hit" : ""}`}>
                  <div className="rank">{String(r).padStart(2, "0")}</div>
                  <div>
                    <h3>
                      <Link href={`/genes/${item.gene_symbol}`}>{item.gene_symbol}</Link>
                      {hit ? <span className="tag bad">came true</span> : <span className="tag plain">not confirmed</span>}
                      <span className="tag future" title={MODALITY[item.implied_modality]?.plain}>
                        {modalityLabel(item.implied_modality)}
                      </span>
                    </h3>
                    <p style={{ margin: "6px 0 10px", color: "var(--ink-2)" }}>{item.statement}</p>
                    <div style={{ display: "flex", gap: 10, alignItems: "center", maxWidth: 420 }}>
                      <Meter value={item.confidence} threshold={threshold} />
                      <span className="mono small">{item.confidence.toFixed(3)}</span>
                    </div>
                    <div className="facts">
                      <span>
                        evidence <b>{item.evidence_count}</b>
                      </span>
                      <span>
                        cost weight <b>×{item.cost_weight}</b>
                      </span>
                      <span>
                        affordable impact <b>{num(item.cost_impact, 3)}</b>
                      </span>
                      <span>
                        rank by confidence <b>{item.rank_by_confidence}</b> · by cost <b>{item.rank_by_cost_impact}</b>
                      </span>
                    </div>
                    <details style={{ marginTop: 14 }}>
                      <summary className="small">Why this route, and the {item.supporting_record_ids.length} supporting records</summary>
                      <div className="body">
                        <p>{item.modality_rationale}</p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {item.supporting_record_ids.map((id) => {
                            const link = recordLink(id);
                            return link ? (
                              <a key={id} href={link} target="_blank" rel="noreferrer" className="tag plain" style={{ textDecoration: "none" }}>
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
                </li>
              );
            })}
          </ol>
        )}
        {result.forecast.already_established.length > 0 && (
          <p className="small muted" style={{ marginTop: 16 }}>
            Left out because the field had already established them before the cutoff (
            {result.forecast.already_established.length}):{" "}
            {result.forecast.already_established.map((s, i) => (
              <span key={s}>
                {i > 0 && ", "}
                <Link href={`/genes/${s}`} className="mono">
                  {s}
                </Link>
              </span>
            ))}
            .
          </p>
        )}
      </section>

      {/* ---------- answer key ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>The answer key</h2>
          <p>Every gene the field established after {cutoff}, and what the system said about it beforehand.</p>
        </div>
        <div className="grid grid-4" style={{ gap: 10 }}>
          {card.ground_truth_symbols.map((s) => {
            const f = forecastBySymbol.get(s);
            const r = refusalBySymbol.get(s);
            return (
              <Link
                key={s}
                href={`/genes/${s}`}
                className="card"
                style={{ padding: "12px 14px", borderLeft: `3px solid ${f ? "var(--accent)" : "var(--future)"}` }}
              >
                <div className="mono" style={{ fontWeight: 600 }}>
                  {s}
                </div>
                <div className="small muted">
                  {f
                    ? `predicted, rank ${f.rank_by_confidence}`
                    : r
                      ? `refused at ${r.confidence.toFixed(2)}`
                      : "never came up"}
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* ---------- traps ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Trick questions</h2>
          <p>Planted before grading, drawn from the data itself. The system never knows which genes are traps.</p>
        </div>
        <div className="grid grid-3" style={{ marginBottom: 20 }}>
          {Object.entries(TRAP_KIND).map(([kind, t]) => (
            <div key={kind} className="card">
              <div className="eyebrow">{t.family === "judgement" ? "judgement trap" : "contamination check"}</div>
              <h3>{t.label}</h3>
              <p className="small muted">{t.plain}</p>
            </div>
          ))}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Gene</th>
                <th>Kind</th>
                <th>Right answer</th>
                <th>System said</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {card.traps.map((t) => (
                <tr key={t.trap_id}>
                  <td>
                    <Link className="gene" href={`/genes/${t.gene_symbol}`}>
                      {t.gene_symbol}
                    </Link>
                  </td>
                  <td className="small">{trapLabel(t.kind)}</td>
                  <td className="small">{t.correct_answer}</td>
                  <td className="small">{t.system_answer}</td>
                  <td>
                    {t.passed ? <span className="tag ok">passed</span> : <span className="tag bad">failed</span>}
                    {t.vacuous && <span className="tag warn" style={{ marginLeft: 6 }}>vacuous</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ---------- refusals ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Refusals</h2>
          <p>
            “The evidence before the cutoff does not support a claim here.” Highlighted rows were refused and then found by the field anyway: a
            correct refusal and a missed forecast at once.
          </p>
        </div>
        <RefusalTable
          threshold={threshold}
          rows={result.forecast.refusals.map((r) => ({
            gene_symbol: r.gene_symbol,
            confidence: r.confidence,
            evidence_count: r.evidence_count,
            reason: r.reason,
            foundLater: truth.has(r.gene_symbol),
          }))}
        />
      </section>

      {/* ---------- calibration ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Is its confidence honest?</h2>
          <span className="num">ECE {num(card.expected_calibration_error, 3)}</span>
        </div>
        <div className="grid grid-2" style={{ alignItems: "center" }}>
          <Calibration bins={card.calibration_bins} />
          <div>
            <p>
              If a forecaster says “30% likely” a hundred times, about thirty of those should come true. Bars show how often claims at each
              confidence level actually came true; the dashed line is perfect honesty.
            </p>
            <p className="muted small">
              Measured over {card.calibration_bins.reduce((n, b) => n + b.n, 0)} claims in five bins, several nearly empty. Treat it as a rough
              reading, not a precise one.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- held-out ---------- */}
      {heldout && heldout.holdouts.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Held-out recovery</h2>
            <p>Hide a gene’s lab measurements and check whether it can still be reached from what remains.</p>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Gene</th>
                  <th className="num">Measurements hidden</th>
                  <th className="num">Confidence with</th>
                  <th className="num">Without</th>
                  <th>Reportable</th>
                  <th>Recovered</th>
                </tr>
              </thead>
              <tbody>
                {heldout.holdouts.map((h) => (
                  <tr key={h.gene_symbol}>
                    <td>
                      <Link className="gene" href={`/genes/${h.gene_symbol}`}>
                        {h.gene_symbol}
                      </Link>
                    </td>
                    <td className="num">{int(h.measurements_hidden)}</td>
                    <td className="num">{num(h.confidence_with_measurements, 3)}</td>
                    <td className="num">{num(h.confidence_without_measurements, 3)}</td>
                    <td className="small">{h.reportable_with ? "yes" : "no"}</td>
                    <td>
                      {h.reportable_with ? (
                        h.recovered ? <span className="tag ok">recovered</span> : <span className="tag bad">lost</span>
                      ) : (
                        <span className="tag plain">not tested</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 12 }}>
            {heldout.genes_tested} reportable gene{heldout.genes_tested === 1 ? "" : "s"} tested, {heldout.recovered} recovered. A rate over one
            or two genes is not evidence of much; the README says so too.
          </p>
        </section>
      )}

      {/* ---------- notes ---------- */}
      <section className="section">
        <div className="section-head">
          <h2>Grader’s notes and run facts</h2>
        </div>
        <div className="grid grid-2" style={{ alignItems: "start" }}>
          <div style={{ display: "grid", gap: 10 }}>
            {card.notes.map((n, i) => (
              <div key={i} className="callout future">
                <p className="small">{n}</p>
              </div>
            ))}
            <div className="callout neutral">
              <p className="small">{result.forecast.ranking_note}</p>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <tbody>
                <tr><td>Rules extracted from evidence</td><td className="num">{int(result.axiom_count)}</td></tr>
                <tr><td>Candidate claims weighed</td><td className="num">{int(result.claim_count)}</td></tr>
                <tr><td>Belief updates, each audited</td><td className="num">{int(result.revision_count)}</td></tr>
                <tr><td>Graph nodes visible before cutoff</td><td className="num">{int(Number(result.slice_manifest.nodes))}</td></tr>
                <tr><td>Graph edges visible before cutoff</td><td className="num">{int(Number(result.slice_manifest.edges))}</td></tr>
                <tr><td>Record IDs checked for provenance</td><td className="num">{int(result.provenance_report.checked_record_ids)}</td></tr>
                <tr><td>Untraceable</td><td className="num">{result.provenance_report.untraceable}</td></tr>
                <tr><td>Cost lens reordered</td><td className="num">{card.cost_lens_reordered}</td></tr>
                <tr><td>Top route, by confidence</td><td className="num">{modalityLabel(card.cost_lens_top_route_by_confidence)}</td></tr>
                <tr><td>Top route, by affordable impact</td><td className="num">{modalityLabel(card.cost_lens_top_route_by_cost_impact)}</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
