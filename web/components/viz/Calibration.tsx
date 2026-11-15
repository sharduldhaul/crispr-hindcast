"use client";

import * as d3 from "d3";
import { useEffect, useMemo, useRef, useState } from "react";

import type { CalibrationBin, VerdictKind } from "@/lib/types";

import { C, DUR, EASE, EASE_IN_OUT, OUTCOME, fmt, ms, styleAxis, useChart } from "./core";
import { Tooltip } from "./Tooltip";

export interface CalibrationClaim {
  symbol: string;
  confidence: number;
  kind: VerdictKind;
}

interface Unit extends CalibrationClaim {
  bin: number;
  came: boolean;
  x: number;
  y: number;
}

const M = { top: 30, right: 14, bottom: 46, left: 44 };
const U = 3.6;
const STEP = 2 * U + 1.6;

const inBin = (b: CalibrationBin, c: number) => c >= b.lower && (c < b.upper || (b.upper >= 1 && c <= 1));

/**
 * Reliability diagram: when the system says 30%, is it right about 30% of the
 * time? Bars are what happened; the dashed diagonal is perfect honesty; the
 * hairline from each dot to the diagonal is that band's miscalibration. Click
 * a band to open it: every claim inside drops to the top (came true) or the
 * bottom (did not) at its stated confidence.
 */
