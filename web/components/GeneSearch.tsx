"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { GeneIndexEntry } from "@/lib/repo";

type Filter = "all" | "forecast" | "truth" | "trap";

export function GeneSearch({ genes }: { genes: GeneIndexEntry[] }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

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

  const filters: [Filter, string][] = [
    ["all", "All"],
    ["forecast", "Ever predicted"],
    ["truth", "In an answer key"],
    ["trap", "Used as a trap"],
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center", marginBottom: 22 }}>
        <input
          type="search"
          placeholder="Search a gene symbol, e.g. BCL11A"
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
        <span className="small muted">{shown.length} genes</span>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 190px), 1fr))", gap: 10 }}>
        {shown.map((g) => (
          <Link
            key={g.symbol}
            href={`/genes/${g.symbol}`}
            className="card"
            style={{
              padding: "12px 14px",
              borderLeft: `3px solid ${g.forecastAt.length ? "var(--accent)" : g.groundTruthAt.length ? "var(--future)" : "var(--rule)"}`,
            }}
          >
            <div className="mono" style={{ fontWeight: 600 }}>
              {g.symbol}
            </div>
            <div className="small muted" style={{ lineHeight: 1.4, marginTop: 2 }}>
              {g.established ? `established ${g.established.slice(0, 4)}` : "not established"}
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 8 }}>
              {g.forecastAt.length > 0 && <span className="tag bad">predicted</span>}
              {g.groundTruthAt.length > 0 && <span className="tag future">answer key</span>}
              {g.trapped && <span className="tag warn">trap</span>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
