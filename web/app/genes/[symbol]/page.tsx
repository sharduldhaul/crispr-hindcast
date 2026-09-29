import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Meter } from "@/components/Charts";
import { MODALITY, TRAP_KIND, modalityLabel, num, year } from "@/lib/format";
import { geneAcrossSlices, geneIndex, loadPolicy, loadRulebook } from "@/lib/repo";
import type { PubRecord } from "@/lib/types";

export const dynamic = "force-dynamic";

type Params = Promise<{ symbol: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { symbol } = await params;
  return { title: decodeURIComponent(symbol).toUpperCase() };
}

function PubLine({ rec }: { rec: PubRecord }) {
  return (
    <div style={{ padding: "10px 0", borderBottom: "1px solid var(--rule)" }}>
      <div className="small mono muted">
        {rec.date.slice(0, 10)}
        {rec.pmid && (
          <>
            {" · "}
            <a href={`https://pubmed.ncbi.nlm.nih.gov/${rec.pmid}/`} target="_blank" rel="noreferrer">
              PMID {rec.pmid} ↗
            </a>
          </>
        )}
      </div>
      <div>{rec.title}</div>
      {(rec.reason || rec.rejected_because) && (
        <div className="small muted" style={{ fontStyle: "italic" }}>
          {rec.reason ?? `not counted: ${rec.rejected_because}`}
        </div>
      )}
    </div>
  );
}

export default async function GenePage({ params }: { params: Params }) {
  const { symbol: raw } = await params;
  const symbol = decodeURIComponent(raw).toUpperCase();
  const known = geneIndex().some((g) => g.symbol === symbol);
  if (!known) notFound();

  const rulebook = loadRulebook()[symbol];
  const views = geneAcrossSlices(symbol);
  const threshold = loadPolicy()?.refusal.confidence_threshold ?? 0.25;
  const established = rulebook?.establishing_record ?? null;

  return (
    <div className="wrap page">
      <div className="eyebrow">
        <Link href="/genes">Genes</Link> / {symbol}
      </div>
      <h1 style={{ fontFamily: "var(--font-mono)", fontWeight: 600, letterSpacing: "-0.03em" }}>
        {symbol}
      </h1>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 14 }}>
        {rulebook?.core_scope && <span className="tag bad">core gene of the field</span>}
        {established ? (
          <span className="tag future">established {established.date.slice(0, 10)}</span>
        ) : (
          <span className="tag plain">not established by the rule book</span>
        )}
        <a
          className="tag plain"
          style={{ textDecoration: "none" }}
          href={`https://www.genenames.org/tools/search/#!/?query=${encodeURIComponent(symbol)}`}
          target="_blank"
          rel="noreferrer"
        >
          HGNC ↗
        </a>
      </div>

      {/* ---------- across slices ---------- */}
      <section className="section" style={{ marginTop: 44 }}>
        <div className="section-head">
          <h2>What the system said</h2>
          <p>Full system, at each cutoff, using only evidence dated before it.</p>
        </div>
        <div className="grid grid-3">
          {views.map((v) => {
            const future = established ? established.date.slice(0, 10) >= v.cutoff : false;
            const verdict = v.verdict;
            return (
              <div key={v.cutoff} className="card lift" style={{ borderTop: `3px solid ${verdict.kind === "forecast" ? "var(--accent)" : "var(--ink)"}` }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <Link href={`/slices/${v.cutoff}`} style={{ fontFamily: "var(--font-display)", fontSize: "2rem" }}>
                    {year(v.cutoff)}
                  </Link>
                  {v.inGroundTruth && <span className="tag future">in answer key</span>}
                </div>
                <div style={{ marginTop: 12 }}>
                  {verdict.kind === "forecast" && (
                    <>
                      <div style={{ fontWeight: 600 }}>
                        Predicted, rank {verdict.rank} {v.inGroundTruth ? <span className="tag ok">came true</span> : null}
                      </div>
                      <p className="small muted" style={{ margin: "6px 0 10px" }}>{verdict.statement}</p>
                      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                        <Meter value={verdict.confidence} threshold={threshold} />
                        <span className="mono small">{num(verdict.confidence, 3)}</span>
                      </div>
                      <p className="small" style={{ marginTop: 10 }}>
                        Likely route: <b title={MODALITY[verdict.modality]?.plain}>{modalityLabel(verdict.modality)}</b>, rank {verdict.costRank} by
                        affordable impact. {verdict.evidence} supporting records.
                      </p>
                    </>
                  )}
                  {verdict.kind === "refused" && (
                    <>
                      <div style={{ fontWeight: 600 }}>
                        Refused{" "}
                        {v.inGroundTruth && <span className="tag warn">found later</span>}
                      </div>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", margin: "10px 0" }}>
                        <Meter value={verdict.confidence} threshold={threshold} />
                        <span className="mono small">{num(verdict.confidence, 3)}</span>
                      </div>
                      <p className="small muted">{verdict.reason}</p>
                    </>
                  )}
                  {verdict.kind === "already-known" && (
                    <p className="small">
                      <b>Already established</b> before this cutoff, so not something to forecast.
                    </p>
                  )}
                  {verdict.kind === "not-considered" && (
                    <p className="small muted">
                      No claim was formed about this gene{future ? "; any evidence for it was still in the future" : ""}.
                    </p>
                  )}
                </div>
                {v.traps.length > 0 && (
                  <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--rule)" }}>
                    {v.traps.map((t) => (
                      <div key={t.trap_id} className="small" style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                        <span className="tag warn">trap</span>
                        <span>{TRAP_KIND[t.kind]?.label ?? t.kind}</span>
                        {t.passed ? <span className="tag ok">passed</span> : <span className="tag bad">failed</span>}
                      </div>
                    ))}
                  </div>
                )}
                {v.holdout && (
                  <div className="small muted" style={{ marginTop: 10 }}>
                    Held-out test: {v.holdout.note}.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* ---------- answer key ---------- */}
      {rulebook && (
        <section className="section">
          <div className="section-head">
            <h2>When the field found it</h2>
            <p>From the frozen rule book: the first publication whose title asserts a role over fetal hemoglobin.</p>
          </div>
          {established ? (
            <div className="callout future">
              <PubLine rec={established} />
            </div>
          ) : (
            <div className="callout neutral">
              <p>No publication met the rule for this gene.</p>
            </div>
          )}
          {(rulebook.near_misses.length > 0 || rulebook.rejected_candidates.length > 0) && (
            <details style={{ marginTop: 16 }}>
              <summary>
                {rulebook.near_misses.length + rulebook.rejected_candidates.length} other candidate publications, and why they did not count
              </summary>
              <div className="body">
                {[...rulebook.near_misses, ...rulebook.rejected_candidates]
                  .sort((a, b) => a.date.localeCompare(b.date))
                  .map((rec, i) => (
                    <PubLine key={`${rec.pmid}-${i}`} rec={rec} />
                  ))}
              </div>
            </details>
          )}
          <p className="small muted" style={{ marginTop: 12 }}>
            {rulebook.records_considered} records considered, searched as {rulebook.query_terms.map((t) => `“${t}”`).join(", ")}.
          </p>
        </section>
      )}
    </div>
  );
}
