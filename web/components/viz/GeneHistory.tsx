"use client";

import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";

import { fractionalYear, longDate } from "@/lib/format";
import type { VerdictKind } from "@/lib/types";

import { C, DUR, EASE, OUTCOME, drawIn, fmt, focusFrame, halo, ms, styleAxis, useChart, yearAxis } from "./core";
import { Tooltip } from "./Tooltip";
import { ZoomBar } from "./ZoomBar";

export interface HistoryMark {
  cutoff: string;
  kind: VerdictKind;
  confidence: number | null;
  detail: string;
}

export interface HistoryPub {
  date: string;
  title: string;
  pmid: string | null;
  role: "established" | "near" | "rejected";
  why: string | null;
}

const MIN_W = 600;
const M = { top: 34, right: 28, left: 46 };
const PLOT_H = 170;
const AXIS_Y = M.top + PLOT_H;
const RUG_H = 26;
const RUG_BASE = AXIS_Y + 46 + RUG_H;
const CTX_TOP = RUG_BASE + 38;
const CTX_H = 22;
const CTX_BASE = CTX_TOP + CTX_H;
const H = CTX_BASE + 24;
const ROLE = {
  established: { h: RUG_H, color: C.sealed, label: "established the gene" },
  near: { h: 17, color: C.ink2, label: "near miss" },
  rejected: { h: 10, color: C.muted, label: "did not count" },
};

type View = "era" | "full" | "custom";

/**
 * One gene through time: the system's confidence at each cutoff against the
 * frozen threshold, the date the field established it, and every candidate
 * publication the rule book weighed along the way. The strip at the bottom is
 * the whole record; drag on it to choose the span the chart above shows.
 */
