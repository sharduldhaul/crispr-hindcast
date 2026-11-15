"use client";

import * as d3 from "d3";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { cutoffWords, fractionalYear, longDate } from "@/lib/format";

import { C, DUR, EASE, EASE_IN_OUT, halo, ms, useInView, useWidth, yearAxis } from "./viz/core";
import { type Tip, Tooltip } from "./viz/Tooltip";

export interface TimelineGene {
  symbol: string;
  date: string;
  core: boolean;
}

export interface TimelineRun {
  cutoff: string;
  predicted: number;
  hits: number;
}

interface Props {
  genes: TimelineGene[];
  runs: TimelineRun[];
  initialCutoff: string;
}

interface Placed extends TimelineGene {
  yr: number;
  cx: number;
  row: number;
}

const START = 2000;
// The axis runs to the end of 2025, so the last labelled year has its whole span.
const END = 2026;
const MIN_W = 720;
const ROW = 22;
const AXIS_GAP = 30;
const M = { top: 36, right: 24, bottom: 34, left: 64 };
// A drag that lands this close to a cutoff that was run snaps onto it.
const SNAP = 0.4;

// A cutoff is the end of its day: a gene established that day is visible.
const at = (date: string) => fractionalYear(date) + 0.001;

export function CutoffTimeline({ genes, runs, initialCutoff }: Props) {
  const router = useRouter();
  const [frameRef, width] = useWidth<HTMLDivElement>();
  const svgRef = useRef<SVGSVGElement>(null);
  const inView = useInView(frameRef);
  const [cutoff, setCutoff] = useState(at(initialCutoff));
  const [tip, setTip] = useState<Tip | null>(null);
  const dragging = useRef(false);
  const cutoffRef = useRef(cutoff);
  cutoffRef.current = cutoff;

  const runPoints = useMemo(() => runs.map((r) => ({ ...r, at: at(r.cutoff) })), [runs]);

  const layout = useMemo(() => {
    if (!width) return null;
    const W = Math.max(width, MIN_W);
    const x = d3.scaleLinear().domain([START, END]).range([M.left, W - M.right]).clamp(true);
    const sorted = [...genes].sort((a, b) => a.date.localeCompare(b.date));
    const earlier = sorted.filter((g) => fractionalYear(g.date) < START);
    // Greedy row packing so labels never overlap.
    const rowEnds: number[] = [];
    const placed: Placed[] = sorted
      .filter((g) => fractionalYear(g.date) >= START)
      .map((g) => {
        const yr = fractionalYear(g.date);
        const cx = x(yr);
        const left = cx - 5;
        let row = rowEnds.findIndex((end) => end < left);
        if (row === -1) {
          row = rowEnds.length;
          rowEnds.push(0);
        }
        rowEnds[row] = left + g.symbol.length * 7.2 + 14;
        return { ...g, yr, cx, row };
      });
    const H = M.top + Math.max(1, rowEnds.length) * ROW + 30 + M.bottom;
    return { W, H, x, axisY: H - M.bottom, placed, earlier };
  }, [genes, width]);

  const snap = (yr: number) => {
    const near = runPoints.find((r) => Math.abs(r.at - yr) < SNAP);
    return near ? near.at : Math.round(yr * 4) / 4;
  };

  // ---- structure and entrance: drawn once per size ----
  const drawnFor = useRef<number | null>(null);
  useEffect(() => {
    if (!layout || !inView || !svgRef.current) return;
    const { W, H, x, axisY, placed, earlier } = layout;
    const entering = drawnFor.current === null;
    drawnFor.current = W;
    const yOf = (d: Placed) => axisY - AXIS_GAP + 6 - d.row * ROW;
    const now = cutoffRef.current;

    const svg = d3.select(svgRef.current).attr("width", W).attr("height", H).attr("viewBox", `0 0 ${W} ${H}`);
    svg.selectAll("*").remove();

    const defs = svg.append("defs");
    const hatch = defs
      .append("pattern")
      .attr("id", "tl-hatch")
      .attr("width", 7)
      .attr("height", 7)
      .attr("patternUnits", "userSpaceOnUse")
      .attr("patternTransform", "rotate(45)");
    hatch.append("line").attr("y2", 7).style("stroke", C.sealed).attr("stroke-width", 1).attr("opacity", 0.1);
    const veilGrad = defs.append("linearGradient").attr("id", "tl-veil-grad");
    veilGrad.append("stop").attr("offset", 0).style("stop-color", C.sealed).attr("stop-opacity", 0.12);
    veilGrad.append("stop").attr("offset", 0.18).style("stop-color", C.sealed).attr("stop-opacity", 0.04);
    veilGrad.append("stop").attr("offset", 1).style("stop-color", C.sealed).attr("stop-opacity", 0.01);
    const glow = defs.append("filter").attr("id", "tl-glow").attr("x", "-200%").attr("width", "500%");
    glow.append("feGaussianBlur").attr("stdDeviation", 3.5).attr("result", "blur");
    const merge = glow.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    defs
      .append("clipPath")
      .attr("id", "tl-plot-clip")
      .append("rect")
      .attr("width", W - M.right)
      .attr("height", axisY);

    const surface = svg.append("rect").attr("width", W).attr("height", H).attr("fill", "transparent").style("cursor", "ew-resize");

    // the sealed future, slid into place from the right on first view; the
    // clip keeps it inside the plot, so it never widens the scrolling frame
    const veil = svg
      .append("g")
      .attr("clip-path", "url(#tl-plot-clip)")
      .append("g")
      .attr("class", "tl-veil")
      .attr("pointer-events", "none")
      .attr("transform", `translate(${entering ? W : x(now)},0)`);
    veil.append("rect").attr("width", W).attr("height", axisY).attr("fill", "url(#tl-veil-grad)");
    veil.append("rect").attr("width", W).attr("height", axisY).attr("fill", "url(#tl-hatch)");
    if (entering) veil.transition().delay(ms(350)).duration(ms(1400)).ease(EASE_IN_OUT).attr("transform", `translate(${x(now)},0)`);

    yearAxis(svg.append("g").attr("transform", `translate(0,${axisY})`).attr("pointer-events", "none"), x);

    // genes established before the axis begins
    const early = svg
      .append("g")
      .attr("transform", `translate(10,${axisY - 12})`)
      .style("cursor", "help")
      .on("pointerenter", () =>
        setTip({
          x: 30,
          y: axisY - 40,
          value: `${earlier.length} genes`,
          label: "established before 2000",
          note: earlier.map((g) => g.symbol).join(", "),
        }),
      )
      .on("pointerleave", () => setTip(null));
    early.append("rect").attr("x", -6).attr("y", -30).attr("width", 52).attr("height", 40).attr("fill", "transparent");
    early.append("text").attr("y", -14).attr("font-size", 16).style("fill", C.ink).text(`+${earlier.length}`);
    early.append("text").attr("font-size", 11).attr("font-family", "var(--font-mono)").style("fill", C.muted).text("earlier");

    // genes: every stem sits in a layer beneath every label, so a tall stem
    // never strikes through a neighbour's name
    const stem = svg
      .append("g")
      .attr("pointer-events", "none")
      .selectAll<SVGLineElement, Placed>("line")
      .data(placed, (d) => d.symbol)
      .join("line")
      .attr("class", "tl-stem")
      .attr("x1", (d) => d.cx)
      .attr("x2", (d) => d.cx)
      .attr("y1", axisY)
      .attr("y2", entering ? axisY : (d) => yOf(d) + 4)
      .attr("stroke-width", 1)
      .attr("opacity", 0.28);
    const node = svg
      .append("g")
      .selectAll<SVGAElement, Placed>("a")
      .data(placed, (d) => d.symbol)
      .join("a")
      .attr("class", "tl-gene")
      .attr("href", (d) => `/genes/${d.symbol}`)
      .attr("aria-label", (d) => `${d.symbol}, established ${d.date}`)
      .style("cursor", "pointer")
      .on("click", (event: MouseEvent, d) => {
        event.preventDefault();
        router.push(`/genes/${d.symbol}`);
      })
      .on("pointerenter focus", function (_event, d) {
        const sealed = d.yr >= cutoffRef.current;
        node.transition("hover").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 1 : 0.35));
        stem.transition("hover").duration(ms(DUR.hover)).attr("opacity", (o) => (o === d ? 0.6 : 0.12));
        setTip({
          x: d.cx,
          y: yOf(d),
          value: d.symbol,
          label: `established ${longDate(d.date)}`,
          rows: [
            {
              color: sealed ? C.sealed : C.ink,
              label: `at a cutoff of ${cutoffWords(cutoffRef.current)}`,
              value: sealed ? "sealed" : "visible",
            },
            ...(d.core ? [{ color: C.gold, label: "core gene of the field", value: "yes" }] : []),
          ],
          note: "Click to open the gene",
        });
      })
      .on("pointerleave blur", () => {
        node.transition("hover").duration(ms(DUR.hover)).attr("opacity", 1);
        stem.transition("hover").duration(ms(DUR.hover)).attr("opacity", 0.28);
        setTip(null);
      });

    node
      .append("rect")
      .attr("x", (d) => d.cx - 8)
      .attr("y", (d) => yOf(d) - 11)
      .attr("width", (d) => d.symbol.length * 7.2 + 20)
      .attr("height", 22)
      .attr("fill", "transparent");
    const dot = node
      .append("circle")
      .attr("cx", (d) => d.cx)
      .attr("cy", (d) => yOf(d))
      .attr("r", entering ? 0 : (d) => (d.core ? 4.5 : 3.2))
      .attr("stroke-width", 1.4);
    const label = node
      .append("text")
      .attr("x", (d) => d.cx + 9)
      .attr("y", (d) => yOf(d) + 4)
      .attr("font-size", 12)
      .attr("font-family", "var(--font-mono)")
      .attr("font-weight", (d) => (d.core ? 600 : 400))
      .attr("opacity", entering ? 0 : 1)
      .text((d) => d.symbol);
    halo(label, 3.5);
    paintGenes(node, stem, now, 0);
    if (entering) {
      const delay = (_: Placed, i: number) => ms(200 + i * 16);
      stem.transition().delay(delay).duration(ms(520)).ease(EASE).attr("y2", (d) => yOf(d) + 4);
      dot
        .transition()
        .delay((d, i) => delay(d, i) + ms(260))
        .duration(ms(420))
        .ease(d3.easeBackOut.overshoot(2.2))
        .attr("r", (d) => (d.core ? 4.5 : 3.2));
      label.transition().delay((d, i) => delay(d, i) + ms(320)).duration(ms(400)).attr("opacity", 1);
    }

    // the cutoffs that were actually run: click to jump
    const run = svg
      .append("g")
      .selectAll("g")
      .data(runPoints)
      .join("g")
      .attr("class", "tl-run")
      .attr("role", "button")
      .attr("tabindex", 0)
      .attr("aria-label", (d) => `Jump to the ${d.cutoff.slice(0, 4)} cutoff`)
      .style("cursor", "pointer")
      .on("click", (_e, d) => setCutoff(d.at))
      .on("keydown", (event: KeyboardEvent, d) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setCutoff(d.at);
        }
      })
      .on("pointerenter focus", (_e, d) =>
        setTip({
          x: x(d.at),
          y: axisY - 16,
          value: `Cutoff ${d.cutoff.slice(0, 4)}`,
          label: "a cutoff the pipeline was run at",
          rows: [
            { color: C.claim, label: "genes predicted", value: String(d.predicted) },
            { color: C.hit, label: "came true", value: String(d.hits) },
          ],
          note: "Click to move the cutoff here",
        }),
      )
      .on("pointerleave blur", () => setTip(null));
    run.append("rect").attr("x", (d) => x(d.at) - 12).attr("y", axisY - 12).attr("width", 24).attr("height", 24).attr("fill", "transparent");
    run
      .append("rect")
      .attr("class", "tl-run-mark")
      .attr("x", (d) => x(d.at) - 4.5)
      .attr("y", axisY - 4.5)
      .attr("width", 9)
      .attr("height", 9)
      .attr("transform", (d) => `rotate(45 ${x(d.at)} ${axisY})`)
      .style("stroke", C.gold)
      .attr("stroke-width", 1.5)
      .style("fill", C.page);

    // the cutoff itself
    const handle = svg
      .append("g")
      .attr("class", "tl-handle")
      .attr("role", "slider")
      .attr("tabindex", 0)
      .attr("aria-label", "Cutoff year")
      .attr("aria-valuemin", START)
      .attr("aria-valuemax", END)
      .attr("transform", `translate(${x(now)},${entering ? -40 : 0})`)
      .style("cursor", "grab")
      .on("keydown", (event: KeyboardEvent) => {
        const step = ({ ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -5, PageUp: 5 } as Record<string, number>)[event.key];
        if (step !== undefined) {
          event.preventDefault();
          setCutoff((c) => Math.max(START, Math.min(END, c + step)));
        } else if (event.key === "Home" || event.key === "End") {
          event.preventDefault();
          setCutoff(event.key === "Home" ? START : END);
        }
      });
    handle.append("rect").attr("x", -14).attr("width", 28).attr("height", axisY + 8).attr("fill", "transparent");
    handle
      .append("line")
      .attr("y1", 20)
      .attr("y2", axisY + 8)
      .style("stroke", C.gold)
      .attr("stroke-width", 2)
      .attr("filter", "url(#tl-glow)");
    handle.append("rect").attr("class", "tl-flag").attr("x", -36).attr("width", 72).attr("height", 21).attr("rx", 10.5).style("fill", C.gold);
    handle
      .append("text")
      .attr("y", 14.5)
      .attr("text-anchor", "middle")
      .attr("font-size", 11)
      .attr("font-weight", 600)
      .attr("font-family", "var(--font-mono)")
      .style("fill", C.page);
    if (entering) handle.transition().delay(ms(250)).duration(ms(800)).ease(d3.easeBackOut.overshoot(1.4)).attr("transform", `translate(${x(now)},0)`);

    // Mouse and pen drag the line, or press anywhere on the chart. Touch
    // scrolls the frame instead, so phones keep their gesture.
    const drag = d3
      .drag<SVGElement, unknown>()
      .touchable(() => false)
      .on("start", (event) => {
        dragging.current = true;
        handle.style("cursor", "grabbing");
        setCutoff(snap(x.invert(event.x)));
      })
      .on("drag", (event) => setCutoff(snap(x.invert(event.x))))
      .on("end", () => {
        dragging.current = false;
        handle.style("cursor", "grab");
      });
    surface.call(drag as unknown as (s: typeof surface) => void);
    handle.call(drag as unknown as (s: typeof handle) => void);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, inView, runPoints, router]);

  // ---- the cutoff moves: slide the veil and the line, re-colour genes ----
  useEffect(() => {
    if (!layout || !inView || !svgRef.current || drawnFor.current === null) return;
    const svg = d3.select(svgRef.current);
    const cx = layout.x(cutoff);
    const duration = dragging.current ? 0 : ms(DUR.update);
    svg.select(".tl-veil").interrupt().transition().duration(duration).ease(EASE).attr("transform", `translate(${cx},0)`);
    svg.select(".tl-handle").interrupt().transition().duration(duration).ease(EASE).attr("transform", `translate(${cx},0)`);
    // A run's cutoff is the last day of its year, so it is named by that year;
    // anywhere else the flag names the month.
    const yearEnd = cutoff - Math.floor(cutoff) > 0.99;
    svg
      .select(".tl-handle")
      .attr("aria-valuenow", cutoff.toFixed(2))
      .attr("aria-valuetext", `Cutoff at the ${cutoffWords(cutoff)}`)
      .select("text")
      .text(yearEnd ? `T ${Math.floor(cutoff)}` : cutoffWords(cutoff));
    svg
      .selectAll<SVGRectElement, { at: number }>(".tl-run-mark")
      .transition()
      .duration(ms(DUR.hover))
      .style("fill", (d) => (Math.abs(d.at - cutoff) < 0.01 ? C.gold : C.page));
    paintGenes(
      svg.selectAll<SVGAElement, Placed>(".tl-gene"),
      svg.selectAll<SVGLineElement, Placed>(".tl-stem"),
      cutoff,
      dragging.current ? ms(160) : ms(DUR.update),
    );
  }, [cutoff, layout, inView]);

  // On a narrow screen the chart scrolls sideways; keep the cutoff and the
  // sealed future to its right in view.
  useEffect(() => {
    const f = frameRef.current;
    if (!f || !layout || f.scrollWidth <= f.clientWidth) return;
    const px = layout.x(cutoff);
    if (px < f.scrollLeft + 40 || px > f.scrollLeft + f.clientWidth - 40) {
      f.scrollTo({ left: px - f.clientWidth * 0.35, behavior: "smooth" });
    }
  }, [cutoff, layout, frameRef]);

  const known = genes.filter((g) => fractionalYear(g.date) < cutoff).length;
  const sealed = genes.length - known;
  const activeRun = runPoints.find((r) => Math.abs(r.at - cutoff) < 0.01);
  const when = cutoffWords(cutoff);
  const label = when.startsWith("end of") ? `by the ${when}` : `before ${when}`;

  return (
    <figure style={{ margin: 0 }}>
      <div className="viz-frame" ref={frameRef}>
        <div className="viz" style={{ width: layout?.W, minHeight: layout?.H ?? 300 }}>
          <svg ref={svgRef} role="group" aria-label="Timeline of when the field established each gene, with a movable cutoff" />
          <Tooltip tip={tip} />
        </div>
      </div>

      <input
        className="tl-range"
        type="range"
        min={START}
        max={END}
        step={0.25}
        value={cutoff}
        onChange={(e) => setCutoff(snap(Number(e.target.value)))}
        aria-label="Cutoff year"
      />

      <div className="tl-bar">
        <div className="tl-counts" aria-live="polite">
          <span>
            <b>{known}</b> <span className="muted">known {label}</span>
          </span>
          <span style={{ color: "var(--future)" }}>
            <b>{sealed}</b> <span>sealed, the answer key</span>
          </span>
        </div>
        {activeRun ? (
          <span className="small">
            <span className="muted">
              Run at this cutoff: {activeRun.predicted} predicted, {activeRun.hits} came true.{" "}
            </span>
            <Link className="go" href={`/slices/${activeRun.cutoff}`}>
              See the forecast
            </Link>
          </span>
        ) : (
          <span className="viz-hint">
            Drag the line, or use <kbd>←</kbd> <kbd>→</kbd>. <span style={{ color: "var(--accent)" }}>◆</span> marks a cutoff that
            was run.
          </span>
        )}
      </div>
    </figure>
  );
}

