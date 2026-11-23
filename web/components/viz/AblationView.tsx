"use client";

import * as d3 from "d3";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { rate } from "@/lib/format";
import type { Rate } from "@/lib/types";

import { C, DUR, EASE, EASE_IN_OUT, halo, ms, styleAxis, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export type MetricKey = "forecast" | "p5" | "mrr" | "traps" | "ece";

export interface AblationRow {
  ablation: string;
  plain: string;
  values: Record<MetricKey, number | null> | null;
  /** The counts behind the traps share, so the table can give its denominator. */
  judgementTraps: Rate | null;
}

interface Metric {
  key: MetricKey;
  label: string;
  hint: string;
  title: string;
  fmt: (v: number) => string;
  /** +1 if higher is better, -1 if lower is better, 0 if neither. */
  better: 1 | -1 | 0;
}

const METRICS: Metric[] = [
  { key: "p5", label: "P@5", hint: "higher is better", title: "Correct in the top five, ranked by confidence", fmt: (v) => v.toFixed(2), better: 1 },
  { key: "mrr", label: "MRR", hint: "higher is better", title: "Mean reciprocal rank: 1.0 means the top pick was right", fmt: (v) => v.toFixed(3), better: 1 },
  { key: "traps", label: "Judgement traps passed", hint: "higher is better", title: "Share of judgement traps passed", fmt: (v) => `${Math.round(v * 100)}%`, better: 1 },
  { key: "ece", label: "ECE", hint: "lower is better", title: "Expected calibration error", fmt: (v) => v.toFixed(3), better: -1 },
  { key: "forecast", label: "Forecast", hint: "bigger is not better", title: "Genes put forward", fmt: (v) => String(v), better: 0 },
];

// Differences smaller than this are rounding, not effect.
const EPS = 0.002;

function tone(m: Metric, v: number | null, base: number | null): "better" | "worse" | "same" {
  if (v === null || base === null || Math.abs(v - base) <= EPS || m.better === 0) return "same";
  return (v - base) * m.better > 0 ? "better" : "worse";
}

function signed(m: Metric, d: number): string {
  if (Math.abs(d) <= EPS) return "same";
  return `${d > 0 ? "+" : "−"}${m.key === "traps" ? `${Math.round(Math.abs(d) * 100)}%` : m.fmt(Math.abs(d))}`;
}

function effect(row: AblationRow, base: AblationRow | undefined): { label: string; tone: string } {
  if (row.ablation === "full system") return { label: "Reference", tone: "plain" };
  if (row.ablation === "no graph") return { label: "Baseline to beat", tone: "future" };
  if (!row.values || !base?.values) return { label: "—", tone: "plain" };
  const changed = METRICS.some((m) => {
    const a = row.values![m.key];
    const b = base.values![m.key];
    return a !== null && b !== null && Math.abs(a - b) > EPS;
  });
  if (!changed) return { label: "No measurable effect", tone: "plain" };
  return METRICS.some((m) => tone(m, row.values![m.key], base.values![m.key]) === "worse")
    ? { label: "Removing it hurts", tone: "bad" }
    : { label: "Mixed", tone: "warn" };
}

export function AblationView({
  byCutoff,
  slices,
  initial,
  primary,
}: {
  byCutoff: Record<string, AblationRow[]>;
  slices: readonly string[];
  initial: string;
  primary: string;
}) {
  const [cutoff, setCutoff] = useState(initial);
  const rows = byCutoff[cutoff] ?? [];
  const base = rows.find((r) => r.ablation === "full system");

  // Fixed scales across cutoffs, so a dot that moves has really changed.
  const domains = useMemo(() => {
    const all = Object.values(byCutoff).flat();
    const max = (k: MetricKey) => d3.max(all, (r) => r.values?.[k] ?? 0) ?? 1;
    return {
      p5: [0, 1],
      mrr: [0, 1],
      traps: [0, 1],
      ece: [0, Math.max(0.3, max("ece") * 1.15)],
      forecast: [0, max("forecast") * 1.08],
    } as Record<MetricKey, [number, number]>;
  }, [byCutoff]);

  function choose(s: string) {
    setCutoff(s);
    window.history.replaceState(null, "", `?cutoff=${s}`);
  }

  return (
    <>
      <div className="segmented lg" role="group" aria-label="Cutoff" style={{ marginTop: 28 }}>
        {slices.map((s) => (
          <button key={s} type="button" aria-pressed={s === cutoff} onClick={() => choose(s)}>
            {s.slice(0, 4)}
          </button>
        ))}
      </div>

      <section style={{ marginTop: 28 }}>
        <AblationDots rows={rows} domains={domains} />
        <p className="viz-hint" style={{ marginTop: 12 }}>
          The vertical line in each column is the full system. Every other variant is joined to it:{" "}
          <span style={{ color: "var(--ok)" }}>green</span> where removing the part helped, <span style={{ color: "var(--bad)" }}>red</span>{" "}
          where it hurt, no line where nothing changed. Switch the cutoff and watch them move; click a column to open it.
        </p>
      </section>

      <section style={{ marginTop: 36 }}>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Ablations">
          <table>
            <thead>
              <tr>
                <th>Variant</th>
                {METRICS.map((m) => (
                  <th key={m.key} className="num" title={m.title}>
                    {m.label}
                  </th>
                ))}
                <th>Effect</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const fx = row.values ? effect(row, base) : null;
                return (
                  <tr key={row.ablation}>
                    <td style={{ minWidth: 250 }}>
                      <Link
                        href={`/slices/${cutoff}${row.ablation === "full system" ? "" : `?ablation=${encodeURIComponent(row.ablation)}`}`}
                        style={{ fontWeight: 600, textDecoration: "none" }}
                      >
                        {row.ablation}
                      </Link>
                      <div className="small muted" style={{ lineHeight: 1.45, marginTop: 2 }}>
                        {row.plain}
                      </div>
                    </td>
                    {row.values ? (
                      <>
                        {METRICS.map((m) => {
                          const v = row.values![m.key];
                          const b = base?.values?.[m.key] ?? null;
                          return (
                            <td key={m.key} className="num">
                              {v === null ? "n/a" : m.key === "traps" && row.judgementTraps ? rate(row.judgementTraps, "n/a") : m.fmt(v)}
                              {row.ablation !== "full system" && v !== null && b !== null && (
                                <span className={`delta ${tone(m, v, b)}`}>{signed(m, v - b)}</span>
                              )}
                            </td>
                          );
                        })}
                        <td>{fx && <span className={`tag ${fx.tone}`}>{fx.label}</span>}</td>
                      </>
                    ) : (
                      <td colSpan={METRICS.length + 1} className="small muted">
                        not run
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          Deltas are against the full system. P@5 and MRR use the confidence ranking. Open a variant to see its full forecast.
        </p>
      </section>

      {cutoff === primary && (
        <section style={{ marginTop: 40 }}>
          <div className="callout neutral" style={{ maxWidth: "80ch" }}>
            <p>
              <b>What the primary slice shows.</b> Belief revision carries the result: without it the forecast is empty and every decoy
              slips through. The no-graph baseline, which just counts papers, names sixty genes and finds its first right answer far down
              the list. Removing the method signature or name normalization changes nothing, because the pre-2018 data holds no
              functional fetal hemoglobin measurement for them to weigh.
            </p>
          </div>
        </section>
      )}
    </>
  );
}

const MIN_W = 760;
const LABEL_W = 184;
const ROW = 30;
const TOP = 54;
const BOTTOM = 34;
// An opened column takes this share of the plot; the rest share what is left.
const OPEN_SHARE = 0.46;
const SHORT: Record<MetricKey, string> = { p5: "P@5", mrr: "MRR", traps: "Traps", ece: "ECE", forecast: "Genes" };
// A header starts 14px into its column and keeps this much clear before the
// next column's separator.
const HEAD_PAD = 22;
// Tick labels are 11px monospace, about this wide per character, and keep
// this gap between neighbours.
const TICK_CHAR = 6.6;
const TICK_GAP = 12;
// A value label that would sit on its own link line rises this far above the
// row instead.
const LIFT = 14;

/** The densest ticks, up to `wanted`, whose labels do not touch. */
function fittingTicks(x: d3.ScaleLinear<number, number>, fmt: (v: number) => string, wanted: number): number[] {
  for (let n = wanted; n >= 1; n--) {
    const ticks = x.ticks(n);
    const clear = ticks.every(
      (v, k) => k === 0 || x(v) - x(ticks[k - 1]) >= ((fmt(v).length + fmt(ticks[k - 1]).length) * TICK_CHAR) / 2 + TICK_GAP,
    );
    if (clear) return ticks;
  }
  return x.domain();
}

interface Dot {
  id: string;
  metric: Metric;
  col: number;
  ablation: string;
  value: number;
  base: number | null;
  tone: "better" | "worse" | "same";
}

/**
 * Small multiples sharing one set of rows: each column is a metric on its own
 * scale, each row a variant. Dots are keyed by metric and variant, so a
 * cutoff switch moves them rather than redrawing them. Click a column to open
 * it: it widens, gains finer ticks and prints every value, and the others
 * narrow to make room.
 */
function AblationDots({ rows, domains }: { rows: AblationRow[]; domains: Record<MetricKey, [number, number]> }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [open, setOpen] = useState<MetricKey | null>(null);
  const H = TOP + rows.length * ROW + BOTTOM;

  const layout = useMemo(() => {
    if (!width) return null;
    const W = Math.max(width, MIN_W);
    const plotW = W - LABEL_W;
    const oi = open ? METRICS.findIndex((m) => m.key === open) : -1;
    const widths = METRICS.map((_, i) =>
      oi < 0 ? plotW / METRICS.length : i === oi ? plotW * OPEN_SHARE : (plotW * (1 - OPEN_SHARE)) / (METRICS.length - 1),
    );
    const x0s = widths.map((_, i) => LABEL_W + d3.sum(widths.slice(0, i)));
    // An opened column also zooms its scale to this cutoff's values, so the
    // detail packed into a few pixels spreads out. Closed columns keep one
    // scale across cutoffs, so a dot that moves there has really moved; an
    // opened one's axis rescales visibly when the cutoff changes.
    const xs = METRICS.map((m, i) => {
      const s = d3.scaleLinear().range([x0s[i] + 14, x0s[i] + widths[i] - 20]);
      if (i !== oi) return s.domain(domains[m.key]);
      const values = rows.map((r) => r.values?.[m.key]).filter((v): v is number => v !== null && v !== undefined);
      const [lo, hi] = (d3.extent(values) as [number, number]) ?? domains[m.key];
      const pad = Math.max((hi - lo) * 0.6, m.key === "forecast" ? 2 : 0.01);
      return s.domain([Math.max(domains[m.key][0], lo - pad), Math.min(domains[m.key][1], hi + pad)]).nice();
    });
    const y = d3
      .scaleBand<string>()
      .domain(rows.map((r) => r.ablation))
      .range([TOP, TOP + rows.length * ROW]);
    return { W, widths, x0s, xs, y, oi };
  }, [width, domains, open, rows]);

  // ---- frame: drawn once per width ----
  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, y } = layout;
    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();
    const names = rows.map((r) => r.ablation);

    svg
      .append("g")
      .selectAll("line")
      .data(names)
      .join("line")
      .attr("x1", LABEL_W - 8)
      .attr("x2", W)
      .attr("y1", (d) => y(d)! + ROW / 2)
      .attr("y2", (d) => y(d)! + ROW / 2)
      .style("stroke", C.grid);
    svg
      .append("g")
      .selectAll("text")
      .data(names)
      .join("text")
      .attr("x", LABEL_W - 16)
      .attr("y", (d) => y(d)! + ROW / 2 + 4)
      .attr("text-anchor", "end")
      .attr("font-size", 12.5)
      .attr("font-weight", (d) => (d === "full system" ? 600 : 400))
      .style("fill", (d) => (d === "full system" ? C.ink : C.ink2))
      .text((d) => d);

    const head = svg
      .append("g")
      .selectAll<SVGGElement, Metric>("g")
      .data(METRICS, (m) => m.key)
      .join("g")
      .attr("class", "col-head")
      .attr("role", "button")
      .attr("tabindex", 0)
      .style("cursor", "pointer")
      .style("outline", "none")
      .on("click", (_e: Event, m) => setOpen((o) => (o === m.key ? null : m.key)))
      .on("keydown", (event: KeyboardEvent, m) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setOpen((o) => (o === m.key ? null : m.key));
        } else if (event.key === "Escape") setOpen(null);
      });
    head.append("rect").attr("class", "hit").attr("x", -14).attr("y", 0).attr("height", TOP - 8).attr("fill", "transparent");
    const title = head.append("text").attr("class", "title").attr("y", 18).attr("font-size", 13.5).attr("font-weight", 600).style("fill", C.ink);
    title.append("tspan").attr("class", "name");
    title.append("tspan").attr("class", "glyph").attr("dx", 6).attr("font-weight", 400).style("fill", C.gold);
    head.append("text").attr("class", "hint").attr("y", 35).attr("font-size", 11).style("fill", C.muted);
    head.append("title").text((m) => m.title);
    svg
      .append("g")
      .selectAll("line")
      .data(METRICS.slice(1), (m) => (m as Metric).key)
      .join("line")
      .attr("class", "sep")
      .attr("y1", 4)
      .attr("y2", H - 10)
      .style("stroke", C.grid);
    svg
      .append("g")
      .selectAll("g")
      .data(METRICS, (m) => (m as Metric).key)
      .join("g")
      .attr("class", "col-axis")
      .attr("transform", `translate(0,${TOP + rows.length * ROW + 6})`);
    svg.append("g").attr("class", "refs");
    svg.append("g").attr("class", "links");
    svg.append("g").attr("class", "dots");
    svg.append("g").attr("class", "values").attr("pointer-events", "none");
    entered.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout?.W, inView]);

  // ---- columns and values: enter on first view, glide on every cutoff switch or opened column ----
  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { xs, y, widths, x0s, oi } = layout;
    const svg = d3.select(svgRef.current);
    const entering = !entered.current;
    entered.current = true;
    const t = d3
      .transition()
      .duration(ms(entering ? DUR.enter + 300 : DUR.update + 150))
      .ease(entering ? EASE : EASE_IN_OUT);

    // headers, separators and axes follow the column widths
    const head = svg.selectAll<SVGGElement, Metric>(".col-head").attr("aria-expanded", (m) => String(open === m.key));
    head
      .attr("aria-label", (m) => `${m.label}: ${m.title}. ${open === m.key ? "Press Enter to close." : "Press Enter to open."}`)
      .select(".hit")
      .attr("width", (_, i) => widths[i]);
    head.select(".glyph").text((m) => (open === m.key ? "⊖" : "⊕"));
    head.select(".hint").text((m) => m.hint);
    // Names and hints are measured, not guessed from the column width, so a
    // long name never runs into the next column's header.
    const fits = (el: SVGTextElement | null, i: number) => el !== null && el.getComputedTextLength() <= widths[i] - HEAD_PAD;
    head.each(function (m, i) {
      const g = d3.select(this);
      g.select(".name").text(m.label);
      if (!fits(g.select<SVGTextElement>(".title").node(), i)) g.select(".name").text(SHORT[m.key]);
      g.select(".hint")
        .transition(t)
        .attr("opacity", fits(g.select<SVGTextElement>(".hint").node(), i) ? 1 : 0);
    });
    if (entering) head.attr("transform", (_, i) => `translate(${x0s[i] + 14},0)`);
    head.transition(t).attr("transform", (_, i) => `translate(${x0s[i] + 14},0)`);
    svg
      .selectAll<SVGLineElement, Metric>(".sep")
      .transition(t)
      .attr("x1", (m) => x0s[METRICS.indexOf(m)])
      .attr("x2", (m) => x0s[METRICS.indexOf(m)]);
    svg.selectAll<SVGGElement, Metric>(".col-axis").each(function (m, i) {
      const g = d3.select(this);
      const fmt = (v: number) => (m.key === "traps" ? `${Math.round(v * 100)}%` : d3.format("~g")(v));
      const axis = d3
        .axisBottom(xs[i])
        .tickValues(fittingTicks(xs[i], fmt, i === oi ? 6 : 3))
        .tickFormat((v) => fmt(+v))
        .tickSizeOuter(0);
      (entering ? g : g.transition(t)).call(axis as never);
      styleAxis(g);
    });

    const baseRow = rows.find((r) => r.ablation === "full system");
    const dots: Dot[] = METRICS.flatMap((m, col) =>
      rows
        .filter((r) => r.values?.[m.key] !== null && r.values?.[m.key] !== undefined)
        .map((r) => {
          const value = r.values![m.key]!;
          const base = baseRow?.values?.[m.key] ?? null;
          return { id: `${m.key}|${r.ablation}`, metric: m, col, ablation: r.ablation, value, base, tone: tone(m, value, base) };
        }),
    );
    const cy = (d: Dot) => y(d.ablation)! + ROW / 2;
    const color = (d: Dot) => (d.tone === "better" ? C.hit : d.tone === "worse" ? C.fail : C.muted);
    const refs = METRICS.map((m, col) => ({ col, value: baseRow?.values?.[m.key] ?? null })).filter((r) => r.value !== null);

    svg
      .select(".refs")
      .selectAll<SVGLineElement, (typeof refs)[number]>("line")
      .data(refs, (d) => String(d.col))
      .join((enter) =>
        enter
          .append("line")
          .attr("x1", (d) => xs[d.col](d.value!))
          .attr("x2", (d) => xs[d.col](d.value!))
          .attr("y1", TOP)
          .attr("y2", TOP)
          .style("stroke", C.gold)
          .attr("stroke-width", 1.5),
      )
      .transition(t)
      .attr("x1", (d) => xs[d.col](d.value!))
      .attr("x2", (d) => xs[d.col](d.value!))
      .attr("y2", TOP + rows.length * ROW);

    svg
      .select(".links")
      .selectAll<SVGLineElement, Dot>("line")
      .data(
        dots.filter((d) => d.ablation !== "full system" && d.base !== null),
        (d) => d.id,
      )
      .join((enter) =>
        enter
          .append("line")
          .attr("x1", (d) => xs[d.col](d.base!))
          .attr("x2", (d) => xs[d.col](d.base!))
          .attr("y1", cy)
          .attr("y2", cy)
          .attr("stroke-width", 2.5)
          .attr("stroke-linecap", "round"),
      )
      .transition(t)
      .attr("x1", (d) => xs[d.col](d.base!))
      .attr("x2", (d) => xs[d.col](d.value))
      .style("stroke", color)
      .attr("opacity", (d) => (d.tone === "same" ? 0 : 0.8));

    const dot = svg
      .select(".dots")
      .selectAll<SVGGElement, Dot>("g")
      .data(dots, (d) => d.id)
      .join((enter) => {
        const g = enter
          .append("g")
          .attr("tabindex", 0)
          .attr("role", "img")
          .style("outline", "none")
          .style("cursor", "pointer")
          .attr("transform", (d) => `translate(${xs[d.col].range()[0]},${cy(d)})`);
        g.append("rect").attr("x", -12).attr("y", -13).attr("width", 24).attr("height", 26).attr("fill", "transparent");
        g.append("circle").attr("r", 6).attr("stroke-width", 2).style("stroke", C.surface);
        return g;
      });
    dot.attr("aria-label", (d) => `${d.metric.label}, ${d.ablation}: ${d.metric.fmt(d.value)}`);
    dot
      .select("circle")
      .transition(t)
      .style("fill", (d) => (d.ablation === "full system" ? C.gold : d.tone === "same" ? C.ink2 : color(d)));
    dot
      .transition(t)
      .delay((d) => (entering ? ms(d.col * 90 + rows.findIndex((r) => r.ablation === d.ablation) * 40) : 0))
      .attr("transform", (d) => `translate(${xs[d.col](d.value)},${cy(d)})`);

    // The opened column prints every value beside its dot, on the side away
    // from the full system's line, unless that runs out of the column. A
    // label pushed back onto the side of its link line would sit on the line,
    // so it rises above the row and reads along it.
    const opened = oi < 0 ? [] : dots.filter((d) => d.col === oi);
    const labelLeft = (d: Dot) => {
      const [r0, r1] = xs[d.col].range();
      const px = xs[d.col](d.value);
      const left = d.base !== null && d.value < d.base - EPS;
      return left ? px - 100 > r0 : px + 100 > r1;
    };
    const lifted = (d: Dot) => d.tone !== "same" && d.base !== null && labelLeft(d) === d.value > d.base;
    const labelX = (d: Dot) => xs[d.col](d.value) + (lifted(d) ? (labelLeft(d) ? 4 : -4) : labelLeft(d) ? -11 : 11);
    svg
      .select(".values")
      .selectAll<SVGTextElement, Dot>("text")
      .data(opened, (d) => d.id)
      .join(
        (enter) =>
          enter
            .append("text")
            .attr("font-size", 11)
            .attr("font-family", "var(--font-mono)")
            .attr("dy", "0.35em")
            .attr("opacity", 0)
            .attr("x", (d) => xs[d.col](d.value))
            .attr("y", cy)
            .call((e) => halo(e, 3)),
        (update) => update,
        (exit) => exit.transition().duration(ms(DUR.exit)).attr("opacity", 0).remove(),
      )
      .style("fill", (d) => (d.ablation === "full system" ? C.gold : C.ink2))
      .attr("text-anchor", (d) => (labelLeft(d) ? "end" : "start"))
      .text((d) =>
        d.ablation === "full system" || d.base === null || d.tone === "same" ? d.metric.fmt(d.value) : `${d.metric.fmt(d.value)}  ${signed(d.metric, d.value - d.base)}`,
      )
      .transition(t)
      .attr("x", labelX)
      .attr("y", (d) => cy(d) - (lifted(d) ? LIFT : 0))
      .attr("opacity", 1);

    dot
      .on("click", (_e: Event, d) => setOpen((o) => (o === d.metric.key ? null : d.metric.key)))
      .on("pointerenter focus", (_e: Event, d) => {
        dot.transition("dim").duration(ms(DUR.hover)).attr("opacity", (o) => (o.ablation === d.ablation || o.col === d.col ? 1 : 0.3));
        setTip({
          x: xs[d.col](d.value),
          y: cy(d),
          value: d.metric.fmt(d.value),
          label: `${d.metric.label} · ${d.ablation}`,
          rows:
            d.ablation === "full system" || d.base === null
              ? undefined
              : [
                  { color: C.gold, label: "full system", value: d.metric.fmt(d.base) },
                  { color: color(d), label: "change", value: signed(d.metric, d.value - d.base) },
                ],
          note: open === d.metric.key ? "Click to close this column." : "Click to open this column.",
        });
      })
      .on("pointerleave blur", () => {
        dot.transition("dim").duration(ms(DUR.hover)).attr("opacity", 1);
        setTip(null);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, rows]);

  return (
    <div className="viz-frame" style={{ ["--min-w" as string]: `${MIN_W}px`, padding: "14px 0 6px" }}>
      <div className="viz" ref={wrapRef} style={{ minHeight: H }}>
        <svg ref={svgRef} role="group" aria-label="Each variant on each metric, joined to the full system; the table below lists the same values." />
        <Tooltip tip={tip} />
      </div>
    </div>
  );
}
