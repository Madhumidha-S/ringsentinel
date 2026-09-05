"use client";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  ReferenceLine, Tooltip, XAxis, YAxis,
} from "recharts";
import { useMeasuredWidth } from "./useMeasuredWidth";

const INK = "#667085";
const GRID = "#eaecf0";
const BRAND = "#3395ff";
const BASE = "#b6bece";
const GOOD = "#0e9f6e";
const BAD = "#b42318";

const AXIS = { stroke: INK, fontSize: 11 };
const TIP = {
  contentStyle: {
    background: "#fff",
    border: "1px solid #e4e7ec",
    borderRadius: 8,
    fontSize: 12,
    boxShadow: "0 4px 12px rgba(16,24,40,0.08)",
    color: "#0d1526",
  },
  labelStyle: { color: "#0d1526", fontWeight: 600, marginBottom: 2 },
};

/** The headline chart: where the model actually earns its keep. */
export function RecallByLevel({
  model, rules, height = 274,
}: {
  model: { evasion_level: number; recall: number; ring_accounts: number }[];
  rules: { evasion_level: number; recall: number }[];
  height?: number;
}) {
  const ruleMap = new Map(rules.map((r) => [r.evasion_level, r.recall]));
  const data = model.map((m) => ({
    level: `L${m.evasion_level}`,
    Model: +(m.recall * 100).toFixed(1),
    "Rule baseline": +((ruleMap.get(m.evasion_level) ?? 0) * 100).toFixed(1),
    n: m.ring_accounts,
  }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref} style={{ overflowX: "auto" }}>
      <BarChart data={data} width={width} height={height}
                margin={{ top: 8, right: 10, left: -20, bottom: 0 }} barGap={3}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="level" tick={AXIS} axisLine={{ stroke: "#e4e7ec" }} tickLine={false} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
        <Tooltip {...TIP} cursor={{ fill: "rgba(51,149,255,0.06)" }}
                 formatter={(v: number) => `${v}%`}
                 labelFormatter={(l) => {
                   const row = data.find((d) => d.level === l);
                   return `Evasion ${l} · ${row?.n ?? 0} ring accounts`;
                 }} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: INK, paddingTop: 4 }} iconType="circle"
                iconSize={8} />
        {/* Everything right of here is where a hand-written rule set falls apart. */}
        <ReferenceLine x="L7" stroke="#d0d5dd" strokeDasharray="4 4" />
        <Bar dataKey="Model" fill={BRAND} radius={[3, 3, 0, 0]} maxBarSize={26} />
        <Bar dataKey="Rule baseline" fill={BASE} radius={[3, 3, 0, 0]} maxBarSize={26} />
      </BarChart>
    </div>
  );
}

export function CostCurve({
  curve, optimal, height = 230,
}: {
  curve: { threshold: number; net_benefit_inr: number }[];
  optimal: number;
  height?: number;
}) {
  const data = curve.map((c) => ({
    threshold: c.threshold,
    lakh: +(c.net_benefit_inr / 1e5).toFixed(2),
  }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref} style={{ overflowX: "auto" }}>
      <AreaChart data={data} width={width} height={height}
                 margin={{ top: 8, right: 12, left: -14, bottom: 0 }}>
        <defs>
          <linearGradient id="cost" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={BRAND} stopOpacity={0.22} />
            <stop offset="100%" stopColor={BRAND} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        {/* 101 points with a 1-decimal formatter renders duplicate tick labels
            (0.0 0.1 0.1 0.2 0.2 ...), so the ticks are pinned explicitly. */}
        <XAxis dataKey="threshold" type="number" domain={[0, 1]}
               ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS}
               axisLine={{ stroke: "#e4e7ec" }} tickLine={false}
               tickFormatter={(v) => v.toFixed(1)} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="L" />
        <Tooltip {...TIP} formatter={(v: number) => [`₹${v} lakh`, "Net benefit"]}
                 labelFormatter={(l) => `Threshold ${(+l).toFixed(2)}`} />
        <ReferenceLine x={optimal} stroke={GOOD} strokeDasharray="4 3"
                       label={{ value: "chosen", fill: GOOD, fontSize: 10.5, position: "top" }} />
        <Area type="monotone" dataKey="lakh" stroke={BRAND} strokeWidth={2} fill="url(#cost)" />
      </AreaChart>
    </div>
  );
}

