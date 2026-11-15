"use client";

import * as d3 from "d3";
import { useEffect, useMemo } from "react";

import { C, DUR, EASE, drawIn, fmt, ms, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export interface SlopeItem {
  symbol: string;
  confidence: number;
  impact: number;
  weight: number;
  route: string;
  rankConf: number;
  rankCost: number;
  hit: boolean;
}

const ROW = 30;
const M = { top: 34, bottom: 12 };
const CHAR = 7.2;
const SLOPE_MIN = 150;

const labelL = (d: SlopeItem, full: boolean) => (full ? [`#${d.rankConf}  `, `${fmt.conf(d.confidence)}  `, d.symbol] : [`#${d.rankConf} `, d.symbol]);
const labelR = (d: SlopeItem, full: boolean) => (full ? [`#${d.rankCost}  `, d.symbol, `  ${d.impact.toFixed(2)}`] : [`#${d.rankCost} `, d.symbol]);

/**
 * How the cost lens reorders the forecast: rank by confidence on the left,
 * rank by confidence times the route's cost weight on the right.
 */
export function RankSlope({ items }: { items: SlopeItem[] }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();

  const layout = useMemo(() => {
    if (!width) return null;
    const W = Math.min(width, 640);
    const n = items.length;
    const H = M.top + n * ROW + M.bottom;
    // Size each side to its longest label. Where that leaves too little room
    // for the slopes, drop the numbers from the labels; the tooltip keeps them.
    const width_ = (full: boolean, side: "L" | "R") =>
      (d3.max(items, (d) => (side === "L" ? labelL(d, full) : labelR(d, full)).join("").length) ?? 8) * CHAR + 14;
    const full = W - width_(true, "L") - width_(true, "R") >= SLOPE_MIN;
    const xL = width_(full, "L");
    const xR = W - width_(full, "R");
    const y = d3
      .scalePoint<number>()
      .domain(d3.range(1, n + 1))
      .range([M.top + ROW / 2, H - M.bottom - ROW / 2]);
    return { W, H, xL, xR, y, full };
  }, [items, width]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, H, xL, xR, y, full } = layout;
    const entering = !entered.current;
    entered.current = true;
    const color = (d: SlopeItem) => (d.hit ? C.hit : C.claim);

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    for (const [xx, text, anchor] of [
      [xL, "By confidence", "start"],
      [xR, "By affordable impact", "end"],
    ] as const) {
      svg
        .append("text")
        .attr("x", anchor === "start" ? 0 : W)
        .attr("y", 14)
        .attr("text-anchor", anchor)
        .attr("font-size", 10.5)
        .attr("letter-spacing", "0.08em")
        .attr("font-family", "var(--font-mono)")
        .style("fill", C.muted)
        .text(text.toUpperCase());
      svg.append("line").attr("x1", xx).attr("x2", xx).attr("y1", M.top - 4).attr("y2", H - M.bottom).style("stroke", C.axis);
    }

    const g = svg
      .append("g")
      .selectAll<SVGGElement, SlopeItem>("g")
      .data(items, (d) => d.symbol)
      .join("g")
      .attr("tabindex", 0)
      .attr("role", "img")
      .attr("aria-label", (d) => `${d.symbol}: rank ${d.rankConf} by confidence, ${d.rankCost} by affordable impact`)
      .style("cursor", "default")
      .style("outline", "none");

    const path = (d: SlopeItem) => `M${xL},${y(d.rankConf)} C${(xL + xR) / 2},${y(d.rankConf)} ${(xL + xR) / 2},${y(d.rankCost)} ${xR},${y(d.rankCost)}`;
    g.append("path").attr("d", path).attr("fill", "none").style("stroke", "transparent").attr("stroke-width", 18);
    const line = g
      .append("path")
      .attr("class", "slope")
      .attr("d", path)
      .attr("fill", "none")
      .style("stroke", color)
      .attr("stroke-width", (d) => (d.rankConf === d.rankCost ? 1.5 : 2.25))
      .attr("opacity", (d) => (d.rankConf === d.rankCost ? 0.55 : 0.95));
    if (entering) drawIn(line, { delay: 200, duration: 1100 });

    for (const side of ["L", "R"] as const) {
      const cx = side === "L" ? xL : xR;
      const rank = (d: SlopeItem) => (side === "L" ? d.rankConf : d.rankCost);
      g.append("circle")
        .attr("cx", cx)
        .attr("cy", (d) => y(rank(d))!)
        .attr("r", entering ? 0 : 4.5)
        .style("fill", color)
        .style("stroke", C.surface)
        .attr("stroke-width", 2)
        .transition()
        .delay((_, i) => ms(side === "L" ? 120 + i * 60 : 1100 + i * 60))
        .duration(ms(entering ? 420 : 0))
        .ease(d3.easeBackOut.overshoot(2))
        .attr("r", 4.5);
      const text = g
        .append("text")
        .attr("x", cx + (side === "L" ? -12 : 12))
        .attr("y", (d) => y(rank(d))! + 4)
        .attr("text-anchor", side === "L" ? "end" : "start")
        .attr("font-size", 12)
        .attr("font-family", "var(--font-mono)")
        .style("white-space", "pre")
        .attr("opacity", entering ? 0 : 1);
      // rank and number in muted ink, the symbol in full ink
      text
        .selectAll("tspan")
        .data((d) => (side === "L" ? labelL(d, full) : labelR(d, full)).map((part, i) => ({ part, symbol: part === d.symbol, i })))
        .join("tspan")
        .attr("font-weight", (p) => (p.symbol ? 600 : 400))
        .style("fill", (p) => (p.symbol ? C.ink : C.muted))
        .text((p) => p.part);
      if (entering) text.transition().delay((_, i) => ms(side === "L" ? 160 + i * 60 : 1150 + i * 60)).duration(ms(400)).attr("opacity", 1);
    }

    const show = (_event: Event, d: SlopeItem) => {
      g.transition("dim").duration(ms(DUR.hover)).ease(EASE).attr("opacity", (o) => (o === d ? 1 : 0.18));
      const moved = d.rankConf - d.rankCost;
      setTip({
        x: (xL + xR) / 2,
        y: (y(d.rankConf)! + y(d.rankCost)!) / 2,
        value: `#${d.rankConf} → #${d.rankCost}`,
        label: `${d.symbol} · ${d.hit ? "came true" : "not confirmed"}`,
        rows: [
          { color: C.claim, label: "confidence", value: fmt.conf(d.confidence) },
          { color: C.gold, label: `cost weight, ${d.route.toLowerCase()}`, value: `×${d.weight}` },
          { color: C.ink, label: "affordable impact", value: d.impact.toFixed(2) },
        ],
        note: moved > 0 ? `Moves up ${moved} once cost counts.` : moved < 0 ? `Drops ${-moved} once cost counts.` : "Same place either way.",
      });
    };
    const hide = () => {
      g.transition("dim").duration(ms(DUR.hover)).attr("opacity", 1);
      setTip(null);
    };
    g.on("pointerenter focus", show).on("pointerleave blur", hide);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, items]);

  return (
    <div className="viz" ref={wrapRef} style={{ minHeight: layout?.H ?? M.top + items.length * ROW + M.bottom, maxWidth: 640 }}>
      <svg ref={svgRef} role="group" aria-label="Forecast rank by confidence against rank by affordable impact" />
      <Tooltip tip={tip} />
    </div>
  );
}
