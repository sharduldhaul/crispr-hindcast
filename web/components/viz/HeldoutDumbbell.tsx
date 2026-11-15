"use client";

import * as d3 from "d3";
import { useEffect, useMemo } from "react";

import { C, DUR, EASE_IN_OUT, fmt, ms, styleAxis, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export interface HeldoutRow {
  symbol: string;
  hidden: number;
  with: number;
  without: number;
  recovered: boolean;
}

const ROW = 34;
const M = { top: 10, right: 20, bottom: 30, left: 72 };

/**
 * Each tested gene's confidence with its lab measurements, and after they are
 * hidden. The second dot slides away from the first: that drop is the test.
 */
export function HeldoutDumbbell({ rows, threshold }: { rows: HeldoutRow[]; threshold: number }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();

  const layout = useMemo(() => {
    if (!width) return null;
    const W = width;
    const H = M.top + rows.length * ROW + M.bottom;
    const x = d3.scaleLinear().domain([0, 1]).range([M.left, W - M.right]);
    const y = d3
      .scaleBand<string>()
      .domain(rows.map((r) => r.symbol))
      .range([M.top, H - M.bottom]);
    return { W, H, x, y };
  }, [rows, width]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, H, x, y } = layout;
    const entering = !entered.current;
    entered.current = true;
    const cy = (d: HeldoutRow) => y(d.symbol)! + y.bandwidth() / 2;
    const end = (d: HeldoutRow) => (d.recovered ? C.hit : C.fail);

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    styleAxis(svg.append("g").attr("transform", `translate(0,${H - M.bottom})`).call(d3.axisBottom(x).ticks(5).tickSizeOuter(0)));
    svg
      .append("line")
      .attr("x1", x(threshold))
      .attr("x2", x(threshold))
      .attr("y1", M.top - 4)
      .attr("y2", H - M.bottom)
      .style("stroke", C.gold)
      .attr("stroke-dasharray", "4 4");

    const row = svg
      .append("g")
      .selectAll<SVGGElement, HeldoutRow>("g")
      .data(rows, (d) => d.symbol)
      .join("g")
      .attr("tabindex", 0)
      .attr("role", "img")
      .attr("aria-label", (d) => `${d.symbol}: ${fmt.conf(d.with)} with measurements, ${fmt.conf(d.without)} without, ${d.recovered ? "recovered" : "lost"}`)
      .style("outline", "none");
    row.append("rect").attr("x", 0).attr("width", W).attr("y", (d) => y(d.symbol)!).attr("height", y.bandwidth()).attr("fill", "transparent");
    row
      .append("text")
      .attr("x", M.left - 14)
      .attr("y", (d) => cy(d) + 4)
      .attr("text-anchor", "end")
      .attr("font-size", 12)
      .attr("font-weight", 600)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.ink)
      .text((d) => d.symbol);
    const bridge = row
      .append("line")
      .attr("x1", (d) => x(d.with))
      .attr("x2", (d) => x(entering ? d.with : d.without))
      .attr("y1", cy)
      .attr("y2", cy)
      .style("stroke", end)
      .attr("stroke-width", 2)
      .attr("opacity", 0.7);
    const after = row
      .append("circle")
      .attr("cx", (d) => x(entering ? d.with : d.without))
      .attr("cy", cy)
      .attr("r", 5)
      .style("fill", end)
      .style("stroke", C.surface)
      .attr("stroke-width", 1.5);
    // The "with" ring is drawn last, so where hiding the measurements changed
    // nothing it still shows, circling the dot that did not move.
    row
      .append("circle")
      .attr("cx", (d) => x(d.with))
      .attr("cy", cy)
      .attr("r", 8)
      .attr("fill", "none")
      .style("stroke", C.ink)
      .attr("stroke-width", 1.5);
    if (entering) {
      const delay = (_: HeldoutRow, i: number) => ms(500 + i * 140);
      after.transition().delay(delay).duration(ms(1300)).ease(EASE_IN_OUT).attr("cx", (d) => x(d.without));
      bridge.transition().delay(delay).duration(ms(1300)).ease(EASE_IN_OUT).attr("x2", (d) => x(d.without));
    }

    const show = (_e: Event, d: HeldoutRow) => {
      row.transition("dim").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 1 : 0.35));
      setTip({
        x: x(d.without),
        y: cy(d),
        value: Math.abs(d.without - d.with) < 0.0005 ? "No change" : `${d.without - d.with > 0 ? "+" : "−"}${Math.abs(d.without - d.with).toFixed(3)}`,
        label: `${d.symbol} · ${d.recovered ? "still reachable" : "lost"} without its measurements`,
        rows: [
          { color: C.ink, label: "with measurements", value: fmt.conf(d.with) },
          { color: d.recovered ? C.hit : C.fail, label: "without", value: fmt.conf(d.without) },
          { label: "measurements hidden", value: fmt.int(d.hidden) },
        ],
      });
    };
    const hide = () => {
      row.transition("dim").duration(ms(DUR.hover)).attr("opacity", 1);
      setTip(null);
    };
    row.on("pointerenter focus", show).on("pointerleave blur", hide);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, rows, threshold]);

  return (
    <div className="viz" ref={wrapRef} style={{ minHeight: layout?.H ?? M.top + rows.length * ROW + M.bottom }}>
      <svg ref={svgRef} role="group" aria-label="Confidence with and without each gene's lab measurements" />
      <Tooltip tip={tip} />
    </div>
  );
}
