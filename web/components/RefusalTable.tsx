"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Meter } from "./Charts";

interface Row {
  gene_symbol: string;
  confidence: number;
  evidence_count: number;
  foundLater: boolean;
}

// Every refusal has the same reason, "confidence below the threshold", so the
// table shows what varies: how far below, and on how much evidence.
export function RefusalTable({ rows, threshold }: { rows: Row[]; threshold: number }) {
  const [query, setQuery] = useState("");
  const [onlyFound, setOnlyFound] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    return rows
      .filter((r) => (!q || r.gene_symbol.includes(q)) && (!onlyFound || r.foundLater))
      .sort((a, b) => b.confidence - a.confidence);
  }, [rows, query, onlyFound]);

  return (
    <div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
        <input type="search" placeholder="Filter genes" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter refusals" />
        <div className="segmented" role="group" aria-label="Show">
          <button type="button" aria-pressed={!onlyFound} onClick={() => setOnlyFound(false)}>
            All {rows.length}
          </button>
          <button type="button" aria-pressed={onlyFound} onClick={() => setOnlyFound(true)}>
            Found later {rows.filter((r) => r.foundLater).length}
          </button>
        </div>
      </div>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Refusals">
        <table>
          <thead>
            <tr>
              <th>Gene</th>
              <th style={{ minWidth: 200 }}>Confidence</th>
              <th className="num">Short by</th>
              <th className="num">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.gene_symbol} className={r.foundLater ? "highlight" : undefined}>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Link className="gene" href={`/genes/${r.gene_symbol}`}>
                    {r.gene_symbol}
                  </Link>
                  {r.foundLater && (
                    <span className="tag future" style={{ marginLeft: 8 }}>
                      found later
                    </span>
                  )}
                </td>
                <td>
                  <div className="meter-row">
                    <Meter value={r.confidence} threshold={threshold} />
                    <span className="mono small">{r.confidence.toFixed(3)}</span>
                  </div>
                </td>
                <td className="num">{(threshold - r.confidence).toFixed(3)}</td>
                <td className="num">{r.evidence_count}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="muted small">
                  Nothing matches.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
