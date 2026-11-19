"use client";

// One hint for the whole app, drawn like a chart's tooltip. Pages keep writing
// a plain `title`, so a hint still works before this script loads; on first
// hover or focus the title moves to `data-tip`, which stops the browser's own
// tooltip from appearing beside this one. The text stays available to
// assistive technology as `aria-description`.
//
// The hint is fixed to the viewport, so a scrolling table can never clip it.

import { useEffect, useRef, useState } from "react";

const GAP = 10;
const EDGE = 8;

interface Hint {
  text: string;
  rect: DOMRect;
}

function claim(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null;
  const el = target.closest<HTMLElement>("[title], [data-tip]");
  if (!el) return null;
  const title = el.getAttribute("title");
  if (title) {
    el.dataset.tip = title;
    el.setAttribute("aria-description", title);
    el.removeAttribute("title");
  }
  return el.dataset.tip ? el : null;
}

export function Hints() {
  const [hint, setHint] = useState<Hint | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const show = (e: Event) => {
      const el = claim(e.target);
      setHint(el ? { text: el.dataset.tip ?? "", rect: el.getBoundingClientRect() } : null);
    };
    const hide = () => setHint(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    document.addEventListener("pointerover", show);
    document.addEventListener("focusin", show);
    document.addEventListener("focusout", hide);
    document.addEventListener("pointerdown", hide);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, { capture: true, passive: true });
    return () => {
      document.removeEventListener("pointerover", show);
      document.removeEventListener("focusin", show);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("pointerdown", hide);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, { capture: true });
    };
  }, []);

  // Above the element and centred on it; below when there is no room above.
  useEffect(() => {
    const el = tipRef.current;
    if (!hint || !el) return;
    const { rect } = hint;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const vw = document.documentElement.clientWidth;
    const left = Math.min(Math.max(EDGE, rect.left + rect.width / 2 - w / 2), vw - EDGE - w);
    const top = rect.top - GAP - h >= EDGE ? rect.top - GAP - h : rect.bottom + GAP;
    el.style.left = `${Math.round(left)}px`;
    el.style.top = `${Math.round(top)}px`;
    el.style.visibility = "visible";
  }, [hint]);

  if (!hint) return null;
  return (
    <div ref={tipRef} className="viz-tip hint" role="tooltip" style={{ visibility: "hidden" }}>
      <div className="viz-tip-label">{hint.text}</div>
    </div>
  );
}
