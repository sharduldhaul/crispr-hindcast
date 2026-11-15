"use client";

import * as d3 from "d3";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import type { VerdictKind } from "@/lib/types";

import { C, DUR, EASE, EASE_IN_OUT, OUTCOME, fmt, focusFrame, halo, ms, styleAxis, useChart } from "./core";
import { Tooltip } from "./Tooltip";
import { ZoomBar } from "./ZoomBar";

export interface SwarmPoint {
  symbol: string;
  confidence: number;
  evidence: number;
  kind: VerdictKind;
}

interface Placed extends SwarmPoint {
  x: number;
  y: number;
  shown: boolean;
}

const R = 5;
const DIAMETER = 2 * R + 1.5;
const MIN_W = 640;
const M = { right: 28, left: 28, bottom: 34 };
const LABEL_TOP = 40;
const LABEL_ROW = 16;
const MIN_SPAN = 0.03;
const CHAR = 7.4;

/**
 * A beeswarm by dodging, after the D3 gallery's: x is exactly the confidence,
 * and only y moves, to the nearest free place above or below the midline.
 */
function dodge(xs: number[]): number[] {
  const order = d3.range(xs.length).sort((a, b) => xs[a] - xs[b]);
  const ys = new Array<number>(xs.length).fill(0);
  const placed: { x: number; y: number }[] = [];
  const d2 = DIAMETER * DIAMETER;
  let head = 0;
  for (const i of order) {
    const bx = xs[i];
    while (head < placed.length && placed[head].x < bx - DIAMETER) head++;
    const near = placed.slice(head);
    const clear = (y: number) => near.every((a) => (a.x - bx) ** 2 + (a.y - y) ** 2 >= d2 - 1e-3);
    let y = 0;
    if (!clear(0)) {
      const candidates = near
        .flatMap((a) => {
          const dy = Math.sqrt(Math.max(0, d2 - (a.x - bx) ** 2));
          return [a.y - dy, a.y + dy];
        })
        .sort((p, q) => Math.abs(p) - Math.abs(q) || p - q);
      y = candidates.find(clear) ?? 0;
    }
    ys[i] = y;
    placed.push({ x: bx, y });
  }
  return ys;
}

/** Which genes get a name, and on which row, so no two names collide. */
function labelRows(nodes: Placed[], threshold: number, zoomed: boolean) {
  const shown = nodes.filter((d) => d.shown);
  const named =
    zoomed && shown.length <= 16
      ? shown
      : [
          ...shown.filter((p) => p.kind === "hit" || p.kind === "forecast").sort((a, b) => b.confidence - a.confidence).slice(0, 10),
          ...shown.filter((p) => p.kind === "missed" && p.confidence >= threshold - 0.06).sort((a, b) => b.confidence - a.confidence).slice(0, 4),
        ];
  // Genes at the same confidence share one label.
  const groups = d3
    .groups(named, (d) => d.confidence.toFixed(3))
    .map(([key, g]) => {
      const lead = g.reduce((a, b) => (b.y < a.y ? b : a));
      return { key, lead, text: g.map((d) => d.symbol).sort().join(" · ") };
    })
    .sort((a, b) => a.lead.x - b.lead.x);
  const rowEnds: number[] = [];
  const out = groups.map((g) => {
    const left = g.lead.x - 4;
    let row = rowEnds.findIndex((end) => end < left);
    if (row === -1) {
      row = rowEnds.length;
      rowEnds.push(0);
    }
    rowEnds[row] = left + g.text.length * CHAR + 12;
    return { ...g, row };
  });
  return { labels: out, rows: rowEnds.length };
}

/**
 * Every gene the system weighed, laid out as a beeswarm along its confidence,
 * with the frozen threshold drawn through it. Right of the line was claimed;
 * left of it was refused. Drag across it to zoom into a range.
 */
