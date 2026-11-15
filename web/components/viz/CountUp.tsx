"use client";

import * as d3 from "d3";
import { useEffect, useRef } from "react";

import { EASE, ms, useInView } from "./core";

/**
 * A number that counts up from zero the first time it is seen. The server
 * renders the final value, so it reads correctly without JavaScript.
 */
export function CountUp({ value, digits = 0 }: { value: number; digits?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref);
  const format = d3.format(digits ? `,.${digits}f` : ",");

  useEffect(() => {
    const el = ref.current;
    if (!inView || !el || !ms(1)) return;
    const i = d3.interpolateNumber(0, value);
    d3.select(el)
      .transition()
      .duration(ms(value > 20 ? 1400 : 900))
      .ease(EASE)
      .tween("text", () => (t) => {
        el.textContent = format(i(t));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, value]);

  return <span ref={ref}>{format(value)}</span>;
}
