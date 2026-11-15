"use client";

import * as d3 from "d3";
import { useEffect, useMemo } from "react";

import { C, DUR, EASE, ms, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export interface Price {
  name: string;
  sub: string;
  price: number;
  route: string;
  note: string;
  source: string;
}

const ROW = 64;

/**
 * List prices on one linear scale. The generic pill is a hairline against the
 * gene therapies, which is the point.
 */
export function PriceBars({ prices }: { prices: Price[] }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();

  const layout = useMemo(() => {
    if (!width) return null;
    const W = width;
    const H = prices.length * ROW;
    const x = d3
      .scaleLinear()
      .domain([0, d3.max(prices, (d) => d.price) ?? 1])
      .range([0, W]);
    return { W, H, x };
  }, [prices, width]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, H, x } = layout;
    const entering = !entered.current;
    entered.current = true;
    const color = (d: Price) => (d.price > 100000 ? C.fail : C.hit);
    const money = d3.format("$,.0f");

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    const row = svg
      .selectAll<SVGGElement, Price>("g")
      .data(prices, (d) => d.name)
      .join("g")
      .attr("transform", (_, i) => `translate(0,${i * ROW})`)
      .attr("tabindex", 0)
      .attr("role", "img")
      .attr("aria-label", (d) => `${d.name}: ${money(d.price)}`)
      .style("outline", "none");
    row.append("rect").attr("width", W).attr("height", ROW).attr("fill", "transparent");
    row
      .append("text")
      .attr("y", 18)
      .attr("font-size", 15)
      .attr("font-weight", 600)
      .style("fill", C.ink)
      .text((d) => d.name);
    row
      .append("text")
      .attr("y", 36)
      .attr("font-size", 12.5)
      .style("fill", C.muted)
      .text((d) => d.sub);
    const value = row
      .append("text")
      .attr("x", W)
      .attr("y", 22)
      .attr("text-anchor", "end")
      .attr("font-size", 17)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.ink)
      .text((d) => money(entering ? 0 : d.price));
    row
      .append("rect")
      .attr("y", 46)
      .attr("width", W)
      .attr("height", 6)
      .attr("rx", 3)
      .style("fill", C.grid);
    const bar = row
      .append("rect")
      .attr("class", "bar")
      .attr("y", 46)
      .attr("height", 6)
      .attr("rx", 3)
      .attr("width", (d) => (entering ? 0 : Math.max(3, x(d.price))))
      .style("fill", color);

    if (entering) {
      const t = (i: number) => ms(200 + i * 220);
      bar
        .transition()
        .delay((_, i) => t(i))
        .duration(ms(1400))
        .ease(EASE)
        .attr("width", (d) => Math.max(3, x(d.price)));
      value
        .transition()
        .delay((_, i) => t(i))
        .duration(ms(1400))
        .ease(EASE)
        .tween("text", function (d) {
          const i = d3.interpolateNumber(0, d.price);
          return (k) => {
            this.textContent = money(i(k));
          };
        });
    }

    const show = (_e: Event, d: Price) => {
      row.select(".bar").transition("hover").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 1 : 0.4));
      setTip({
        x: Math.min(x(d.price), W - 20),
        y: prices.indexOf(d) * ROW + 49,
        value: money(d.price),
        label: d.name,
        rows: [{ color: color(d), label: "route", value: d.route }],
        note: `${d.note} Source: ${d.source}.`,
      });
    };
    const hide = () => {
      row.select(".bar").transition("hover").duration(ms(DUR.hover)).attr("opacity", 1);
      setTip(null);
    };
    row.on("pointerenter focus", show).on("pointerleave blur", hide);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, prices]);

  return (
    <div className="viz" ref={wrapRef} style={{ minHeight: layout?.H ?? prices.length * ROW }}>
      <svg ref={svgRef} role="group" aria-label="List prices of the approved therapies and the generic pill" />
      <Tooltip tip={tip} />
    </div>
  );
}
