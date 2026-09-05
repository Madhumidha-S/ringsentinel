"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Measure a container's width and keep it current.
 *
 * Recharts' own <ResponsiveContainer> does not update under React 19 — it
 * latches onto its first measurement and never re-renders, which left every
 * chart drawing its bars into a ~230px band inside a 660px SVG. Owning the
 * measurement removes that dependency.
 *
 * A ResizeObserver alone is not quite enough: RO callbacks are delivered as
 * part of the rendering lifecycle, so a backgrounded or non-compositing tab can
 * change layout without ever firing one. A window `resize` listener covers that
 * case, and the caller pairs this with `overflow-x: auto` so that a stale width
 * scrolls inside its own box rather than widening the page or clipping data.
 */
export function useMeasuredWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const next = Math.max(240, el.clientWidth);
      setWidth((prev) => (Math.abs(prev - next) > 1 ? next : prev));
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    window.addEventListener("resize", update);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  return { ref, width };
}