export function GeneHistory({
  established,
  marks,
  pubs,
  threshold,
}: {
  established: string | null;
  marks: HistoryMark[];
  pubs: HistoryPub[];
  threshold: number;
}) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [view, setView] = useState<View>("era");
  const moveTo = useRef<((v: Exclude<View, "custom">) => void) | null>(null);

  const layout = useMemo(() => {
    if (!width) return null;
    const W = Math.max(width, MIN_W);
    const estYr = established ? fractionalYear(established) : null;
    const cutYrs = marks.map((m) => fractionalYear(m.cutoff));
    const all = [...pubs.map((p) => fractionalYear(p.date)), ...(estYr !== null ? [estYr] : []), ...cutYrs];
    // The whole record: nothing is clamped to an edge.
    const full: [number, number] = [Math.floor(Math.min(2000, d3.min(all) ?? 2000)), Math.max(2026, Math.ceil((d3.max(all) ?? 2025) + 0.25))];
    // The cutoff era: a few years before the first cutoff, or from the year the
    // field found the gene if that came later than 2000.
    const lead = Math.min((d3.min(cutYrs) ?? 2015) - 6, estYr !== null && estYr >= 2000 ? estYr - 1 : Infinity);
    const era: [number, number] = [Math.max(full[0], Math.floor(lead)), full[1]];
    const xC = d3.scaleLinear().domain(full).range([M.left, W - M.right]);
    const top = Math.max(0.5, (d3.max(marks, (m) => m.confidence ?? 0) ?? 0) * 1.15);
    const y = d3.scaleLinear().domain([0, top]).range([AXIS_Y, M.top]).nice();
    const sortedPubs = [...pubs].sort((a, b) => a.date.localeCompare(b.date)).map((p) => ({ ...p, yr: fractionalYear(p.date) }));
    return { W, full, era, xC, y, estYr, sortedPubs };
  }, [width, pubs, marks, established]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, full, era, xC, y, estYr, sortedPubs } = layout;
    const entering = !entered.current;
    entered.current = true;
    const xF = d3.scaleLinear().domain(era).range([M.left, W - M.right]);
    const inPlot = (px: number) => px >= M.left - 0.5 && px <= W - M.right + 0.5;

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    // Lines and ticks are clipped to the plot exactly; dots get a few pixels
    // more, so one sitting on the edge is not cut in half.
    const defs = svg.append("defs");
    for (const [id, pad] of [
      ["gh-clip", 0],
      ["gh-clip-pad", 9],
    ] as const) {
      defs
        .append("clipPath")
        .attr("id", id)
        .append("rect")
        .attr("x", M.left - pad)
        .attr("y", 0)
        .attr("width", W - M.left - M.right + 2 * pad)
        .attr("height", RUG_BASE + 2);
    }
    const under = svg.append("g").attr("clip-path", "url(#gh-clip)");

    // the window in which the system could have foreseen it
    const windowRect = under
      .append("rect")
      .attr("x", M.left)
      .attr("y", M.top - 18)
      .attr("height", AXIS_Y - M.top + 18)
      .attr("width", 0)
      .style("fill", C.sealed)
      .attr("opacity", 0.07);
    const windowLabel = svg
      .append("text")
      .attr("x", M.left + 10)
      .attr("y", M.top - 4)
      .attr("font-size", 11)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.sealed)
      .text("window to foresee it");

    svg
      .append("g")
      .selectAll("line")
      .data(y.ticks(3).filter((t) => t > 0))
      .join("line")
      .attr("x1", M.left)
      .attr("x2", W - M.right)
      .attr("y1", (d) => y(d))
      .attr("y2", (d) => y(d))
      .style("stroke", C.grid);
    styleAxis(svg.append("g").attr("transform", `translate(${M.left},0)`).call(d3.axisLeft(y).ticks(3).tickFormat(d3.format(".1f")).tickSizeOuter(0)), {
      domain: false,
    });
    const axis = svg.append("g").attr("transform", `translate(0,${AXIS_Y})`);

    // the frozen threshold
    svg
      .append("line")
      .attr("x1", M.left)
      .attr("x2", entering ? M.left : W - M.right)
      .attr("y1", y(threshold))
      .attr("y2", y(threshold))
      .style("stroke", C.gold)
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "4 4")
      .transition()
      .duration(ms(entering ? 900 : 0))
      .ease(EASE)
      .attr("x2", W - M.right);
    svg
      .append("text")
      .attr("x", W - M.right)
      .attr("y", y(threshold) - 6)
      .attr("text-anchor", "end")
      .attr("font-size", 11)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.gold)
      .text(`threshold ${threshold}`);

    // drawn over the axes
    const over = svg.append("g").attr("clip-path", "url(#gh-clip)");
    const marksG = svg.append("g").attr("clip-path", "url(#gh-clip-pad)");

    // when the field found it; off the edge of the view, an arrow says which way
    const found = over.append("line").attr("y1", M.top - 18).attr("y2", RUG_BASE).style("stroke", C.sealed).attr("stroke-width", 1.5);
    const foundLabel = svg
      .append("text")
      .attr("y", M.top - 22)
      .attr("font-size", 12)
      .attr("font-weight", 600)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.sealed);

    // confidence across cutoffs
    const pts = marks.map((m) => ({ ...m, yr: fractionalYear(m.cutoff), py: m.confidence === null ? AXIS_Y : y(m.confidence) }));
    const scored = pts.filter((p) => p.confidence !== null);
    const line = d3
      .line<(typeof scored)[number]>()
      .y((d) => d.py)
      .curve(d3.curveMonotoneX);
    const path = over.append("path").datum(scored).attr("fill", "none").style("stroke", C.ink2).attr("stroke-width", 1.5);

    const mark = marksG
      .append("g")
      .selectAll<SVGGElement, (typeof pts)[number]>("g")
      .data(pts, (d) => d.cutoff)
      .join("g")
      .attr("tabindex", 0)
      .attr("role", "img")
      .attr("aria-label", (d) => `Cutoff ${d.cutoff.slice(0, 4)}: ${OUTCOME[d.kind].label}${d.confidence !== null ? `, confidence ${fmt.conf(d.confidence)}` : ""}`)
      .style("outline", "none");
    mark.append("line").attr("y1", AXIS_Y).attr("y2", (d) => d.py).style("stroke", C.gold).attr("stroke-dasharray", "2 3").attr("opacity", 0.5);
    mark.append("rect").attr("y", (d) => d.py - 16).attr("width", 32).attr("height", 32).attr("fill", "transparent");
    mark
      .append("circle")
      .attr("cy", (d) => d.py)
      .attr("r", entering ? 0 : 6.5)
      .style("fill", (d) => (OUTCOME[d.kind].filled ? OUTCOME[d.kind].color : C.surface))
      .style("stroke", (d) => (OUTCOME[d.kind].filled ? C.surface : OUTCOME[d.kind].color))
      .attr("stroke-width", 2)
      .transition()
      .delay((_, i) => ms(entering ? 500 + i * 260 : 0))
      .duration(ms(entering ? 480 : 0))
      .ease(d3.easeBackOut.overshoot(2))
      .attr("r", 6.5);
    // A run of cutoffs with the same unscored verdict ("already known" three
    // times over) shares one label, centred on the run, instead of stacking three.
    const runEnd = pts.map((p, i) => {
      if (p.confidence !== null) return i;
      if (i > 0 && pts[i - 1].confidence === null && pts[i - 1].kind === p.kind) return -1;
      let j = i;
      while (j + 1 < pts.length && pts[j + 1].confidence === null && pts[j + 1].kind === p.kind) j++;
      return j;
    });
    const value = halo(
      mark
        .append("text")
        .attr("class", "value")
        .attr("y", (d) => d.py - 14)
        .attr("text-anchor", "middle")
        .attr("font-size", 11.5)
        .attr("font-weight", 600)
        .style("fill", C.ink)
        .text((d, i) => {
          if (d.confidence !== null) return fmt.conf(d.confidence);
          if (runEnd[i] === -1) return "";
          const label = OUTCOME[d.kind].label.toLowerCase();
          return runEnd[i] > i ? `${label} at ${runEnd[i] === pts.length - 1 && i === 0 ? "every cutoff" : `${runEnd[i] - i + 1} cutoffs`}` : label;
        }),
    );
    const cutLabel = mark
      .append("text")
      .attr("class", "cut")
      .attr("y", AXIS_Y + 36)
      .attr("text-anchor", "middle")
      .attr("font-size", 10.5)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.gold)
      .text((d) => `T ${d.cutoff.slice(0, 4)}`);

    let xNow = xF;
    mark
      .on("pointerenter focus", (_e: Event, d) => {
        mark.transition("dim").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 1 : 0.4));
        setTip({
          x: xNow(d.yr),
          y: d.py,
          value: d.confidence !== null ? fmt.conf(d.confidence) : OUTCOME[d.kind].label,
          label: `cutoff ${longDate(d.cutoff)} · ${OUTCOME[d.kind].label.toLowerCase()}`,
          rows: [
            ...(d.confidence !== null
              ? [
                  {
                    color: C.gold,
                    label: d.confidence >= threshold ? "above the line" : "below the line",
                    value: Math.abs(d.confidence - threshold).toFixed(3),
                  },
                ]
              : []),
            { color: OUTCOME[d.kind].color, label: d.detail, value: "" },
          ],
        });
      })
      .on("pointerleave blur", () => {
        mark.transition("dim").duration(ms(DUR.hover)).attr("opacity", 1);
        setTip(null);
      });

    // the publication record, as a rug
    svg
      .append("text")
      .attr("x", M.left)
      .attr("y", RUG_BASE + 16)
      .attr("font-size", 10.5)
      .attr("font-family", "var(--font-mono)")
      .attr("letter-spacing", "0.06em")
      .style("fill", C.muted)
      .text(`PUBLICATION RECORD · ${pubs.length} CANDIDATES`);
    svg.append("line").attr("x1", M.left).attr("x2", W - M.right).attr("y1", RUG_BASE).attr("y2", RUG_BASE).style("stroke", C.axis);
    const tick = over
      .append("g")
      .selectAll("line")
      .data(sortedPubs)
      .join("line")
      .attr("y1", RUG_BASE)
      .attr("y2", entering ? RUG_BASE : (d) => RUG_BASE - ROLE[d.role].h)
      .style("stroke", (d) => ROLE[d.role].color)
      .attr("stroke-width", (d) => (d.role === "established" ? 2.5 : 1.5))
      .attr("stroke-linecap", "round");
    if (entering) {
      tick
        .transition()
        .delay((_, i) => ms(700 + i * 30))
        .duration(ms(500))
        .ease(EASE)
        .attr("y2", (d) => RUG_BASE - ROLE[d.role].h);
    }

    // The rug is a crosshair: the nearest publication on x, within reach.
    const nearestPub = (event: PointerEvent) => {
      const [px] = d3.pointer(event, svg.node());
      let best: (typeof sortedPubs)[number] | null = null;
      for (const p of sortedPubs) {
        const d = Math.abs(xNow(p.yr) - px);
        if (d <= 14 && inPlot(xNow(p.yr)) && (!best || d < Math.abs(xNow(best.yr) - px))) best = p;
      }
      return best;
    };
    svg
      .append("rect")
      .attr("x", M.left - 8)
      .attr("y", RUG_BASE - RUG_H - 6)
      .attr("width", W - M.left - M.right + 16)
      .attr("height", RUG_H + 12)
      .attr("fill", "transparent")
      .on("pointermove", (event: PointerEvent) => {
        const d = nearestPub(event);
        if (!d) {
          tick.attr("opacity", (o) => (inPlot(xNow(o.yr)) ? 1 : 0));
          setTip(null);
          return;
        }
        tick.attr("opacity", (o) => (!inPlot(xNow(o.yr)) ? 0 : o === d ? 1 : 0.35));
        d3.select(event.currentTarget as Element).style("cursor", d.pmid ? "pointer" : "default");
        setTip({
          x: xNow(d.yr),
          y: RUG_BASE - RUG_H,
          value: longDate(d.date),
          label: d.title.length > 140 ? `${d.title.slice(0, 137)}…` : d.title,
          rows: [{ color: ROLE[d.role].color, label: ROLE[d.role].label, value: d.pmid ? `PMID ${d.pmid}` : "" }],
          note: d.why ?? undefined,
        });
      })
      .on("pointerleave", () => {
        tick.attr("opacity", (o) => (inPlot(xNow(o.yr)) ? 1 : 0));
        setTip(null);
      })
      .on("click", (event: PointerEvent) => {
        const d = nearestPub(event);
        if (d?.pmid) window.open(`https://pubmed.ncbi.nlm.nih.gov/${d.pmid}/`, "_blank", "noopener");
      });

    // ---- the context strip: the whole record, and the span on view ----
    svg.append("rect").attr("x", M.left).attr("y", CTX_TOP).attr("width", W - M.left - M.right).attr("height", CTX_H).attr("rx", 3).style("fill", C.grid).attr("opacity", 0.6);
    svg
      .append("g")
      .attr("pointer-events", "none")
      .selectAll("line")
      .data(sortedPubs)
      .join("line")
      .attr("x1", (d) => xC(d.yr))
      .attr("x2", (d) => xC(d.yr))
      .attr("y1", CTX_BASE - 2)
      .attr("y2", (d) => CTX_BASE - 2 - (d.role === "established" ? 16 : d.role === "near" ? 10 : 6))
      .style("stroke", (d) => ROLE[d.role].color)
      .attr("stroke-width", 1);
    svg
      .append("g")
      .attr("pointer-events", "none")
      .selectAll("path")
      .data(pts)
      .join("path")
      .attr("d", (d) => `M${xC(d.yr)},${CTX_TOP + 1}l-3.5,-5h7z`)
      .style("fill", C.gold);
    if (estYr !== null) {
      svg
        .append("line")
        .attr("x1", xC(estYr))
        .attr("x2", xC(estYr))
        .attr("y1", CTX_TOP)
        .attr("y2", CTX_BASE)
        .style("stroke", C.sealed)
        .attr("stroke-width", 1.5)
        .attr("pointer-events", "none");
    }
    const ctxAxis = svg.append("g").attr("transform", `translate(0,${CTX_BASE})`).attr("pointer-events", "none");
    ctxAxis.call(
      d3
        .axisBottom(xC)
        .ticks(Math.max(3, Math.round((W - M.left - M.right) / 90)))
        .tickFormat(d3.format("d"))
        .tickSize(3)
        .tickSizeOuter(0),
    );
    styleAxis(ctxAxis, { domain: false });
    ctxAxis.attr("font-size", 10).selectAll(".tick text").attr("dy", "0.6em");

    // ---- redraw the focus for a span of years ----
    const render = (domain: [number, number]) => {
      const x = d3.scaleLinear().domain(domain).range([M.left, W - M.right]);
      xNow = x;
      yearAxis(axis, x);
      const ex = estYr !== null ? x(estYr) : null;
      const windowW = ex === null ? 0 : Math.max(0, Math.min(W - M.right, ex) - M.left);
      windowRect.attr("width", windowW);
      windowLabel.attr("opacity", windowW > 170 ? 1 : 0);
      if (ex === null) {
        found.attr("opacity", 0);
        foundLabel.text("");
      } else {
        found.attr("x1", ex).attr("x2", ex).attr("opacity", inPlot(ex) ? 1 : 0);
        const off = ex < M.left ? "left" : ex > W - M.right ? "right" : null;
        const lx = off === "left" ? M.left + 2 : off === "right" ? W - M.right : ex + (ex > W * 0.78 ? -8 : 8);
        foundLabel
          .attr("x", lx)
          .attr("text-anchor", off === "left" ? "start" : off === "right" || ex > W * 0.78 ? "end" : "start")
          .text(off === "left" ? `◂ found ${established}` : off === "right" ? `found ${established} ▸` : `found ${established}`);
      }
      path.attr(
        "d",
        line.x((d) => x(d.yr)),
      );
      mark.attr("display", (d) => (inPlot(x(d.yr)) ? null : "none"));
      mark.select<SVGLineElement>("line").attr("x1", (d) => x(d.yr)).attr("x2", (d) => x(d.yr));
      mark.select<SVGRectElement>("rect").attr("x", (d) => x(d.yr) - 16);
      mark.select<SVGCircleElement>("circle").attr("cx", (d) => x(d.yr));
      value.attr("x", (d, i) => (runEnd[i] > i ? (x(d.yr) + x(pts[runEnd[i]].yr)) / 2 : x(d.yr)));
      cutLabel.attr("x", (d) => x(d.yr));
      // Where labels would collide at a wide view, keep the first and drop the rest.
      for (const sel of [value, cutLabel]) {
        let end = -Infinity;
        sel.attr("opacity", function () {
          if (!this.textContent) return 0;
          const b = this.getBBox();
          const keep = b.x > end + 6;
          if (keep) end = b.x + b.width;
          return keep ? 1 : 0;
        });
      }
      tick.attr("x1", (d) => x(d.yr)).attr("x2", (d) => x(d.yr)).attr("opacity", (d) => (inPlot(x(d.yr)) ? 1 : 0));
    };

    const brush = d3
      .brushX()
      .extent([
        [M.left, CTX_TOP],
        [W - M.right, CTX_BASE],
      ])
      .touchable(() => true)
      .on("brush end", (event: d3.D3BrushEvent<unknown>) => {
        if (!event.selection) {
          if (event.type === "end" && event.sourceEvent) brushG.call(brush.move, era.map(xC) as [number, number]);
          return;
        }
        const [a, b] = event.selection as [number, number];
        let lo = xC.invert(a);
        let hi = xC.invert(b);
        if (hi - lo < 1.5) [lo, hi] = [(lo + hi) / 2 - 0.75, (lo + hi) / 2 + 0.75];
        render([lo, hi]);
        if (event.type === "end") {
          const same = (d: [number, number]) => Math.abs(d[0] - lo) < 0.05 && Math.abs(d[1] - hi) < 0.05;
          setView(same(era) ? "era" : same(full) ? "full" : "custom");
        }
      });
    const brushG = svg.append("g").attr("class", "brush").call(brush);
    brushG.selectAll(".handle").style("fill", C.gold).attr("opacity", 0.0);
    brushG.call(brush.move, era.map(xC) as [number, number]);
    moveTo.current = (v) => {
      const d = v === "era" ? era : full;
      brushG
        .transition()
        .duration(ms(DUR.update + 150))
        .ease(d3.easeCubicInOut)
        .call(brush.move, d.map(xC) as [number, number]);
    };
    setView("era");

    if (entering) {
      drawIn(path, { delay: 300, duration: 1100 });
      windowRect
        .attr("width", 0)
        .transition()
        .duration(ms(1100))
        .ease(EASE)
        .attr("width", estYr !== null ? Math.max(0, Math.min(W - M.right, xF(estYr)) - M.left) : 0);
    }
    // On a phone, open on the cutoffs rather than the empty early years.
    focusFrame(wrapRef.current, xF(pts[0]?.yr ?? 2015), 0.15);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, marks, established, threshold]);

  const span = layout ? (view === "full" ? layout.full : layout.era) : null;
  return (
    <div>
      <ZoomBar
        presets={[
          { key: "era", label: "Cutoff era" },
          { key: "full", label: "Full history" },
        ]}
        active={view === "custom" ? null : view}
        onPick={(k) => moveTo.current?.(k as Exclude<View, "custom">)}
        status={
          view === "custom" || !span
            ? "Drag or resize the window on the strip below; click the strip to reset."
            : `${Math.round(span[0])} to ${Math.round(span[1])}. Drag across the strip below to zoom into any span.`
        }
      />
      <div className="viz-frame" style={{ ["--min-w" as string]: `${MIN_W}px` }}>
        <div className="viz" ref={wrapRef} style={{ minHeight: H }}>
          <svg ref={svgRef} role="group" aria-label="Confidence at each cutoff, the date the field established the gene, and its publication record" />
          <Tooltip tip={tip} />
        </div>
      </div>
    </div>
  );
}