/** Colour each gene, and its stem, by which side of the cutoff it falls on. */
function paintGenes<E extends Element, P extends d3.BaseType, F extends Element, Q extends d3.BaseType>(
  genes: d3.Selection<E, Placed, P, unknown>,
  stems: d3.Selection<F, Placed, Q, unknown>,
  cutoff: number,
  duration: number,
) {
  const changed = (el: Element, d: Placed) => {
    const future = String(d.yr >= cutoff);
    if (el.getAttribute("data-future") === future) return false;
    el.setAttribute("data-future", future);
    return true;
  };
  genes.each(function (d) {
    if (!changed(this, d)) return;
    const future = d.yr >= cutoff;
    const g = d3.select(this);
    const t = d3.transition().duration(duration).ease(EASE);
    g.select("circle")
      .transition(t)
      .style("fill", future ? C.surface : d.core ? C.gold : C.ink)
      .style("stroke", future ? C.sealed : "transparent");
    g.select("text").transition(t).style("fill", future ? C.sealed : d.core ? C.ink : C.ink2);
  });
  stems.each(function (d) {
    if (!changed(this, d)) return;
    d3.select(this)
      .transition("paint")
      .duration(duration)
      .ease(EASE)
      .style("stroke", d.yr >= cutoff ? C.sealed : C.ink);
  });
}
