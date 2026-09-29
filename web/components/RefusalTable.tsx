"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Meter } from "./Charts";

interface Row {
  gene_symbol: string;
  confidence: number;
  evidence_count: number;
  reason: string;
  foundLater: boolean;
}

export function RefusalTable({ rows, threshold }: { rows: Row[]; threshold: number }) {
  const [query, setQuery] = useState("");
  const [onlyFound, setOnlyFound] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    return rows
      .filter((r) => (!q || r.gene_symbol.includes(q) || r.reason.toUpperCase().includes(q)) && (!onlyFound || r.foundLater))
      .sort((a, b) => b.confidence - a.confidence);
  }, [rows, query, onlyFound]);

  return (
    <div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
        <input
          type="search"
          placeholder="Filter by gene or reason…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter refusals"
        />
        <label className="small" style={{ display: "flex", gap: 8, alignItems: "center", cursor: "pointer" }}>
          <input type="checkbox" checked={onlyFound} onChange={(e) => setOnlyFound(e.target.checked)} style={{ accentColor: "var(--accent)" }} />
          Only genes the field found later
        </label>
        <span className="small muted" style={{ marginLeft: "auto" }}>
          {filtered.length} of {rows.length}
        </span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Gene</th>
              <th style={{ minWidth: 150 }}>Confidence</th>
              <th className="num">Evidence</th>
              <th>Why it was refused</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.gene_symbol} className={r.foundLater ? "highlight" : undefined}>
                <td>
                  <Link className="gene" href={`/genes/${r.gene_symbol}`}>
                    {r.gene_symbol}
                  </Link>
                  {r.foundLater && (
                    <div style={{ marginTop: 4 }}>
                      <span className="tag future">found later</span>
                    </div>
                  )}
                </td>
                <td>
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <Meter value={r.confidence} threshold={threshold} />
                    <span className="mono small">{r.confidence.toFixed(3)}</span>
                  </div>
                </td>
                <td className="num">{r.evidence_count}</td>
                <td className="small" style={{ color: "var(--ink-2)", minWidth: 280 }}>
                  {r.reason}
                </td>
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
