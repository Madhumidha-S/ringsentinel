"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Measure a container's width with a ResizeObserver.
 *
 * Recharts' own <ResponsiveContainer> does not update under React 19 — it
 * latches onto its first measurement and never re-renders, which left every
 * chart drawing its bars into a ~230px band inside a 660px SVG. Owning the
 * measurement ourselves removes the dependency on recharts internals.
 */
export function useMeasuredWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => setWidth(Math.max(240, el.clientWidth));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}