export function DecisionSwarm({ points, threshold }: { points: SwarmPoint[]; threshold: number }) {
  const router = useRouter();
  const { wrapRef, width, svgRef, inView, tip, setTip, entered } = useChart();
  const [zoom, setZoom] = useState<[number, number] | null>(null);
  const focusIndex = useRef<number | null>(null);
  const live = useRef<{ x: d3.ScaleLinear<number, number>; order: Placed[]; delaunay: d3.Delaunay<Placed> | null } | null>(null);

  const full = useMemo<[number, number]>(() => {
    const top = Math.max(threshold * 2, ...points.map((p) => p.confidence));
    return [0, Math.min(1, Math.ceil(top * 10) / 10)];
  }, [points, threshold]);
  const around: [number, number] = [Math.max(full[0], threshold - 0.1), Math.min(full[1], threshold + 0.1)];

  // The frame's height comes from the full view, the most crowded one, so
  // zooming in never resizes the chart; it only spreads the swarm out.
  const frame = useMemo(() => {
    if (!width) return null;
    const W = Math.max(width, MIN_W);
    const x = d3.scaleLinear().domain(full).range([M.left, W - M.right]);
    const ys = dodge(points.map((p) => x(p.confidence)));
    const nodes = points.map((p, i) => ({ ...p, x: x(p.confidence), y: ys[i], shown: true }));
    const rows = Math.max(3, labelRows(nodes, threshold, false).rows);
    const swarmTop = LABEL_TOP + rows * LABEL_ROW + 18;
    const midY = swarmTop + R + 4 - (d3.min(ys) ?? 0);
    const axisY = midY + (d3.max(ys) ?? 0) + R + 12;
    return { W, H: axisY + M.bottom, rows, swarmTop, midY, axisY };
  }, [points, threshold, width, full]);

  const layout = useMemo(() => {
    if (!frame) return null;
    const domain = zoom ?? full;
    const x = d3.scaleLinear().domain(domain).range([M.left, frame.W - M.right]);
    const inside = (c: number) => c >= domain[0] - 1e-9 && c <= domain[1] + 1e-9;
    const shownIdx = points.map((p, i) => (inside(p.confidence) ? i : -1)).filter((i) => i >= 0);
    const ys = dodge(shownIdx.map((i) => x(points[i].confidence)));
    const yOf = new Map(shownIdx.map((i, k) => [i, ys[k]]));
    const nodes: Placed[] = points.map((p, i) => ({
      ...p,
      x: x(p.confidence),
      y: frame.midY + (yOf.get(i) ?? 0),
      shown: yOf.has(i),
    }));
    const { labels } = labelRows(nodes, threshold, zoom !== null);
    return {
      x,
      domain,
      nodes,
      labels: labels.filter((l) => l.row < frame.rows),
      below: nodes.filter((d) => d.confidence < domain[0] - 1e-9).length,
      above: nodes.filter((d) => d.confidence > domain[1] + 1e-9).length,
    };
  }, [frame, zoom, full, points, threshold]);

  // ---- frame: everything that does not move with the zoom ----
  useEffect(() => {
    if (!frame || !inView || !svgRef.current) return;
    const { W, H, axisY } = frame;
    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();
    entered.current = false;

    svg
      .append("defs")
      .append("clipPath")
      .attr("id", "swarm-clip")
      .append("rect")
      .attr("x", M.left - R - 2)
      .attr("y", 0)
      .attr("width", W - M.left - M.right + 2 * R + 4)
      .attr("height", axisY);

    svg.append("rect").attr("class", "claimed").attr("y", LABEL_TOP - 16).attr("height", axisY - LABEL_TOP + 16).style("fill", C.claim).attr("opacity", 0);
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${axisY})`);
    svg.append("g").attr("class", "brush");
    svg.append("line").attr("class", "rule").style("stroke", C.gold).attr("stroke-width", 1.5).attr("stroke-dasharray", "4 4").attr("pointer-events", "none");
    const caption = (cls: string, anchor: string, fill: string, text: string) =>
      svg
        .append("text")
        .attr("class", cls)
        .attr("y", LABEL_TOP - 22)
        .attr("text-anchor", anchor)
        .attr("font-size", 11)
        .attr("font-family", "var(--font-mono)")
        .attr("pointer-events", "none")
        .style("fill", fill)
        .text(text);
    caption("cap-refused", "end", C.muted, "← refused");
    caption("cap-claimed", "start", C.gold, "claimed →");
    caption("edge-below", "start", C.muted, "");
    caption("edge-above", "end", C.muted, "");
    svg
      .append("text")
      .attr("class", "rule-label")
      .attr("y", axisY + 18)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.gold)
      .text(threshold);
    const clipped = svg.append("g").attr("clip-path", "url(#swarm-clip)").attr("pointer-events", "none");
    clipped.append("g").attr("class", "labels");
    clipped.append("g").attr("class", "dots");
    svg
      .append("circle")
      .attr("class", "ring")
      .attr("r", R + 4)
      .attr("fill", "none")
      .style("stroke", C.ink)
      .attr("stroke-width", 1.5)
      .attr("opacity", 0)
      .attr("pointer-events", "none");

    // Drag across the swarm to zoom into that range of confidence. Touch is
    // left to scroll the frame; the buttons above zoom on a phone.
    const brush = d3
      .brushX()
      .extent([
        [M.left, LABEL_TOP - 16],
        [W - M.right, axisY],
      ])
      .touchable(() => false)
      .on("end", (event: d3.D3BrushEvent<unknown>) => {
        if (!event.sourceEvent || !event.selection || !live.current) return;
        const [a, b] = event.selection as [number, number];
        svg.select<SVGGElement>(".brush").call(brush.move, null);
        if (b - a < 6) return;
        let lo = live.current.x.invert(a);
        let hi = live.current.x.invert(b);
        if (hi - lo < MIN_SPAN) {
          const mid = (lo + hi) / 2;
          lo = mid - MIN_SPAN / 2;
          hi = mid + MIN_SPAN / 2;
        }
        setZoom([Math.max(full[0], lo), Math.min(full[1], hi)]);
      });
    svg.select<SVGGElement>(".brush").call(brush);

    const ring = svg.select<SVGCircleElement>(".ring");
    const dots = () => svg.select(".dots").selectAll<SVGCircleElement, Placed>("circle");
    const show = (d: Placed) => {
      ring.interrupt().transition().duration(ms(DUR.hover)).ease(EASE).attr("cx", d.x).attr("cy", d.y).attr("opacity", 1);
      dots()
        .transition("dim")
        .duration(ms(DUR.hover))
        .attr("opacity", (o) => (!o.shown ? 0 : o.symbol === d.symbol ? 1 : 0.45));
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
      dots()
        .transition("dim")
        .duration(ms(DUR.hover))
        .attr("opacity", (o) => (o.shown ? 1 : 0));
      setTip(null);
      focusIndex.current = null;
    };
    const nearest = (event: PointerEvent) => {
      const cur = live.current;
      if (!cur?.delaunay || !cur.order.length) return null;
      const [px, py] = d3.pointer(event, svg.node());
      const d = cur.order[cur.delaunay.find(px, py)];
      return Math.hypot(d.x - px, d.y - py) < 24 ? d : null;
    };

    // A tap shows the tip; a second tap on the same gene opens it.
    let armed: string | null = null;
    let suppress = false;
    svg
      .attr("tabindex", 0)
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
      .on("dblclick", () => setZoom(null))
      .on("blur", hide)
      .on("keydown", (event: KeyboardEvent) => {
        const order = live.current?.order ?? [];
        const step = event.key === "ArrowRight" || event.key === "ArrowUp" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowDown" ? -1 : 0;
        if (step && order.length) {
          event.preventDefault();
          const start = focusIndex.current ?? (step > 0 ? -1 : order.length);
          focusIndex.current = Math.max(0, Math.min(order.length - 1, start + step));
          show(order[focusIndex.current]);
        } else if (event.key === "Enter" && focusIndex.current !== null && order[focusIndex.current]) {
          router.push(`/genes/${order[focusIndex.current].symbol}`);
        } else if (event.key === "Escape") {
          hide();
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, inView, threshold, router, full]);

  // ---- the swarm: enters on first view, spreads and gathers on every zoom ----
  useEffect(() => {
    if (!frame || !layout || !inView || !svgRef.current) return;
    const { W, axisY, midY } = frame;
    const { x, nodes, labels, domain, below, above } = layout;
    const svg = d3.select(svgRef.current);
    const entering = !entered.current;
    if (entering) focusFrame(wrapRef.current, x(threshold));
    entered.current = true;
    const duration = ms(entering ? DUR.enter : DUR.update + 150);
    const ease = entering ? EASE : EASE_IN_OUT;

    const order = nodes.filter((d) => d.shown).sort((a, b) => a.x - b.x);
    live.current = { x, order, delaunay: order.length ? d3.Delaunay.from(order, (d) => d.x, (d) => d.y) : null };
    focusIndex.current = null;
    setTip(null);
    svg.select(".ring").attr("opacity", 0);

    // threshold, shading, captions
    const tx = x(threshold);
    const ruleIn = tx >= M.left - 0.5 && tx <= W - M.right + 0.5;
    const shadeFrom = Math.min(Math.max(tx, M.left), W - M.right);
    if (entering) {
      // Start everything that slides with the zoom at its place, so the
      // entrance grows it rather than sliding it in from the left edge.
      svg.select(".claimed").attr("x", shadeFrom).attr("width", W - M.right - shadeFrom);
      svg.select(".rule").attr("x1", tx).attr("x2", tx).attr("y1", LABEL_TOP - 16).attr("y2", LABEL_TOP - 16);
      svg.selectAll(".rule-label").attr("x", tx);
      svg.select(".cap-refused").attr("x", tx - 10);
      svg.select(".cap-claimed").attr("x", tx + 10);
    }
    svg
      .select(".claimed")
      .transition()
      .delay(ms(entering ? 400 : 0))
      .duration(duration)
      .ease(ease)
      .attr("x", shadeFrom)
      .attr("width", W - M.right - shadeFrom)
      .attr("opacity", 0.06);
    svg
      .select(".rule")
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("x1", tx)
      .attr("x2", tx)
      .attr("y2", axisY + 6)
      .attr("opacity", ruleIn ? 1 : 0);
    svg
      .select(".rule-label")
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("x", tx)
      .attr("opacity", ruleIn ? 1 : 0);
    const roomL = ruleIn && tx - M.left > 150;
    const roomR = ruleIn && W - M.right - tx > 150;
    svg.select(".cap-refused").transition().duration(duration).ease(ease).attr("x", tx - 10).attr("opacity", roomL ? 1 : 0);
    svg.select(".cap-claimed").transition().duration(duration).ease(ease).attr("x", tx + 10).attr("opacity", roomR ? 1 : 0);
    svg
      .select(".edge-below")
      .attr("x", M.left)
      .text(below ? `← ${below} lower` : "")
      .attr("opacity", !ruleIn || tx - M.left > 260 ? 1 : 0);
    svg
      .select(".edge-above")
      .attr("x", W - M.right)
      .text(above ? `${above} higher →` : "")
      .attr("opacity", !ruleIn || W - M.right - tx > 260 ? 1 : 0);

    const span = domain[1] - domain[0];
    const ticks = (span > 0.4 ? d3.range(0, domain[1] + 1e-9, 0.1) : x.ticks(Math.max(4, Math.round(W / 110)))).filter(
      (v) => v >= domain[0] - 1e-9 && Math.abs(x(v) - tx) > 28,
    );
    const tickFormat = d3.format(span > 0.4 ? ".1f" : span > 0.1 ? ".2f" : ".3f");
    const axis = svg.select<SVGGElement>(".axis");
    axis
      .transition()
      .duration(duration)
      .ease(ease)
      .call(
        d3
          .axisBottom(x)
          .tickValues(ticks)
          .tickFormat((v) => tickFormat(+v))
          .tickSizeOuter(0),
      );
    styleAxis(axis);

    // dots
    const fill = (d: Placed) => (OUTCOME[d.kind].filled ? OUTCOME[d.kind].color : C.surface);
    const stroke = (d: Placed) => (OUTCOME[d.kind].filled ? C.surface : OUTCOME[d.kind].color);
    svg
      .select(".dots")
      .selectAll<SVGCircleElement, Placed>("circle")
      .data(nodes, (d) => d.symbol)
      .join((enter) =>
        enter
          .append("circle")
          .attr("cx", (d) => d.x)
          .attr("cy", midY)
          .attr("r", 0)
          .style("fill", fill)
          .style("stroke", stroke)
          .attr("stroke-width", (d) => (OUTCOME[d.kind].filled ? 1.5 : 1.3)),
      )
      .interrupt("dim")
      .transition()
      .delay((d) => (entering ? ms(150 + (d.x / W) * 700) : 0))
      .duration(duration)
      .ease(ease)
      .attr("cx", (d) => d.x)
      .attr("cy", (d) => d.y)
      .attr("r", R)
      .attr("opacity", (d) => (d.shown ? 1 : 0));

    // names, with leader lines
    type L = (typeof labels)[number];
    const label = svg
      .select(".labels")
      .selectAll<SVGGElement, L>("g")
      .data(labels, (d) => d.text)
      .join(
        (enter) => {
          const g = enter.append("g").attr("opacity", 0);
          g.append("line").attr("stroke-width", 1).attr("opacity", 0.5);
          halo(g.append("text").attr("font-size", 12).attr("font-weight", 600).attr("font-family", "var(--font-mono)").style("fill", C.ink));
          g.select("line")
            .attr("x1", (d) => d.lead.x)
            .attr("x2", (d) => d.lead.x)
            .attr("y1", (d) => LABEL_TOP + d.row * LABEL_ROW + 4)
            .attr("y2", (d) => d.lead.y - R - 2);
          g.select("text")
            .attr("x", (d) => d.lead.x - 4)
            .attr("y", (d) => LABEL_TOP + d.row * LABEL_ROW);
          return g;
        },
        (update) => update,
        (exit) => exit.transition().duration(ms(DUR.exit)).attr("opacity", 0).remove(),
      );
    label
      .select("line")
      .style("stroke", (d) => OUTCOME[d.lead.kind].color)
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("x1", (d) => d.lead.x)
      .attr("x2", (d) => d.lead.x)
      .attr("y1", (d) => LABEL_TOP + d.row * LABEL_ROW + 4)
      .attr("y2", (d) => d.lead.y - R - 2);
    label
      .select("text")
      .text((d) => d.text)
      .transition()
      .duration(duration)
      .ease(ease)
      .attr("x", (d) => d.lead.x - 4)
      .attr("y", (d) => LABEL_TOP + d.row * LABEL_ROW);
    label
      .transition()
      .delay(ms(entering ? 1100 : 0))
      .duration(ms(entering ? 500 : DUR.update))
      .attr("opacity", 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame, layout, inView]);

  const isAround = zoom !== null && Math.abs(zoom[0] - around[0]) < 1e-9 && Math.abs(zoom[1] - around[1]) < 1e-9;
  const shownCount = layout?.nodes.filter((d) => d.shown).length ?? points.length;
  return (
    <div>
      <ZoomBar
        presets={[
          { key: "all", label: "All genes" },
          { key: "around", label: "Around the line" },
        ]}
        active={zoom === null ? "all" : isAround ? "around" : null}
        onPick={(k) => setZoom(k === "all" ? null : around)}
        status={
          zoom === null
            ? "Drag across the swarm to zoom into a range."
            : `${shownCount} of ${points.length} genes between ${fmt.conf(zoom[0])} and ${fmt.conf(zoom[1])}. Double-click to zoom out.`
        }
      />
      <div className="viz-frame" style={{ ["--min-w" as string]: `${MIN_W}px` }}>
        <div className="viz" ref={wrapRef} style={{ minHeight: frame?.H ?? 220 }}>
          <svg
            ref={svgRef}
            role="img"
            aria-label={`Each of ${points.length} genes the system weighed, by confidence, against the refusal threshold of ${threshold}. Use the arrow keys to step through them.`}
          />
          <Tooltip tip={tip} />
        </div>
      </div>
    </div>
  );
}