export function Calibration({ bins, claims }: { bins: CalibrationBin[]; claims: CalibrationClaim[] }) {
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [open, setOpen] = useState<number | null>(null);
  const openRef = useRef(open);
  openRef.current = open;

  const layout = useMemo(() => {
    if (!width) return null;
    const W = Math.min(width, 380);
    const H = Math.round(W * 0.9);
    const x = d3.scaleLinear().domain([0, 1]).range([M.left, W - M.right]);
    const y = d3.scaleLinear().domain([0, 1]).range([H - M.bottom, M.top]);
    // Each claim, stacked by its exact confidence: came-true ones hang from
    // the top line, the rest stand on the bottom one.
    const units: Unit[] = [];
    bins.forEach((b, bi) => {
      for (const came of [true, false]) {
        const group = claims
          .filter((c) => inBin(b, c.confidence) && (c.kind === "hit" || c.kind === "missed") === came)
          .sort((p, q) => p.confidence - q.confidence || p.symbol.localeCompare(q.symbol));
        const stacks = new Map<number, number>();
        for (const c of group) {
          // claims closer together than a dot share a stack
          const px = x(c.confidence);
          const key = [...stacks.keys()].find((k) => Math.abs(k - px) < STEP) ?? px;
          const k = stacks.get(key) ?? 0;
          stacks.set(key, k + 1);
          units.push({ ...c, bin: bi, came, x: key, y: came ? y(1) + U + 2 + k * STEP : y(0) - U - 2 - k * STEP });
        }
      }
    });
    return { W, H, x, y, units };
  }, [width, bins, claims]);

  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, H, x, y } = layout;
    const entering = !entered.current;
    entered.current = true;

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    // grid on the same values as the axis ticks
    const yTicks = y.ticks(5);
    svg
      .append("g")
      .selectAll("line")
      .data(yTicks.filter((t) => t > 0))
      .join("line")
      .attr("x1", x(0))
      .attr("x2", x(1))
      .attr("y1", (d) => y(d))
      .attr("y2", (d) => y(d))
      .style("stroke", C.grid);
    styleAxis(svg.append("g").attr("transform", `translate(0,${y(0)})`).call(d3.axisBottom(x).ticks(5).tickSizeOuter(0)));
    styleAxis(svg.append("g").attr("transform", `translate(${x(0)},0)`).call(d3.axisLeft(y).tickValues(yTicks).tickSizeOuter(0)), { domain: false });
    svg
      .append("text")
      .attr("x", (x(0) + x(1)) / 2)
      .attr("y", H - 6)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .style("fill", C.muted)
      .text("confidence the system stated");
    svg
      .append("text")
      .attr("transform", `translate(12,${(y(0) + y(1)) / 2}) rotate(-90)`)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .style("fill", C.muted)
      .text("how often it came true");

    const diag = svg
      .append("line")
      .attr("x1", x(0))
      .attr("y1", y(0))
      .attr("x2", x(1))
      .attr("y2", y(1))
      .style("stroke", C.muted)
      .attr("stroke-dasharray", "4 4");
    if (entering) diag.attr("opacity", 0).transition().duration(ms(900)).attr("opacity", 1);

    const col = svg
      .append("g")
      .selectAll<SVGGElement, CalibrationBin>("g")
      .data(bins, (d) => String(d.lower))
      .join("g")
      .attr("class", "col")
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", (d) =>
        d.n ? `${d.n} claims stated ${d.lower} to ${d.upper}, true ${fmt.pct(d.observed_frequency)} of the time. Press Enter to list them.` : `No claims stated ${d.lower} to ${d.upper}`,
      )
      .style("outline", "none")
      .style("cursor", (d) => (d.n ? "pointer" : "default"));
    col
      .append("rect")
      .attr("x", (d) => x(d.lower))
      .attr("width", (d) => x(d.upper) - x(d.lower))
      .attr("y", y(1))
      .attr("height", y(0) - y(1))
      .attr("fill", "transparent");
    const bar = col
      .append("rect")
      .attr("class", "bar")
      .attr("x", (d) => x(d.lower) + 3)
      .attr("width", (d) => x(d.upper) - x(d.lower) - 6)
      .attr("rx", 3)
      .attr("y", (d) => (entering ? y(0) : y(d.observed_frequency)))
      .attr("height", (d) => (entering ? 0 : y(0) - y(d.observed_frequency)))
      .style("fill", C.claim)
      .attr("opacity", 0.8);
    if (entering) {
      bar
        .transition()
        .delay((_, i) => ms(250 + i * 110))
        .duration(ms(900))
        .ease(EASE)
        .attr("y", (d) => y(d.observed_frequency))
        .attr("height", (d) => y(0) - y(d.observed_frequency));
    }
    col
      .filter((d) => d.n > 0)
      .append("line")
      .attr("class", "gap")
      .attr("x1", (d) => x(d.mean_confidence))
      .attr("x2", (d) => x(d.mean_confidence))
      .attr("y1", (d) => y(d.mean_confidence))
      .attr("y2", (d) => y(d.observed_frequency))
      .style("stroke", C.ink)
      .attr("stroke-width", 1)
      .attr("opacity", entering ? 0 : 0.6)
      .transition()
      .delay(ms(entering ? 1100 : 0))
      .duration(ms(entering ? 500 : 0))
      .attr("opacity", 0.6);
    col
      .filter((d) => d.n > 0)
      .append("circle")
      .attr("class", "mean")
      .attr("cx", (d) => x(d.mean_confidence))
      .attr("cy", (d) => y(d.observed_frequency))
      .attr("r", entering ? 0 : 4)
      .style("fill", C.ink)
      .style("stroke", C.surface)
      .attr("stroke-width", 2)
      .transition()
      .delay((_, i) => ms(entering ? 900 + i * 110 : 0))
      .duration(ms(entering ? 420 : 0))
      .ease(d3.easeBackOut.overshoot(2))
      .attr("r", 4);
    // claim counts on a row of their own, clear of the bars and dots
    col
      .append("text")
      .attr("x", (d) => (x(d.lower) + x(d.upper)) / 2)
      .attr("y", M.top - 12)
      .attr("text-anchor", "middle")
      .attr("font-size", 10)
      .attr("font-family", "var(--font-mono)")
      .style("fill", (d) => (d.n ? C.ink2 : C.muted))
      .attr("opacity", entering ? 0 : 1)
      .text((d) => `n=${d.n}`)
      .transition()
      .delay((_, i) => ms(entering ? 700 + i * 110 : 0))
      .duration(ms(entering ? 400 : 0))
      .attr("opacity", 1);

    // the claims inside an opened band
    svg.append("g").attr("class", "units");

    const showBin = (_e: Event, d: CalibrationBin) => {
      if (openRef.current !== null) return;
      col.select(".bar").transition("hover").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 1 : 0.45));
      const gap = d.observed_frequency - d.mean_confidence;
      setTip({
        x: (x(d.lower) + x(d.upper)) / 2,
        y: Math.min(y(d.observed_frequency), y(0) - 30),
        value: d.n ? `${fmt.pct(d.observed_frequency)} came true (${Math.round(d.observed_frequency * d.n)} of ${d.n})` : "No claims",
        label: `stated ${d.lower.toFixed(1)}–${d.upper.toFixed(1)}`,
        rows: d.n
          ? [
              { color: C.claim, label: "claims in this band", value: String(d.n) },
              { color: C.ink, label: "mean stated confidence", value: d.mean_confidence.toFixed(3) },
              { color: C.muted, label: gap > 0 ? "underconfident by" : "overconfident by", value: Math.abs(gap).toFixed(3) },
            ]
          : undefined,
        note: d.n
          ? `${d.n < 5 ? "Too few claims to read much into. " : ""}Click to see each claim.`
          : undefined,
      });
    };
    const hideBin = () => {
      if (openRef.current !== null) return;
      col.select(".bar").transition("hover").duration(ms(DUR.hover)).attr("opacity", 0.8);
      setTip(null);
    };
    const toggle = (_e: Event, d: CalibrationBin) => {
      if (!d.n) return;
      const i = bins.indexOf(d);
      setTip(null);
      setOpen((o) => (o === i ? null : i));
    };
    col
      .on("pointerenter focus", showBin)
      .on("pointerleave blur", hideBin)
      .on("click", toggle)
      .on("keydown", (event: KeyboardEvent, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          toggle(event, d);
        } else if (event.key === "Escape") setOpen(null);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, bins]);

  // ---- open or fold a band ----
  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { x, y, units } = layout;
    const svg = d3.select(svgRef.current);
    const shown = open === null ? [] : units.filter((u) => u.bin === open);
    const b = open === null ? null : bins[open];
    const t = d3.transition().duration(ms(DUR.update)).ease(EASE_IN_OUT);

    svg
      .selectAll<SVGGElement, CalibrationBin>(".col")
      .select(".bar")
      .transition("hover")
      .duration(ms(DUR.update))
      .attr("opacity", (d, i) => (open === null ? 0.8 : i === open ? 0.28 : 0.12));
    svg
      .selectAll<SVGGElement, CalibrationBin>(".col")
      .selectAll<SVGElement, CalibrationBin>(".mean, .gap")
      .transition("open")
      .duration(ms(DUR.update))
      .attr("opacity", function () {
        const isGap = (this as Element).classList.contains("gap");
        return open === null ? (isGap ? 0.6 : 1) : 0.2;
      });

    // Each claim flies out of the bar's top to its row, and back when folded.
    const home = (u: Unit) => [x(u.confidence), y(bins[u.bin].observed_frequency)];
    svg
      .select(".units")
      .selectAll<SVGGElement, Unit>("g")
      .data(shown, (u) => u.symbol)
      .join(
        (enter) => {
          const g = enter
            .append("g")
            .attr("transform", (u) => `translate(${home(u)})`)
            .attr("opacity", 0)
            .attr("tabindex", 0)
            .attr("role", "img")
            .attr("aria-label", (u) => `${u.symbol}, stated ${fmt.conf(u.confidence)}, ${u.came ? "came true" : "did not come true"}`)
            .style("outline", "none");
          g.append("circle").attr("r", 7).attr("fill", "transparent");
          g.append("circle")
            .attr("r", U)
            .style("fill", (u) => (u.came ? C.hit : C.surface))
            .style("stroke", (u) => (u.came ? C.surface : OUTCOME[u.kind].color))
            .attr("stroke-width", 1.3);
          g.on("pointerenter focus", (_e: Event, u) =>
            setTip({
              x: u.x,
              y: u.y,
              value: u.symbol,
              label: u.came ? "came true" : "did not come true",
              rows: [{ color: C.claim, label: "stated confidence", value: fmt.conf(u.confidence) }],
              note: "Click the band again to fold it.",
            }),
          ).on("pointerleave blur", () => setTip(null));
          return g;
        },
        (update) => update,
        (exit) =>
          exit
            .transition(t)
            .attr("transform", (u) => `translate(${home(u)})`)
            .attr("opacity", 0)
            .remove(),
      )
      .transition(t)
      .delay((_, i) => ms(i * 14))
      .attr("transform", (u) => `translate(${u.x},${u.y})`)
      .attr("opacity", 1);

    const caption = svg.selectAll<SVGTextElement, number>("text.open-caption").data(b ? [0, 1] : []);
    caption
      .join((enter) =>
        enter
          .append("text")
          .attr("class", "open-caption")
          .attr("text-anchor", "end")
          .attr("font-size", 10.5)
          .attr("font-family", "var(--font-mono)")
          .attr("opacity", 0),
      )
      .attr("x", x(1) - 2)
      .attr("y", (i) => (i === 0 ? y(1) + 30 : y(0) - 26))
      .style("fill", (i) => (i === 0 ? C.hit : C.muted))
      .text((i) => {
        if (!b) return "";
        const came = shown.filter((u) => u.came).length;
        return i === 0 ? `came true · ${came}` : `did not · ${shown.length - came}`;
      })
      .transition(t)
      .attr("opacity", 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, layout, inView]);

  return (
    <div className="viz" ref={wrapRef} style={{ minHeight: layout?.H ?? 300, maxWidth: 380 }}>
      <svg ref={svgRef} role="group" aria-label="Reliability diagram: stated confidence against how often claims came true. Select a band to list its claims." />
      <Tooltip tip={tip} />
    </div>
  );
}
