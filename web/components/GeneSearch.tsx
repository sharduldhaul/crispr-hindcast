"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { VERDICT } from "@/lib/format";
import type { GeneIndexEntry } from "@/lib/repo";

import { EvidenceScatter, type ScatterPoint } from "./viz/EvidenceScatter";

type Filter = "all" | "forecast" | "truth" | "trap";

const RING = new Set(["missed", "refused", "none"]);

export function GeneSearch({
  genes,
  slices,
  primary,
  scatter,
  threshold,
}: {
  genes: GeneIndexEntry[];
  slices: readonly string[];
  primary: string;
  scatter: Record<string, ScatterPoint[]>;
  threshold: number;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [cutoff, setCutoff] = useState(primary);

  const shown = useMemo(() => {
    const q = query.trim().toUpperCase();
    return genes.filter((g) => {
      if (q && !g.symbol.includes(q)) return false;
      if (filter === "forecast") return g.forecastAt.length > 0;
      if (filter === "truth") return g.groundTruthAt.length > 0;
      if (filter === "trap") return g.trapped;
      return true;
    });
  }, [genes, query, filter]);

  // The filter row scopes the chart too: anything it hides, the chart dims.
  const highlight = useMemo(
    () => (query.trim() || filter !== "all" ? new Set(shown.map((g) => g.symbol)) : null),
    [shown, query, filter],
  );

  const filters: [Filter, string][] = [
    ["all", "All"],
    ["forecast", "Predicted"],
    ["truth", "In an answer key"],
    ["trap", "Traps"],
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 28 }}>
        <input
          type="search"
          placeholder="Search a symbol, e.g. BCL11A"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search genes"
          autoFocus
        />
        <div className="segmented" role="group" aria-label="Filter">
          {filters.map(([key, label]) => (
            <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>
              {label}
            </button>
          ))}
        </div>
        <span className="small muted" style={{ marginLeft: "auto" }} aria-live="polite">
          {shown.length} genes
        </span>
      </div>

      <section style={{ marginBottom: 44 }}>
        <div className="viz-head">
          <div>
            <h2 style={{ fontSize: "1.45rem" }}>Evidence is not confidence</h2>
            <p className="small muted" style={{ margin: "6px 0 0", maxWidth: "62ch" }}>
              Every gene the system weighed at one cutoff. Correlated records count with diminishing returns, so a gene hundreds of
              records deep can still sit under the line.
            </p>
          </div>
          <div className="segmented" role="group" aria-label="Cutoff for the chart">
            {slices.map((s) => (
              <button key={s} type="button" aria-pressed={cutoff === s} onClick={() => setCutoff(s)}>
                {s.slice(0, 4)}
              </button>
            ))}
          </div>
        </div>
        <EvidenceScatter byCutoff={scatter} cutoff={cutoff} threshold={threshold} highlight={highlight} />
        <div className="legend">
          {(["hit", "forecast", "missed", "refused"] as const).map((k) => (
            <span key={k} className={`v-${k}`}>
              <span className={`dot${k === "refused" ? " ring" : ""}`} /> {VERDICT[k].plain.toLowerCase()}
            </span>
          ))}
        </div>
      </section>

      <div className="table-wrap" tabIndex={0} role="region" aria-label="Genes">
        <table>
          <thead>
            <tr>
              <th>Gene</th>
              <th>Established</th>
              {slices.map((s) => (
                <th key={s}>Cutoff {s.slice(0, 4)}</th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {shown.map((g) => (
              <tr key={g.symbol} className="row-link">
                <td>
                  <Link className="gene" href={`/genes/${g.symbol}`}>
                    {g.symbol}
                  </Link>
                </td>
                <td className="mono small" style={{ color: g.established ? "var(--future)" : "var(--muted)" }}>
                  {g.established ? g.established.slice(0, 4) : "—"}
                </td>
                {g.verdicts.map((v, i) => (
                  <td key={slices[i]}>
                    <span className={`vstrip v-${v}`} title={VERDICT[v].plain}>
                      {v !== "none" && <span className={`dot${RING.has(v) ? " ring" : ""}`} />}
                      {VERDICT[v].label}
                    </span>
                  </td>
                ))}
                <td style={{ textAlign: "right" }}>{g.trapped && <span className="tag trap">trap</span>}</td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr>
                <td colSpan={slices.length + 3} className="muted small">
                  No gene matches. The system would refuse to guess, and so will this page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
