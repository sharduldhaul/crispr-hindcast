"use client";

import * as d3 from "d3";
import { useEffect, useMemo } from "react";

import { C, DUR, OUTCOME, ms, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export interface OutcomeItem {
  symbol: string;
  kind: "hit" | "missed" | "none";
}

const R = 5.5;
const STEP = 16;

/** One dot per gene the field went on to find, filled if it was foreseen. */
export function OutcomeDots({ items }: { items: OutcomeItem[] }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();

  const layout = useMemo(() => {
    if (!width) return null;
    const perRow = Math.max(1, Math.floor((width + STEP - 2 * R) / STEP));
    const rows = Math.ceil(items.length / perRow);
    const pos = items.map((d, i) => ({ ...d, x: R + 1 + (i % perRow) * STEP, y: R + 1 + Math.floor(i / perRow) * STEP }));
    return { W: width, H: rows * STEP + 2, pos };
  }, [items, width]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const entering = !entered.current;
    entered.current = true;
    const svg = d3.select(svgRef.current).attr("width", layout.W).attr("height", layout.H);
    svg.selectAll("*").remove();
    const dot = svg
      .selectAll("circle")
      .data(layout.pos, (d) => (d as OutcomeItem).symbol)
      .join("circle")
      .attr("cx", (d) => d.x)
      .attr("cy", (d) => d.y)
      .attr("r", entering ? 0 : R)
      .style("fill", (d) => (d.kind === "hit" ? C.hit : C.surface))
      .style("stroke", (d) => OUTCOME[d.kind].color)
      .attr("stroke-width", 1.5)
      .on("pointerenter", function (_e, d) {
        d3.select(this).transition().duration(ms(DUR.hover)).attr("r", R + 2);
        setTip({
          x: d.x,
          y: d.y,
          value: d.symbol,
          label: d.kind === "hit" ? "foreseen: predicted, then found" : d.kind === "missed" ? "weighed, then refused" : "no trace before the cutoff",
        });
      })
      .on("pointerleave", function () {
        d3.select(this).transition().duration(ms(DUR.hover)).attr("r", R);
        setTip(null);
      });
    if (entering) {
      dot
        .transition()
        .delay((_, i) => ms(200 + i * 40))
        .duration(ms(450))
        .ease(d3.easeBackOut.overshoot(2.4))
        .attr("r", R);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView]);

  return (
    <div className="viz" ref={wrapRef} style={{ minHeight: layout?.H ?? STEP }} aria-hidden>
      <svg ref={svgRef} />
      <Tooltip tip={tip} />
    </div>
  );
}
