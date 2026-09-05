"use client";
import { useMemo } from "react";

type Node = {
  id: string;
  score: number;
  focus: boolean;
  degree: number;
  ground_truth_is_ring?: boolean | null;
};
type Edge = { source: string; target: string; weight: number; identifier_types: string[] };

export const TYPE_COLOR: Record<string, string> = {
  email_norm: "#7f56d9",
  phone: "#c11574",
  device_id: "#3395ff",
  card_token: "#0e9f6e",
  ship_address_norm: "#dc6803",
  ip: "#98a2b3",
};
const TYPE_LABEL: Record<string, string> = {
  email_norm: "inbox",
  phone: "phone",
  device_id: "device",
  card_token: "card",
  ship_address_norm: "address",
  ip: "network",
};

/**
 * Deterministic radial layout: focus account at the centre, its cluster around
 * it, ordered by risk. A force simulation would settle differently on every
 * render, which makes evidence harder to read, not easier.
 */
export default function EvidenceGraph({
  nodes, edges, width = 560, height = 340,
}: {
  nodes: Node[]; edges: Edge[]; width?: number; height?: number;
}) {
  const pos = useMemo(() => {
    const map: Record<string, { x: number; y: number }> = {};
    const cx = width / 2;
    const cy = height / 2;
    const focus = nodes.find((n) => n.focus);
    const others = nodes.filter((n) => !n.focus).sort((a, b) => b.score - a.score);
    if (focus) map[focus.id] = { x: cx, y: cy };
    const r = Math.min(width, height) / 2 - 44;
    others.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(1, others.length) - Math.PI / 2;
      const ring = others.length > 12 && i % 2 === 1 ? r * 0.6 : r;
      map[n.id] = { x: cx + ring * Math.cos(a), y: cy + ring * Math.sin(a) };
    });
    return map;
  }, [nodes, width, height]);

  const fill = (n: Node) =>
    n.focus ? "#3395ff" : n.score >= 0.7 ? "#f97066" : n.score >= 0.28 ? "#fdb022" : "#cdd3de";

  const used = Array.from(new Set(edges.flatMap((e) => e.identifier_types)));

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="Identity links between this account and its cluster"
           style={{ display: "block" }}>
        <rect width={width} height={height} fill="#fafbfc" rx="8" />
        {edges.map((e, i) => {
          const a = pos[e.source];
          const b = pos[e.target];
          if (!a || !b) return null;
          const primary = e.identifier_types[0] ?? "ip";
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={TYPE_COLOR[primary] ?? "#cdd3de"}
                  strokeWidth={Math.max(1, Math.min(3.6, e.weight * 1.6))}
                  strokeOpacity={0.55} strokeLinecap="round" />
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const r = n.focus ? 11.5 : 7.5;
          return (
            <g key={n.id}>
              {n.focus && (
                <circle cx={p.x} cy={p.y} r={r + 5} fill="none" stroke="#3395ff"
                        strokeOpacity={0.24} strokeWidth={2} />
              )}
              <circle cx={p.x} cy={p.y} r={r} fill={fill(n)}
                      stroke={n.ground_truth_is_ring ? "#b42318" : "#ffffff"}
                      strokeWidth={n.ground_truth_is_ring ? 2 : 1.5} />
              <text x={p.x} y={p.y + r + 11} textAnchor="middle" fontSize="8.5"
                    fill="#98a2b3" fontFamily="ui-monospace, Menlo, monospace">
                {n.id.replace("acc_", "")}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ marginTop: 9 }}>
        {used.map((k) => (
          <span key={k} className="legend-chip">
            <span className="swatch" style={{ background: TYPE_COLOR[k] ?? "#cdd3de" }} />
            {TYPE_LABEL[k] ?? k}
          </span>
        ))}
      </div>
      <p className="footnote">
        Line colour is the identifier type linking each pair; thickness is evidence weight after
        inverse-degree discounting. A red ring marks a true ring member in the held-out labels —
        shown so you can audit the calls, never used to make them.
      </p>
    </div>
  );
}
