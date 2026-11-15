import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Meter } from "@/components/Charts";
import { GeneHistory, type HistoryPub } from "@/components/viz/GeneHistory";
import { MODALITY, TRAP_KIND, VERDICT, longDate, modalityLabel, num, year } from "@/lib/format";
import { type GeneSliceView, geneAcrossSlices, geneIndex, loadPolicy, loadRulebook } from "@/lib/repo";
import type { PubRecord, VerdictKind } from "@/lib/types";

export const dynamic = "force-dynamic";

type Params = Promise<{ symbol: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { symbol } = await params;
  return { title: decodeURIComponent(symbol).toUpperCase() };
}

function kindOf(v: GeneSliceView): VerdictKind {
  switch (v.verdict.kind) {
    case "forecast":
      return v.inGroundTruth ? "hit" : "forecast";
    case "refused":
      return v.inGroundTruth ? "missed" : "refused";
    case "already-known":
      return "known";
    default:
      return "none";
  }
}

function PubLine({ rec, bare = false }: { rec: PubRecord; bare?: boolean }) {
  return (
    <div style={{ padding: bare ? 0 : "12px 0", borderBottom: bare ? "none" : "1px solid var(--rule)" }}>
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
      <div style={{ color: "var(--ink)" }}>{rec.title}</div>
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
  if (!geneIndex().some((g) => g.symbol === symbol)) notFound();

  const rulebook = loadRulebook()[symbol];
  const views = geneAcrossSlices(symbol);
  const threshold = loadPolicy()?.refusal.confidence_threshold ?? 0.25;
  const established = rulebook?.establishing_record ?? null;
  const kinds = views.map(kindOf);
  const uniform = kinds.every((k) => k === kinds[0]) && (kinds[0] === "known" || kinds[0] === "none");
  const holdoutNotes = views.filter((v) => v.holdout).map((v) => `${year(v.cutoff)}: ${v.holdout!.note}`);
  const why = (rec: PubRecord) => rec.reason ?? (rec.rejected_because ? `Not counted: ${rec.rejected_because}` : null);
  const pubs: HistoryPub[] = rulebook
    ? [
        ...(established ? [{ ...established, role: "established" as const }] : []),
        ...rulebook.near_misses.map((r) => ({ ...r, role: "near" as const })),
        ...rulebook.rejected_candidates.map((r) => ({ ...r, role: "rejected" as const })),
      ].map((r) => ({ date: r.date.slice(0, 10), title: r.title, pmid: r.pmid, role: r.role, why: why(r) }))
    : [];

  return (
    <div className="wrap page">
      <div className="eyebrow">
        <Link href="/genes">Genes</Link> / {symbol}
      </div>
      <h1 style={{ fontFamily: "var(--font-mono)", fontWeight: 600, letterSpacing: "-0.03em" }}>{symbol}</h1>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
        {rulebook?.core_scope && <span className="tag gold">core gene of the field</span>}
        {established ? (
          <span className="tag future">established {longDate(established.date)}</span>
        ) : (
          <span className="tag plain">not established by the rule book</span>
        )}
        {views.some((v) => v.traps.length > 0) && <span className="tag trap">used as a trap</span>}
        <a
          className="tag plain"
          href={`https://www.genenames.org/tools/search/#!/?query=${encodeURIComponent(symbol)}`}
          target="_blank"
          rel="noreferrer"
        >
          HGNC ↗
        </a>
      </div>

      {/* ---------- across slices ---------- */}
      <section className="section" style={{ marginTop: 52 }}>
        <div className="section-head">
          <h2>What the system said</h2>
        </div>
        <GeneHistory
          threshold={threshold}
          established={established?.date.slice(0, 10) ?? null}
          pubs={pubs}
          marks={views.map((v, i) => ({
            cutoff: v.cutoff,
            kind: kinds[i],
            confidence: v.verdict.kind === "forecast" || v.verdict.kind === "refused" ? v.verdict.confidence : null,
            detail:
              v.verdict.kind === "forecast"
                ? `rank ${v.verdict.rank}, ${v.verdict.evidence} supporting records`
                : v.verdict.kind === "refused"
                  ? `${v.verdict.evidence} piece${v.verdict.evidence === 1 ? "" : "s"} of evidence`
                  : v.verdict.kind === "already-known"
                    ? "already established before this cutoff"
                    : "no evidence reached the system",
          }))}
        />

        {uniform ? (
          <p className="muted" style={{ marginTop: 20 }}>
            {kinds[0] === "known"
              ? "Already established before every cutoff, so never something to forecast."
              : "No claim was formed about this gene at any cutoff."}
            {holdoutNotes.length > 0 && ` Held-out test, ${holdoutNotes.join("; ")}.`}
          </p>
        ) : (
          <div className="grid grid-3" style={{ marginTop: 20 }}>
            {views.map((v, i) => {
              const verdict = v.verdict;
              const kind = kinds[i];
              return (
                <div key={v.cutoff} className={`card v-${kind}`} style={{ borderTop: "2px solid var(--v)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                    <Link href={`/slices/${v.cutoff}`} style={{ fontSize: "1.8rem", fontWeight: 300, textDecoration: "none" }}>
                      {year(v.cutoff)}
                    </Link>
                    {kind !== "none" && <span className="tag v">{VERDICT[kind].label}</span>}
                  </div>
                  <div style={{ marginTop: 12 }} className="small">
                    {verdict.kind === "forecast" && (
                      <>
                        <p style={{ color: "var(--ink-2)", marginBottom: 10 }}>{verdict.statement}</p>
                        <div className="meter-row">
                          <Meter value={verdict.confidence} threshold={threshold} />
                          <span className="mono">{num(verdict.confidence, 3)}</span>
                        </div>
                        <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
                          Rank {verdict.rank} by confidence, {verdict.costRank} by affordable impact. Route{" "}
                          <span title={MODALITY[verdict.modality]?.plain} style={{ color: "var(--ink)" }}>
                            {modalityLabel(verdict.modality)}
                          </span>
                          , {verdict.evidence} supporting records.
                        </p>
                      </>
                    )}
                    {verdict.kind === "refused" && (
                      <>
                        <div className="meter-row">
                          <Meter value={verdict.confidence} threshold={threshold} />
                          <span className="mono">{num(verdict.confidence, 3)}</span>
                        </div>
                        <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
                          {(threshold - verdict.confidence).toFixed(3)} short of the {threshold} threshold, on {verdict.evidence} piece
                          {verdict.evidence === 1 ? "" : "s"} of evidence.
                          {kind === "missed" && " The field found it anyway."}
                        </p>
                      </>
                    )}
                    {verdict.kind === "already-known" && (
                      <p className="muted" style={{ margin: 0 }}>
                        Already established before this cutoff, so not something to forecast.
                      </p>
                    )}
                    {verdict.kind === "not-considered" && (
                      <p className="muted" style={{ margin: 0 }}>
                        No claim was formed: no evidence for it before this cutoff reached the system.
                      </p>
                    )}
                  </div>
                  {v.traps.length > 0 && (
                    <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--rule)", display: "grid", gap: 6 }}>
                      {v.traps.map((t) => (
                        <div key={t.trap_id} className="small" style={{ display: "flex", gap: 8, alignItems: "baseline", justifyContent: "space-between" }}>
                          <span className="muted">Trap: {TRAP_KIND[t.kind]?.label ?? t.kind}</span>
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
        )}
      </section>

      {/* ---------- answer key ---------- */}
      {rulebook && (
        <section className="section">
          <div className="section-head">
            <h2>When the field found it</h2>
          </div>
          {established ? (
            <div className="callout future">
              <PubLine rec={established} bare />
            </div>
          ) : (
            <div className="callout neutral">
              <p>No publication met the rule for this gene.</p>
            </div>
          )}
          {(rulebook.near_misses.length > 0 || rulebook.rejected_candidates.length > 0) && (
            <details className="disclose" style={{ marginTop: 16 }}>
              <summary>
                {rulebook.near_misses.length + rulebook.rejected_candidates.length} other candidate publication
                {rulebook.near_misses.length + rulebook.rejected_candidates.length === 1 ? "" : "s"}, and why{" "}
                {rulebook.near_misses.length + rulebook.rejected_candidates.length === 1 ? "it" : "they"} did not count
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
