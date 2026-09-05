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

const TYPE_COLOR: Record<string, string> = {
  email_norm: "#c084fc",
  phone: "#f0abfc",
  device_id: "#3395ff",
  card_token: "#2fbf71",
  ship_address_norm: "#e8a33d",
  ip: "#4b5a75",
};

/**
 * Deterministic radial layout: the focus account at the centre, its cluster
 * around it, ordered by risk score. A force simulation would move on every
 * render and make the evidence harder, not easier, to read.
 */
export default function EvidenceGraph({
  nodes,
  edges,
  width = 520,
  height = 360,
}: {
  nodes: Node[];
  edges: Edge[];
  width?: number;
  height?: number;
}) {
  const pos = useMemo(() => {
    const map: Record<string, { x: number; y: number }> = {};
    const cx = width / 2;
    const cy = height / 2;
    const focus = nodes.find((n) => n.focus);
    const others = nodes.filter((n) => !n.focus).sort((a, b) => b.score - a.score);
    if (focus) map[focus.id] = { x: cx, y: cy };
    const r = Math.min(width, height) / 2 - 46;
    others.forEach((n, i) => {
      const a = (2 * Math.PI * i) / Math.max(1, others.length) - Math.PI / 2;
      // Two rings when the cluster is large, so labels stay readable.
      const ring = others.length > 12 && i % 2 === 1 ? r * 0.62 : r;
      map[n.id] = { x: cx + ring * Math.cos(a), y: cy + ring * Math.sin(a) };
    });
    return map;
  }, [nodes, width, height]);

  const colourFor = (n: Node) =>
    n.focus ? "#3395ff" : n.score >= 0.7 ? "#e5484d" : n.score >= 0.28 ? "#e8a33d" : "#4b5a75";

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="Identity links between this account and its cluster">
        {edges.map((e, i) => {
          const a = pos[e.source];
          const b = pos[e.target];
          if (!a || !b) return null;
          const primary = e.identifier_types[0] ?? "ip";
          return (
            <line
              key={i}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={TYPE_COLOR[primary] ?? "#334"}
              strokeWidth={Math.max(0.7, Math.min(3.4, e.weight * 1.5))}
              strokeOpacity={0.5}
            />
          );
        })}
        {nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const r = n.focus ? 11 : 7;
          return (
            <g key={n.id}>
              <circle cx={p.x} cy={p.y} r={r} fill={colourFor(n)}
                      stroke={n.ground_truth_is_ring ? "#ff8085" : "#0b0f17"}
                      strokeWidth={n.ground_truth_is_ring ? 2 : 1.5} />
              <text x={p.x} y={p.y + r + 11} textAnchor="middle" fontSize="8.5"
                    fill="#8b9ab4" fontFamily="ui-monospace, Menlo, monospace">
                {n.id.replace("acc_", "")}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ marginTop: 6 }}>
        {Object.entries(TYPE_COLOR).map(([k, v]) => (
          <span key={k} className="chip">
            <span style={{ color: v }}>■</span> {k.replace("_norm", "").replace("_id", "")}
          </span>
        ))}
        <div style={{ fontSize: 11, color: "#8b9ab4", marginTop: 6, lineHeight: 1.5 }}>
          Line colour is the identifier type that links the pair; thickness is evidence weight.
          A red outline marks an account that is a true ring member in the held-out labels —
          shown so you can audit the calls, never used to make them.
        </div>
      </div>
    </div>
  );
}
