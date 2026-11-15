"use client";

import * as d3 from "d3";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { VerdictKind } from "@/lib/types";

import { C, DUR, EASE, EASE_IN_OUT, OUTCOME, fmt, halo, ms, styleAxis, useChart } from "./core";
import { Tooltip } from "./Tooltip";
import { ZoomBar } from "./ZoomBar";

export interface ScatterPoint {
  symbol: string;
  confidence: number;
  evidence: number;
  kind: VerdictKind;
}

interface Placed extends ScatterPoint {
  x: number;
  y: number;
  shown: boolean;
}

type Domain = { x: [number, number]; y: [number, number] };

const R = 5;
const MIN_W = 560;
const M = { top: 22, right: 28, bottom: 48, left: 54 };
// Marks sit this far inside the axes, so a gene at zero evidence is not drawn on the axis line.
const INSET = 14;
const CHAR = 7;
const EVIDENCE_TICKS = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000];

/**
 * Evidence is not confidence. Each gene the system weighed at one cutoff, by
 * how much evidence it had and how confident that evidence made the system.
 * Evidence runs on a symlog scale, so a gene with none sits at a true zero.
 * Switching the cutoff moves each gene to where it stood then; dragging a
 * box zooms in, and the crowd spreads apart and is named.
 */
export function EvidenceScatter({
  byCutoff,
  cutoff,
  threshold,
  highlight,
}: {
  byCutoff: Record<string, ScatterPoint[]>;
  cutoff: string;
  threshold: number;
  highlight: Set<string> | null;
}) {
  const router = useRouter();
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [zoom, setZoom] = useState<Domain | null>(null);
  const live = useRef<{ x: d3.ScaleSymLog<number, number>; y: d3.ScaleLinear<number, number>; shown: Placed[]; delaunay: d3.Delaunay<Placed> | null } | null>(null);
  const highlightRef = useRef(highlight);
  highlightRef.current = highlight;

  // Fixed across cutoffs, so a dot that moves has really moved.
  const full = useMemo<Domain>(() => {
    const all = Object.values(byCutoff).flat();
    return {
      x: [0, (d3.max(all, (d) => d.evidence) ?? 10) * 1.25],
      y: [0, Math.ceil(Math.max(0.55, (d3.max(all, (d) => d.confidence) ?? 0.5) * 1.1) * 10) / 10],
    };
  }, [byCutoff]);
  const near: Domain = { x: full.x, y: [Math.max(0, threshold - 0.1), threshold + 0.1] };

  const frame = useMemo(() => {
    if (!width) return null;
    const W = Math.max(width, MIN_W);
    const H = Math.round(Math.min(440, Math.max(340, W * 0.42)));
    return { W, H, plot: { x0: M.left, x1: W - M.right, y0: M.top, y1: H - M.bottom } };
  }, [width]);

  const layout = useMemo(() => {
    if (!frame) return null;
    const { W, H, plot } = frame;
    const dom = zoom ?? full;
    const x = d3
      .scaleSymlog()
      .constant(1)
      .domain(dom.x)
      .range([M.left + INSET, W - M.right - INSET]);
    const y = d3
      .scaleLinear()
      .domain(dom.y)
      .range([H - M.bottom - INSET, M.top + INSET]);
    const points = byCutoff[cutoff] ?? [];
    const inside = (p: ScatterPoint) =>
      p.evidence >= dom.x[0] - 1e-9 && p.evidence <= dom.x[1] + 1e-9 && p.confidence >= dom.y[0] - 1e-9 && p.confidence <= dom.y[1] + 1e-9;

    // Genes at the same spot are relaxed apart around it, never more than
    // they need, and kept inside the plot.
    type Node = Placed & { tx: number; ty: number };
    const nodes: Node[] = points.map((p) => ({ ...p, tx: x(p.evidence), ty: y(p.confidence), x: x(p.evidence), y: y(p.confidence), shown: inside(p) }));
    const shown = nodes.filter((d) => d.shown);
    for (const [, group] of d3.group(shown, (d) => `${d.evidence}|${d.confidence.toFixed(4)}`)) {
      group.forEach((d, i) => {
        const a = i * 2.39996;
        d.x += Math.sqrt(i) * 2 * Math.cos(a);
        d.y += Math.sqrt(i) * 2 * Math.sin(a);
      });
    }
    const keep = (d: Node) => {
      d.x = Math.max(plot.x0 + R + 1, Math.min(plot.x1 - R - 1, d.x));
      d.y = Math.max(plot.y0 + R + 1, Math.min(plot.y1 - R - 1, d.y));
    };
    const sim = d3
      .forceSimulation(shown)
      .force("x", d3.forceX<Node>((d) => d.tx).strength(0.4))
      .force("y", d3.forceY<Node>((d) => d.ty).strength(0.4))
      .force("collide", d3.forceCollide(R + 0.9).iterations(3))
      .stop();
    for (let i = 0; i < 160; i++) {
      sim.tick();
      shown.forEach(keep);
    }

    // Name what was claimed and the two most-evidenced refusals; zoomed in on
    // a small crowd, name everyone.
    const named =
      zoom && shown.length <= 18
        ? shown
        : [
            ...shown.filter((d) => d.kind === "hit" || d.kind === "forecast"),
            ...shown
              .filter((d) => d.kind === "refused" || d.kind === "missed")
              .sort((a, b) => b.evidence - a.evidence)
              .slice(0, 2),
          ];
    const taken: { x0: number; x1: number; y: number }[] = shown.map((d) => ({ x0: d.x - R, x1: d.x + R, y: d.y + 4 }));
    const labels = [...named]
      .sort((a, b) => a.y - b.y)
      .flatMap((d) => {
        const w = d.symbol.length * CHAR;
        const flip = d.x + 9 + w > plot.x1;
        const x0 = flip ? d.x - 9 - w : d.x + 9;
        const x1 = x0 + w;
        // Try beside the dot, then step away above and below until clear.
        for (const dy of [0, -13, 13, -26, 26, -39, 39]) {
          const ly = d.y + 4 + dy;
          if (ly < plot.y0 + 10 || ly > plot.y1 - 2) continue;
          const hit = taken.some((p) => p.x0 < x1 && x0 < p.x1 && Math.abs(p.y - ly) < 12);
          if (!hit) {
            taken.push({ x0, x1, y: ly });
            return [{ symbol: d.symbol, flip, lx: flip ? d.x - 9 : d.x + 9, ly, dx: d.x, dy: d.y }];
          }
        }
        return [];
      });
    return { x, y, nodes: nodes as Placed[], shown: shown as Placed[], labels, dom };
  }, [frame, zoom, full, byCutoff, cutoff]);

  // ---- frame: drawn once per size ----
  useEffect(() => {
    if (!frame || !inView || !svgRef.current) return;
    const { W, H, plot } = frame;
    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();
    entered.current = false;

    svg
      .append("defs")
      .append("clipPath")
      .attr("id", "scatter-clip")
      .append("rect")
      .attr("x", plot.x0)
      .attr("y", plot.y0)
      .attr("width", plot.x1 - plot.x0)
      .attr("height", plot.y1 - plot.y0);
    svg.append("g").attr("class", "grid");
    svg.append("rect").attr("class", "claimed").attr("x", plot.x0).attr("width", plot.x1 - plot.x0).style("fill", C.claim).attr("opacity", 0.05);
    svg.append("g").attr("class", "x-axis").attr("transform", `translate(0,${plot.y1})`);
    svg.append("g").attr("class", "y-axis").attr("transform", `translate(${plot.x0},0)`);
    svg
      .append("text")
      .attr("x", (plot.x0 + plot.x1) / 2)
      .attr("y", H - 8)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .style("fill", C.muted)
      .text("pieces of evidence before the cutoff (symlog scale)");
    svg
      .append("text")
      .attr("transform", `translate(14,${(plot.y0 + plot.y1) / 2}) rotate(-90)`)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .style("fill", C.muted)
      .text("confidence");
    svg.append("g").attr("class", "brush");
    const clipped = svg.append("g").attr("clip-path", "url(#scatter-clip)").attr("pointer-events", "none");
    clipped
      .append("line")
      .attr("class", "threshold")
      .style("stroke", C.gold)
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "4 4");
    clipped
      .append("text")
      .attr("class", "threshold-label")
      .attr("x", plot.x1 - 6)
      .attr("text-anchor", "end")
      .attr("font-size", 11)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.gold)
      .text(`claimed above ${threshold}`);
    clipped.append("g").attr("class", "dots");
    clipped.append("g").attr("class", "labels");
    svg
      .append("circle")
      .attr("class", "ring")
      .attr("r", R + 4)
      .attr("fill", "none")
      .style("stroke", C.ink)
      .attr("stroke-width", 1.5)
      .attr("opacity", 0)
      .attr("pointer-events", "none");

    // Drag a box to zoom into it. Touch scrolls the frame; the buttons zoom on a phone.
    const brush = d3
      .brush()
      .extent([
        [plot.x0, plot.y0],
        [plot.x1, plot.y1],
      ])
      .touchable(() => false)
      .on("end", (event: d3.D3BrushEvent<unknown>) => {
        if (!event.sourceEvent || !event.selection || !live.current) return;
        const [[a, b], [c, d]] = event.selection as [[number, number], [number, number]];
        svg.select<SVGGElement>(".brush").call(brush.move, null);
        if (c - a < 10 || d - b < 10) return;
        const { x, y } = live.current;
        let [x0, x1] = [Math.max(full.x[0], x.invert(a)), Math.min(full.x[1], x.invert(c))];
        let [y0, y1] = [Math.max(full.y[0], y.invert(d)), Math.min(full.y[1], y.invert(b))];
        if (x1 - x0 < 1) [x0, x1] = [Math.max(0, (x0 + x1) / 2 - 0.5), (x0 + x1) / 2 + 0.5];
        if (y1 - y0 < 0.02) [y0, y1] = [(y0 + y1) / 2 - 0.01, (y0 + y1) / 2 + 0.01];
        setZoom({ x: [x0, x1], y: [y0, y1] });
      });
    svg.select<SVGGElement>(".brush").call(brush);

    const ring = svg.select<SVGCircleElement>(".ring");
    const nearest = (event: PointerEvent) => {
      const cur = live.current;
      if (!cur?.delaunay || !cur.shown.length) return null;
      const [px, py] = d3.pointer(event, svg.node());
      const d = cur.shown[cur.delaunay.find(px, py)];
      return Math.hypot(d.x - px, d.y - py) < 28 ? d : null;
    };
    const show = (d: Placed) => {
      ring.interrupt().transition().duration(ms(DUR.hover)).ease(EASE).attr("cx", d.x).attr("cy", d.y).attr("opacity", 1);
      const gap = d.confidence - threshold;
      setTip({
        x: d.x,
        y: d.y,
        value: fmt.conf(d.confidence),
        label: `${d.symbol} · ${OUTCOME[d.kind].label.toLowerCase()}`,
        rows: [
          { color: OUTCOME[d.kind].color, label: "pieces of evidence", value: fmt.int(d.evidence) },
          { color: C.gold, label: gap >= 0 ? "above the line" : "below the line", value: Math.abs(gap).toFixed(3) },
        ],
        note: "Click to open the gene",
      });
    };
    const hide = () => {
      ring.transition().duration(ms(DUR.hover)).attr("opacity", 0);
      setTip(null);
    };
    let armed: string | null = null;
    let suppress = false;
    svg
      .on("pointermove", (event: PointerEvent) => {
        if (event.pointerType === "touch") return;
        const d = nearest(event);
        if (d) show(d);
        else hide();
      })
      .on("pointerdown", (event: PointerEvent) => {
        suppress = false;
        if (event.pointerType === "mouse") return;
        const d = nearest(event);
        if (!d) {
          armed = null;
          hide();
        } else if (armed !== d.symbol) {
          armed = d.symbol;
          suppress = true;
          show(d);
        }
      })
      .on("pointerleave", (event: PointerEvent) => {
        if (event.pointerType !== "touch") hide();
      })
      .on("click", (event: PointerEvent) => {
        if (suppress) return;
        const d = nearest(event);
        if (d) router.push(`/genes/${d.symbol}`);
      })
      .on("dblclick", () => setZoom(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, inView, threshold, router, full]);

  // ---- points: enter, move between cutoffs and zooms, exit ----
  useEffect(() => {
    if (!frame || !layout || !inView || !svgRef.current) return;
    const { plot } = frame;
    const { x, y, nodes, shown, labels, dom } = layout;
    const svg = d3.select(svgRef.current);
    const entering = !entered.current;
    entered.current = true;
    const duration = ms(entering ? DUR.enter : DUR.update + 150);
    const ease = entering ? EASE : EASE_IN_OUT;
    live.current = { x, y, shown, delaunay: shown.length ? d3.Delaunay.from(shown, (d) => d.x, (d) => d.y) : null };
    svg.select(".ring").attr("opacity", 0);
    setTip(null);

    // axes and grid follow the zoom
    const inX = EVIDENCE_TICKS.filter((v) => v >= dom.x[0] - 1e-9 && v <= dom.x[1] + 1e-9);
    const xTicks = inX.length >= 4 ? inX : x.ticks(6).filter((v, i, a) => a.length < 4 || Number.isInteger(v));
    const yTicks = y.ticks(5);
    const ySpan = dom.y[1] - dom.y[0];
    const xFmt = (v: number) => (Number.isInteger(v) ? fmt.int(v) : d3.format(".1f")(v));
    const yFmt = d3.format(ySpan < 0.3 ? ".2f" : ".1f");
    const xa = svg.select<SVGGElement>(".x-axis");
    const ya = svg.select<SVGGElement>(".y-axis");
    xa.transition().duration(duration).ease(ease).call(d3.axisBottom(x).tickValues(xTicks).tickFormat((v) => xFmt(+v)).tickSizeOuter(0));
    ya.transition().duration(duration).ease(ease).call(d3.axisLeft(y).tickValues(yTicks).tickFormat((v) => yFmt(+v)).tickSizeOuter(0));
    styleAxis(xa);
    styleAxis(ya, { domain: false });
    const grid = svg.select(".grid");
    grid
      .selectAll<SVGLineElement, number>("line.h")
      .data(yTicks, (d) => d)
      .join((enter) => enter.append("line").attr("class", "h").attr("y1", (d) => y(d)).attr("y2", (d) => y(d)).attr("opacity", 0))
      .attr("x1", plot.x0)
      .attr("x2", plot.x1)
      .style("stroke", C.grid)
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("y1", (d) => y(d))
      .attr("y2", (d) => y(d))
      .attr("opacity", 1);
    grid
      .selectAll<SVGLineElement, number>("line.v")
      .data(xTicks, (d) => d)
      .join((enter) => enter.append("line").attr("class", "v").attr("x1", (d) => x(d)).attr("x2", (d) => x(d)).attr("opacity", 0))
      .attr("y1", plot.y0)
      .attr("y2", plot.y1)
      .style("stroke", C.grid)
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("x1", (d) => x(d))
      .attr("x2", (d) => x(d))
      .attr("opacity", 1);

    // the line, and the claimed side of it
    const ty = y(threshold);
    const shadeTo = Math.max(plot.y0, Math.min(plot.y1, ty));
    if (entering) svg.select(".claimed").attr("y", plot.y0).attr("height", shadeTo - plot.y0);
    svg
      .select(".claimed")
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("y", plot.y0)
      .attr("height", shadeTo - plot.y0);
    const line = svg.select(".threshold");
    if (entering) line.attr("x1", plot.x0).attr("x2", plot.x0).attr("y1", ty).attr("y2", ty);
    line
      .transition()
      .duration(ms(entering ? 1000 : duration))
      .ease(ease)
      .attr("x2", plot.x1)
      .attr("y1", ty)
      .attr("y2", ty);
    if (entering) svg.select(".threshold-label").attr("y", ty - 7);
    svg
      .select(".threshold-label")
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("y", ty - 7);

    // dots
    const fill = (d: Placed) => (OUTCOME[d.kind].filled ? OUTCOME[d.kind].color : C.surface);
    const stroke = (d: Placed) => (OUTCOME[d.kind].filled ? C.surface : OUTCOME[d.kind].color);
    const opacity = (d: Placed) => (!d.shown ? 0 : highlightRef.current && !highlightRef.current.has(d.symbol) ? 0.12 : 1);
    svg
      .select(".dots")
      .selectAll<SVGCircleElement, Placed>("circle")
      .data(nodes, (d) => d.symbol)
      .join(
        (enter) =>
          enter
            .append("circle")
            .attr("cx", (d) => d.x)
            .attr("cy", plot.y1)
            .attr("r", 0)
            .style("fill", fill)
            .style("stroke", stroke)
            .attr("stroke-width", 1.4),
        (update) => update,
        (exit) => exit.transition().duration(ms(DUR.exit)).attr("r", 0).attr("opacity", 0).remove(),
      )
      .transition()
      .delay((_, i) => (entering ? ms(120 + i * 12) : ms(i * 4)))
      .duration(duration)
      .ease(ease)
      .attr("cx", (d) => d.x)
      .attr("cy", (d) => d.y)
      .attr("r", R)
      .attr("opacity", opacity)
      .style("fill", fill)
      .style("stroke", stroke);

    type Lb = (typeof labels)[number];
    svg
      .select(".labels")
      .selectAll<SVGTextElement, Lb>("text")
      .data(labels, (d) => d.symbol)
      .join(
        (enter) =>
          enter
            .append("text")
            .attr("font-size", 11.5)
            .attr("font-weight", 600)
            .attr("font-family", "var(--font-mono)")
            .style("fill", C.ink)
            .attr("opacity", 0)
            .attr("x", (d) => d.lx)
            .attr("y", (d) => d.ly)
            .text((d) => d.symbol)
            .call((e) => halo(e)),
        (update) => update,
        (exit) => exit.transition().duration(ms(DUR.exit)).attr("opacity", 0).remove(),
      )
      .attr("text-anchor", (d) => (d.flip ? "end" : "start"))
      .transition()
      .delay(ms(entering ? 700 : 0))
      .duration(ms(entering ? 500 : DUR.update + 150))
      .ease(ease)
      .attr("x", (d) => d.lx)
      .attr("y", (d) => d.ly)
      .attr("opacity", (d) => (!highlightRef.current || highlightRef.current.has(d.symbol) ? 1 : 0.15));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, layout, inView]);

  // ---- search: dim everything that does not match ----
  useEffect(() => {
    if (!svgRef.current || !entered.current) return;
    const svg = d3.select(svgRef.current);
    svg
      .select(".dots")
      .selectAll<SVGCircleElement, Placed>("circle")
      .filter((d) => d.shown)
      .transition("highlight")
      .duration(ms(DUR.update / 2))
      .attr("opacity", (d) => (!highlight || highlight.has(d.symbol) ? 1 : 0.12));
    svg
      .select(".labels")
      .selectAll<SVGTextElement, { symbol: string }>("text")
      .transition("highlight")
      .duration(ms(DUR.update / 2))
      .attr("opacity", (d) => (!highlight || highlight.has(d.symbol) ? 1 : 0.15));
  }, [highlight, svgRef, entered]);

  const isNear = zoom !== null && zoom.y[0] === near.y[0] && zoom.y[1] === near.y[1] && zoom.x[1] === near.x[1];
  const total = (byCutoff[cutoff] ?? []).length;
  return (
    <div>
      <ZoomBar
        presets={[
          { key: "all", label: "All genes" },
          { key: "near", label: "Near the line" },
        ]}
        active={zoom === null ? "all" : isNear ? "near" : null}
        onPick={(k) => setZoom(k === "all" ? null : near)}
        status={
          zoom === null
            ? "Drag a box to zoom in; the crowd spreads out and is named."
            : `${layout?.shown.length ?? 0} of ${total} genes in view. Double-click to zoom out.`
        }
      />
      <div className="viz-frame" style={{ ["--min-w" as string]: `${MIN_W}px` }}>
        <div className="viz" ref={wrapRef} style={{ minHeight: frame?.H ?? 360 }}>
          <svg ref={svgRef} role="img" aria-label="Each weighed gene by pieces of evidence and confidence; the table below lists the same genes." />
          <Tooltip tip={tip} />
        </div>
      </div>
    </div>
  );
}
