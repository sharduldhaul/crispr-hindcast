"use client";

// Shared plumbing for every chart: sizing, when to animate, motion timing,
// outcome colours and axis styling. Charts are React components that hand an
// <svg> to d3 inside an effect; d3 owns everything inside it.

import * as d3 from "d3";
import { useEffect, useRef, useState } from "react";

import type { VerdictKind } from "@/lib/types";

import type { Tip } from "./Tooltip";

export const EASE = d3.easeCubicOut;
export const EASE_IN_OUT = d3.easeCubicInOut;
export const DUR = { enter: 900, update: 750, exit: 280, hover: 140 };

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** A duration, or 0 when the reader has asked for less motion. */
export function ms(duration: number): number {
  return reducedMotion() ? 0 : duration;
}

/** The width of a container, kept current as it resizes. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setWidth(el.clientWidth);
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

/** True once the element has scrolled into view, so entrances play when seen. */
export function useInView(ref: React.RefObject<Element | null>) {
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (reducedMotion() || !("IntersectionObserver" in window)) {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref, seen]);
  return seen;
}

/** Everything a chart needs: its width, its svg, whether it has been seen, its tooltip. */
export function useChart() {
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const inView = useInView(wrapRef);
  const [tip, setTip] = useState<Tip | null>(null);
  const entered = useRef(false);
  return { wrapRef, width, svgRef, inView, tip, setTip, entered };
}

// Colours are CSS custom properties, so the stylesheet stays the one source of truth.
export const C = {
  claim: "var(--claim)",
  hit: "var(--ok)",
  sealed: "var(--future)",
  refused: "var(--muted)",
  fail: "var(--bad)",
  gold: "var(--accent)",
  ink: "var(--ink)",
  ink2: "var(--ink-2)",
  muted: "var(--muted)",
  grid: "var(--grid)",
  axis: "var(--axis)",
  surface: "var(--paper-2)",
  page: "var(--paper)",
};

export const OUTCOME: Record<VerdictKind, { color: string; filled: boolean; label: string }> = {
  hit: { color: C.hit, filled: true, label: "Came true" },
  forecast: { color: C.claim, filled: true, label: "Predicted, not confirmed" },
  missed: { color: C.sealed, filled: true, label: "Refused, found later" },
  refused: { color: C.refused, filled: false, label: "Refused" },
  known: { color: C.ink2, filled: true, label: "Already known" },
  none: { color: C.muted, filled: false, label: "No claim" },
};

// d3's selections are invariant in their four type parameters, so the helpers
// below are generic over them rather than taking one loose selection type.

/** Recessive axis: hairline domain, muted mono ticks. */
export function styleAxis<E extends d3.BaseType, D, P extends d3.BaseType, PD>(g: d3.Selection<E, D, P, PD>, opts: { domain?: boolean } = {}) {
  g.attr("font-family", "var(--font-mono)").attr("font-size", 11);
  g.selectAll(".domain").style("stroke", C.axis);
  if (opts.domain === false) g.selectAll(".domain").remove();
  g.selectAll(".tick line").style("stroke", C.axis);
  g.selectAll(".tick text").style("fill", C.muted);
  return g;
}

/**
 * A year axis that labels each year's span rather than its first instant, so a
 * cutoff on 31 December sits at the right edge of its own year instead of
 * under the next year's label. Label density follows the zoom.
 */
export function yearAxis(g: d3.Selection<SVGGElement, unknown, null, undefined>, x: d3.ScaleLinear<number, number>) {
  const [a, b] = x.domain();
  const ppy = Math.abs(x(a + 1) - x(a));
  const every = ppy >= 38 ? 1 : ppy >= 15 ? 2 : ppy >= 6 ? 5 : 10;
  const years = d3.range(Math.ceil(a), Math.floor(b) + 1).filter((y) => ppy >= 5 || y % every === 0);
  g.call(
    d3
      .axisBottom(x)
      .tickValues(years)
      .tickFormat(() => "")
      .tickSize(4)
      .tickSizeOuter(0),
  );
  styleAxis(g);
  g.selectAll<SVGGElement, number>(".tick")
    .select("line")
    .attr("y2", (d) => (d % every === 0 ? 8 : 4));
  g.selectAll<SVGTextElement, number>("text.year")
    .data(
      years.filter((y) => y % every === 0 && y + 1 <= b + 1e-9 && y >= a - 1e-9),
      (d) => d,
    )
    .join("text")
    .attr("class", "year")
    .attr("x", (y) => x(y + 0.5))
    .attr("y", 21)
    .attr("text-anchor", "middle")
    .style("fill", C.muted)
    .text(String);
  return g;
}

/** When a chart is wider than a phone, open its scrolling frame on the part that matters. */
export function focusFrame(inner: HTMLElement | null, x: number, at = 0.45) {
  const frame = inner?.parentElement;
  if (frame && frame.scrollWidth > frame.clientWidth) frame.scrollLeft = Math.max(0, x - frame.clientWidth * at);
}

/** A dark halo behind text, so a label stays readable where it crosses marks. */
export function halo<E extends d3.BaseType, D, P extends d3.BaseType, PD>(sel: d3.Selection<E, D, P, PD>, width = 4) {
  return sel
    .attr("paint-order", "stroke")
    .style("stroke", C.surface)
    .attr("stroke-width", width)
    .attr("stroke-linejoin", "round");
}

/** Draw a path or line in from its start: the stroke-dashoffset trick. */
export function drawIn<E extends SVGGeometryElement, D, P extends d3.BaseType, PD>(
  sel: d3.Selection<E, D, P, PD>,
  { delay = 0, duration = DUR.enter }: { delay?: number; duration?: number } = {},
) {
  sel.each(function () {
    const len = this.getTotalLength();
    d3.select(this)
      .attr("stroke-dasharray", `${len} ${len}`)
      .attr("stroke-dashoffset", len)
      .transition()
      .delay(ms(delay))
      .duration(ms(duration))
      .ease(EASE_IN_OUT)
      .attr("stroke-dashoffset", 0)
      .on("end", function () {
        d3.select(this).attr("stroke-dasharray", null);
      });
  });
}

export const fmt = {
  conf: d3.format(".3f"),
  int: d3.format(","),
  pct: d3.format(".0%"),
};
