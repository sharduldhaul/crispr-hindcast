"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

export interface TimelineGene {
  symbol: string;
  date: string;
  core: boolean;
}

interface Props {
  genes: TimelineGene[];
  slices: readonly string[];
  initialCutoff: string;
  /** Let the reader drag the cutoff to any year, not only the three slices. */
  free?: boolean;
}

const START = 2000;
const END = 2025;
const W = 1000;
const PAD_L = 70;
const PAD_R = 20;
const ROW = 22;
const AXIS_GAP = 30;

function toYear(date: string): number {
  const d = new Date(date);
  const start = new Date(d.getFullYear(), 0, 1).getTime();
  const end = new Date(d.getFullYear() + 1, 0, 1).getTime();
  return d.getFullYear() + (d.getTime() - start) / (end - start);
}

function x(year: number): number {
  const clamped = Math.max(START, Math.min(END, year));
  return PAD_L + ((clamped - START) / (END - START)) * (W - PAD_L - PAD_R);
}

export function CutoffTimeline({ genes, slices, initialCutoff, free = false }: Props) {
  const [cutoff, setCutoff] = useState(toYear(initialCutoff) + 0.001);

  const { placed, earlier, rows } = useMemo(() => {
    const sorted = [...genes].sort((a, b) => a.date.localeCompare(b.date));
    const earlier = sorted.filter((g) => toYear(g.date) < START);
    const rest = sorted.filter((g) => toYear(g.date) >= START);
    // Greedy row packing so labels never overlap.
    const rowEnds: number[] = [];
    const placed = rest.map((g) => {
      const cx = x(toYear(g.date));
      const width = g.symbol.length * 7.2 + 14;
      const left = cx - 5;
      let row = rowEnds.findIndex((end) => end < left);
      if (row === -1) {
        row = rowEnds.length;
        rowEnds.push(0);
      }
      rowEnds[row] = left + width;
      return { ...g, cx, row, width, year: toYear(g.date) };
    });
    return { placed, earlier, rows: Math.max(rowEnds.length, 1) };
  }, [genes]);

  const H = rows * ROW + AXIS_GAP + 40;
  const axisY = H - 34;
  const cx = x(cutoff);
  const known = genes.filter((g) => toYear(g.date) < cutoff).length;
  const sealed = genes.length - known;
  const activeSlice = slices.find((s) => Math.abs(toYear(s) + 0.001 - cutoff) < 0.01);

  return (
    <figure style={{ margin: 0 }}>
      <div
        style={{
          display: "flex",
          gap: 16,
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          marginBottom: 14,
        }}
      >
        <div className="segmented" role="group" aria-label="Choose a cutoff date">
          {slices.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={activeSlice === s}
              onClick={() => setCutoff(toYear(s) + 0.001)}
            >
              Cutoff {s.slice(0, 4)}
            </button>
          ))}
        </div>
        <div className="small" style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
          <span>
            <b style={{ color: "var(--ink)" }}>{known}</b>{" "}
            <span className="muted">known before the cutoff</span>
          </span>
          <span>
            <b style={{ color: "var(--future)" }}>{sealed}</b>{" "}
            <span className="muted">sealed: the answer key</span>
          </span>
        </div>
      </div>

      {free && (
        <label className="small muted" style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 10 }}>
          <span style={{ whiteSpace: "nowrap" }}>Drag the cutoff</span>
          <input
            type="range"
            min={START}
            max={END}
            step={0.25}
            value={cutoff}
            onChange={(e) => setCutoff(Number(e.target.value))}
            style={{ flex: 1, accentColor: "var(--accent)" }}
            aria-label="Cutoff year"
          />
          <span className="mono" style={{ color: "var(--accent)", minWidth: 40 }}>
            {Math.floor(cutoff)}
          </span>
        </label>
      )}

      <div style={{ overflowX: "auto", border: "1px solid var(--rule)", borderRadius: 3, background: "var(--paper)" }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: "block", width: "100%", minWidth: 720, height: "auto" }}
          role="img"
          aria-label={`Timeline of when the field established each gene. ${known} were known before the cutoff and ${sealed} came after it.`}
        >
          <defs>
            <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="7" stroke="var(--future)" strokeWidth="1" opacity="0.22" />
            </pattern>
          </defs>

          {/* the sealed future */}
          <rect
            x={cx}
            y={0}
            width={Math.max(0, W - PAD_R - cx)}
            height={axisY}
            fill="url(#hatch)"
            style={{ transition: "x 300ms ease, width 300ms ease" }}
          />

          {/* axis */}
          <line x1={PAD_L} x2={W - PAD_R} y1={axisY} y2={axisY} stroke="var(--ink)" strokeWidth="1" />
          {Array.from({ length: END - START + 1 }, (_, i) => START + i).map((yr) => (
            <g key={yr}>
              <line
                x1={x(yr)}
                x2={x(yr)}
                y1={axisY}
                y2={axisY + (yr % 5 === 0 ? 7 : 3)}
                stroke="var(--ink)"
                strokeWidth="1"
              />
              {yr % 5 === 0 && (
                <text
                  x={x(yr)}
                  y={axisY + 22}
                  textAnchor="middle"
                  fontSize="12"
                  fill="var(--muted)"
                  fontFamily="var(--font-mono)"
                >
                  {yr}
                </text>
              )}
            </g>
          ))}

          {/* genes established before 2000 */}
          <g>
            <text x={8} y={axisY - 10} fontSize="11" fill="var(--muted)" fontFamily="var(--font-mono)">
              earlier
            </text>
            <text x={8} y={axisY - 26} fontSize="15" fill="var(--ink)" fontFamily="var(--font-display)">
              +{earlier.length}
            </text>
            <title>{earlier.map((g) => g.symbol).join(", ")}</title>
          </g>

          {/* genes */}
          {placed.map((g) => {
            const future = g.year >= cutoff;
            const y = axisY - AXIS_GAP + 6 - g.row * ROW;
            return (
              <Link key={g.symbol} href={`/genes/${g.symbol}`}>
                <g style={{ cursor: "pointer" }}>
                  <title>
                    {`${g.symbol}: first established ${g.date}${future ? " (after the cutoff: hidden from the system)" : " (before the cutoff: visible)"}`}
                  </title>
                  <line
                    x1={g.cx}
                    x2={g.cx}
                    y1={y + 4}
                    y2={axisY}
                    stroke={future ? "var(--future)" : "var(--ink)"}
                    strokeWidth="1"
                    opacity={0.25}
                  />
                  <circle
                    cx={g.cx}
                    cy={y}
                    r={g.core ? 4 : 3}
                    fill={future ? "var(--paper)" : g.core ? "var(--accent)" : "var(--ink)"}
                    stroke={future ? "var(--future)" : "none"}
                    strokeWidth="1.3"
                  />
                  <text
                    x={g.cx + 8}
                    y={y + 4}
                    fontSize="12"
                    fontFamily="var(--font-mono)"
                    fontWeight={g.core ? 600 : 400}
                    fill={future ? "var(--future)" : "var(--ink)"}
                    style={{ transition: "fill 250ms ease" }}
                  >
                    {g.symbol}
                  </text>
                </g>
              </Link>
            );
          })}

          {/* the cutoff itself */}
          <g style={{ transform: `translateX(${cx}px)`, transition: "transform 300ms cubic-bezier(.2,.7,.2,1)" }}>
            <line x1={0} x2={0} y1={4} y2={axisY + 8} stroke="var(--accent)" strokeWidth="2" />
            <rect x={-26} y={0} width={52} height={18} fill="var(--accent)" rx="2" />
            <text x={0} y={13} textAnchor="middle" fontSize="11" fill="var(--paper)" fontFamily="var(--font-mono)" fontWeight="600">
              T {Math.floor(cutoff)}
            </text>
          </g>
        </svg>
      </div>
      <figcaption className="small muted" style={{ marginTop: 10 }}>
        Each label is a gene and the date a publication first established its role in fetal
        hemoglobin, from the frozen answer key. Solid means the system could see it; outlined and
        hatched means it was sealed away. Red dots are the core genes of the field. Click any gene.
      </figcaption>
    </figure>
  );
}
