"use client";

// One tooltip per chart. The value leads; the label follows; rows key their
// series with a short stroke. React escapes every string, so labels drawn from
// data never reach the page as markup.
//
// The tip is portalled to <body> and placed in page coordinates, so a chart's
// scrolling frame can never clip it. It prefers the right of the point, flips
// left when there is no room, and is clamped inside the viewport.

import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface TipRow {
  color?: string;
  label: string;
  value: string;
}

export interface Tip {
  /** Position of the point in the chart's own coordinates (the svg's top-left is 0,0). */
  x: number;
  y: number;
  value: string;
  label: string;
  rows?: TipRow[];
  note?: string;
}

const GAP = 14;
const EDGE = 8;

export function Tooltip({ tip }: { tip: Tip | null }) {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);
  useLayoutEffect(() => setMounted(true), []);

  useLayoutEffect(() => {
    const el = tipRef.current;
    const chart = anchorRef.current?.parentElement;
    if (!tip || !el || !chart) return;
    const svg = chart.querySelector("svg") ?? chart;
    const r = svg.getBoundingClientRect();
    const px = r.left + tip.x;
    const py = r.top + tip.y;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    let left = px + GAP;
    let top = py - h / 2;
    if (left + w > vw - EDGE) left = px - GAP - w;
    if (left < EDGE) {
      // No room either side: centre over the point and sit above or below it.
      left = Math.min(Math.max(EDGE, px - w / 2), vw - EDGE - w);
      top = py - GAP - h >= EDGE ? py - GAP - h : py + GAP;
    }
    top = Math.min(Math.max(EDGE, top), vh - EDGE - h);
    el.style.left = `${Math.round(left + window.scrollX)}px`;
    el.style.top = `${Math.round(top + window.scrollY)}px`;
    el.style.visibility = "visible";
  }, [tip]);

  return (
    <>
      <span ref={anchorRef} hidden />
      {mounted &&
        tip &&
        createPortal(
          <div ref={tipRef} className="viz-tip" role="status" style={{ visibility: "hidden" }}>
            <div className="viz-tip-value">{tip.value}</div>
            <div className="viz-tip-label">{tip.label}</div>
            {tip.rows && tip.rows.length > 0 && (
              <div className="viz-tip-rows">
                {tip.rows.map((r) => (
                  <div key={r.label} className="viz-tip-row">
                    <i style={{ background: r.color ?? "transparent" }} />
                    <span>{r.label}</span>
                    <b>{r.value}</b>
                  </div>
                ))}
              </div>
            )}
            {tip.note && <div className="viz-tip-note">{tip.note}</div>}
          </div>,
          document.body,
        )}
    </>
  );
}