export function PrCurve({
  curve, height = 230,
}: { curve: { precision: number; recall: number }[]; height?: number }) {
  const data = curve
    .map((c) => ({ recall: +(c.recall * 100).toFixed(1), precision: +(c.precision * 100).toFixed(1) }))
    .sort((a, b) => a.recall - b.recall);
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref} style={{ overflowX: "auto" }}>
      <LineChart data={data} width={width} height={height}
                 margin={{ top: 8, right: 12, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="recall" tick={AXIS} axisLine={{ stroke: "#e4e7ec" }} tickLine={false}
               unit="%" type="number" domain={[0, 100]} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
        <Tooltip {...TIP} formatter={(v: number) => `${v}%`}
                 labelFormatter={(l) => `Recall ${l}%`} />
        <Line type="monotone" dataKey="precision" stroke={GOOD} strokeWidth={2} dot={false}
              name="Precision" />
      </LineChart>
    </div>
  );
}

/** Precision as organised abuse gets rarer. The honest caveat, drawn. */
export function PrevalenceCurve({
  rows, height = 216,
}: {
  rows: {
    achieved_prevalence: number; precision_mean: number;
    precision_p2_5: number; precision_p97_5: number; recall_mean: number;
  }[];
  height?: number;
}) {
  const data = rows.map((r) => ({
    prev: +(r.achieved_prevalence * 100).toFixed(2),
    Precision: +(r.precision_mean * 100).toFixed(1),
    Recall: +(r.recall_mean * 100).toFixed(1),
  }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref} style={{ overflowX: "auto" }}>
      <LineChart data={data} width={width} height={height}
                 margin={{ top: 8, right: 14, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="prev" tick={AXIS} axisLine={{ stroke: "#e4e7ec" }} tickLine={false}
               unit="%" />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" domain={[50, 100]} />
        <Tooltip {...TIP} formatter={(v: number) => `${v}%`}
                 labelFormatter={(l) => `Prevalence ${l}%`} />
        <Legend wrapperStyle={{ fontSize: 11.5, color: INK, paddingTop: 4 }} iconType="circle"
                iconSize={8} />
        <Line type="monotone" dataKey="Precision" stroke={BAD} strokeWidth={2}
              dot={{ r: 2.5, fill: BAD }} />
        <Line type="monotone" dataKey="Recall" stroke={GOOD} strokeWidth={2}
              strokeDasharray="4 3" dot={{ r: 2.5, fill: GOOD }} />
      </LineChart>
    </div>
  );
}

/** Which feature families carry the load against sophisticated rings. */
export function AblationBars({
  rows, height = 250,
}: {
  rows: { feature_set: string; recall_L7_L9: number; average_precision: number }[];
  height?: number;
}) {
  const order = [
    "behavioural_only", "behavioural+temporal", "behavioural+churn",
    "no_graph", "graph_only", "no_neighbour", "all",
  ];
  const label: Record<string, string> = {
    behavioural_only: "Behaviour only",
    "behavioural+temporal": "Behaviour + time",
    "behavioural+churn": "Behaviour + churn",
    no_graph: "No graph",
    graph_only: "Graph only",
    no_neighbour: "No neighbour",
    all: "All features",
  };
  const data = order
    .map((k) => rows.find((r) => r.feature_set === k))
    .filter(Boolean)
    .map((r) => ({
      name: label[r!.feature_set] ?? r!.feature_set,
      hard: +(r!.recall_L7_L9 * 100).toFixed(1),
      full: r!.feature_set === "all",
    }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref} style={{ overflowX: "auto" }}>
      <BarChart data={data} width={width} height={height} layout="vertical"
                margin={{ top: 4, right: 34, left: 118, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} unit="%" tick={AXIS}
               axisLine={{ stroke: "#e4e7ec" }} tickLine={false} />
        <YAxis type="category" dataKey="name" tick={{ ...AXIS, fontSize: 11 }}
               axisLine={false} tickLine={false} width={116} />
        <Tooltip {...TIP} cursor={{ fill: "rgba(51,149,255,0.06)" }}
                 formatter={(v: number) => [`${v}%`, "Recall on L7–L9"]} />
        <Bar dataKey="hard" radius={[0, 3, 3, 0]} maxBarSize={16}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.full ? BRAND : d.hard < 20 ? BAD : BASE} />
          ))}
        </Bar>
      </BarChart>
    </div>
  );
}
