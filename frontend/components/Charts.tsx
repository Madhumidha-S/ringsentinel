"use client";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { useMeasuredWidth } from "./useMeasuredWidth";

const HEIGHT = 250;

const AXIS = { stroke: "#8b9ab4", fontSize: 11 };
const TOOLTIP = {
  contentStyle: { background: "#171f30", border: "1px solid #232d42", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#e6ecf7" },
};

export function RecallByLevel({
  model, rules,
}: {
  model: { evasion_level: number; recall: number; ring_accounts: number }[];
  rules: { evasion_level: number; recall: number }[];
}) {
  const ruleMap = new Map(rules.map((r) => [r.evasion_level, r.recall]));
  const data = model.map((m) => ({
    level: `L${m.evasion_level}`,
    Model: +(m.recall * 100).toFixed(1),
    "Rules baseline": +((ruleMap.get(m.evasion_level) ?? 0) * 100).toFixed(1),
  }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref}>
      <BarChart data={data} width={width} height={HEIGHT}
                margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="#1f2942" vertical={false} />
        <XAxis dataKey="level" tick={AXIS} axisLine={{ stroke: "#232d42" }} tickLine={false} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
        <Tooltip {...TOOLTIP} formatter={(v: number) => `${v}%`} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8b9ab4" }} />
        <Bar dataKey="Model" fill="#3395ff" radius={[3, 3, 0, 0]} />
        <Bar dataKey="Rules baseline" fill="#3b4761" radius={[3, 3, 0, 0]} />
      </BarChart>
    </div>
  );
}

export function CostCurve({
  curve, optimal,
}: {
  curve: { threshold: number; net_benefit_inr: number }[];
  optimal: number;
}) {
  const data = curve.map((c) => ({
    threshold: c.threshold,
    "Net benefit (lakh)": +(c.net_benefit_inr / 100000).toFixed(2),
  }));
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref}>
      <LineChart data={data} width={width} height={HEIGHT}
                 margin={{ top: 6, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="#1f2942" vertical={false} />
        <XAxis dataKey="threshold" tick={AXIS} axisLine={{ stroke: "#232d42" }}
               tickLine={false} tickFormatter={(v) => v.toFixed(1)} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} />
        <Tooltip {...TOOLTIP} formatter={(v: number) => `INR ${v} lakh`}
                 labelFormatter={(l) => `threshold ${(+l).toFixed(2)}`} />
        <ReferenceLine x={optimal} stroke="#2fbf71" strokeDasharray="4 3"
                       label={{ value: "chosen", fill: "#2fbf71", fontSize: 10, position: "top" }} />
        <Line type="monotone" dataKey="Net benefit (lakh)" stroke="#3395ff"
              strokeWidth={2} dot={false} />
      </LineChart>
    </div>
  );
}

export function PrCurve({ curve }: { curve: { precision: number; recall: number }[] }) {
  const data = curve
    .map((c) => ({ recall: +(c.recall * 100).toFixed(1), precision: +(c.precision * 100).toFixed(1) }))
    .sort((a, b) => a.recall - b.recall);
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  return (
    <div ref={ref}>
      <LineChart data={data} width={width} height={HEIGHT}
                 margin={{ top: 6, right: 12, left: -18, bottom: 0 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="#1f2942" vertical={false} />
        <XAxis dataKey="recall" tick={AXIS} axisLine={{ stroke: "#232d42" }} tickLine={false}
               unit="%" type="number" domain={[0, 100]} />
        <YAxis tick={AXIS} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
        <Tooltip {...TOOLTIP} formatter={(v: number) => `${v}%`} />
        <Line type="monotone" dataKey="precision" stroke="#2fbf71" strokeWidth={2} dot={false} />
      </LineChart>
    </div>
  );
}
