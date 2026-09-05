"use client";
import { useEffect, useState } from "react";
import EvidenceGraph from "@/components/EvidenceGraph";
import { CostCurve, PrCurve, RecallByLevel } from "@/components/Charts";

const inr = (n: number) =>
  n >= 1e5 ? `₹${(n / 1e5).toFixed(2)} L` : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

type Alert = {
  account_id: string; score: number; action: string; band: string; rationale: string;
  requires_human: boolean; severity: string; claims: number; claimed_inr: number;
  orders: number; linked_accounts: number; community_size: number;
  ground_truth_is_ring: boolean | null; effect: string;
};

export default function Page() {
  const [overview, setOverview] = useState<any>(null);
  const [evaluation, setEvaluation] = useState<any>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [reviewMsg, setReviewMsg] = useState<string>("");

  useEffect(() => {
    Promise.all([
      fetch("/api/overview").then((r) => r.json()),
      fetch("/api/evaluation").then((r) => r.json()),
      fetch("/api/alerts?limit=200").then((r) => r.json()),
    ]).then(([o, e, a]) => {
      setOverview(o); setEvaluation(e); setAlerts(a.alerts);
      if (a.alerts.length) setSelected(a.alerts[0].account_id);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null); setGraph(null); setReviewMsg("");
    fetch(`/api/accounts/${selected}`).then((r) => r.json()).then(setDetail);
    fetch(`/api/accounts/${selected}/graph?max_nodes=26`).then((r) => r.json()).then(setGraph);
  }, [selected]);

  const submitReview = async (verdict: string) => {
    if (!selected) return;
    const r = await fetch(`/api/accounts/${selected}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, note: `marked ${verdict} from dashboard`, reviewer: "analyst" }),
    }).then((x) => x.json());
    setReviewMsg(`Recorded as ledger entry #${r.index}. Chain head ${r.chain_head.slice(0, 12)}…`);
    fetch(`/api/accounts/${selected}`).then((x) => x.json()).then(setDetail);
  };

  if (!overview || !evaluation) return <div className="loading">Building population, backtesting and scoring…</div>;

  const m = overview.model;
  const op = overview.at_operating_point;
  const bp = overview.banded_policy;
  const rules = overview.rules_baseline;
  // Computed server-side over every decision, not over the truncated alert page.
  const cv = overview.customer_visible;

  return (
    <div className="wrap">
      <header className="top">
        <h1>RingSentinel</h1>
        <span className="badge accent">Track 2 · AI Risk Manager</span>
        <span className="badge ok">Defence only · cannot move money</span>
        <span className={`badge ${overview.ledger.verified ? "ok" : ""}`}>
          Ledger {overview.ledger.verified ? "verified" : "BROKEN"} · {overview.ledger.entries} entries
        </span>
        <div className="sub" style={{ width: "100%", marginTop: 6 }}>
          Refund &amp; promotion abuse rings on a merchant payment stream. Trained on accounts up to
          day {overview.split.train_cutoff_day}; every number below is measured on{" "}
          {overview.split.n_test.toLocaleString()} accounts first seen <em>after</em> that cutoff.
        </div>
      </header>

      <div className="grid kpis">
        <div className="card">
          <h3>Average precision</h3>
          <div className="v">{m.average_precision.toFixed(3)}</div>
          <div className="foot">Rules baseline {rules.average_precision.toFixed(3)} on the same fold</div>
        </div>
        <div className="card">
          <h3>Precision / recall</h3>
          <div className="v">{pct(op.precision)} / {pct(op.recall)}</div>
          <div className="foot">At the cost-optimal threshold {m.cost_optimal_threshold.toFixed(2)}</div>
        </div>
        <div className="card">
          <h3>Abuse exposure caught</h3>
          <div className="v">{inr(m.exposure_caught_inr)}</div>
          <div className="foot">of {inr(m.abuse_exposure_inr)} claimed by ring accounts</div>
        </div>
        <div className="card">
          <h3>Net benefit</h3>
          <div className="v">{inr(bp.net_benefit_inr)}</div>
          <div className="foot">Shipped 3-band policy, after review costs</div>
        </div>
        <div className="card">
          <h3>Customers wrongly restricted</h3>
          <div className="v" style={{ color: cv.on_legitimate_accounts <= 5 ? "var(--good)" : "var(--warn)" }}>
            {cv.on_legitimate_accounts}
          </div>
          <div className="foot">
            of {cv.total_actions} customer-visible actions ({pct(cv.precision)} precision).
            The {cv.raw_model_false_positives} raw model false positives are absorbed into
            review or monitoring.
          </div>
        </div>
      </div>

      <div className="grid two">
        <div className="section card">
          <h2>Recall by adversary evasion level</h2>
          <p className="note">
            The headline score hides the only thing that matters. Rules and model are
            indistinguishable against naive rings — and the gap opens exactly where the money is,
            against operators who partition into cells and rotate infrastructure.
          </p>
          <RecallByLevel
            model={evaluation.recall_by_evasion_level}
            rules={evaluation.rules_recall_by_evasion_level}
          />
        </div>
        <div className="section card">
          <h2>Choosing the threshold in rupees</h2>
          <p className="note">
            Not by F1. Each point prices catching an abuser against restricting a real customer
            (₹2,400 in lost lifetime value and support). The peak is the operating point we ship.
          </p>
          <CostCurve curve={evaluation.cost_curve} optimal={m.cost_optimal_threshold} />
        </div>
      </div>

      <div className="grid two">
        <div className="section card">
          <h2>Alert queue</h2>
          <p className="note">
            {bp.auto_actioned} auto-actioned · {bp.queued_for_review} queued to a human ·{" "}
            {bp.missed} missed. Ground truth is shown so you can audit the calls; the system never
            sees it.
          </p>
          <div className="scrollbox">
            <table>
              <thead>
                <tr>
                  <th>Account</th><th>Score</th><th>Action</th><th>Claims</th>
                  <th>Linked</th><th>Ring?</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.account_id}
                      className={`row ${selected === a.account_id ? "sel" : ""}`}
                      onClick={() => setSelected(a.account_id)}>
                    <td className="mono">{a.account_id}</td>
                    <td className="mono">{a.score.toFixed(3)}</td>
                    <td><span className={`pill ${a.action}`}>{a.action.replace(/_/g, " ")}</span></td>
                    <td className="mono">{a.claims}</td>
                    <td className="mono">{a.linked_accounts}</td>
                    <td>
                      <span className={`pill ${a.ground_truth_is_ring ? "t" : "f"}`}>
                        {a.ground_truth_is_ring ? "ring" : "legit"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="section card detail">
          <h2>Evidence · {selected}</h2>
          {!detail ? (
            <div className="loading">Loading evidence…</div>
          ) : (
            <>
              <div className="narr">{detail.narration?.text}</div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 10 }}>
                Narration source: <strong>{detail.narration?.source}</strong> ·{" "}
                {detail.narration?.validation}
              </div>

              {graph && <EvidenceGraph nodes={graph.nodes} edges={graph.edges} />}

              <div style={{ marginTop: 14 }}>
                <dl className="kv">
                  <dt>Decision</dt>
                  <dd>
                    <span className={`pill ${detail.decision?.action}`}>
                      {detail.decision?.action?.replace(/_/g, " ")}
                    </span>{" "}
                    {detail.decision?.requires_human && (
                      <span className="badge">human confirmation required</span>
                    )}
                  </dd>
                  <dt>Effect</dt><dd>{detail.action_effect?.effect}</dd>
                  <dt>Reversal</dt><dd>{detail.action_effect?.reversal}</dd>
                  <dt>Evidence</dt>
                  <dd>
                    <strong>{detail.evidence.sufficiency}</strong> — {detail.evidence.sufficiency_reason}
                  </dd>
                  <dt>Rationale</dt><dd>{detail.decision?.rationale}</dd>
                </dl>
              </div>

              <div style={{ marginTop: 12 }}>
                <h3 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--muted)",
                             letterSpacing: ".07em" }}>
                  Contributing factors
                </h3>
                <ul className="clean ev">
                  {detail.evidence.contributing_factors.map((f: any) => (
                    <li key={f.feature}>
                      • {f.statement}{" "}
                      <span style={{ color: "var(--muted)" }}>
                        (population median {f.population_median}
                        {f.lift ? `, ${f.lift}× baseline` : ""})
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div style={{ marginTop: 12 }}>
                <h3 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--muted)",
                             letterSpacing: ".07em" }}>
                  Audit trail
                </h3>
                <ul className="clean ledger">
                  {detail.ledger.map((e: any) => (
                    <li key={e.index}>
                      #{e.index} {e.event_type} · {e.entry_hash}…
                    </li>
                  ))}
                </ul>
              </div>

              <div style={{ marginTop: 14 }}>
                <button className="act" onClick={() => submitReview("confirm")}>Confirm abuse</button>
                <button className="act" onClick={() => submitReview("clear")}>Clear account</button>
                <button className="act" onClick={() => submitReview("escalate")}>Escalate</button>
                {reviewMsg && (
                  <div style={{ fontSize: 11.5, color: "var(--good)", marginTop: 8 }}>{reviewMsg}</div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="section card">
        <h2>Precision–recall on the held-out fold</h2>
        <p className="note">
          {overview.split.n_test.toLocaleString()} accounts, {pct(overview.split.test_prevalence)}{" "}
          prevalence. Average precision {m.average_precision.toFixed(3)}.
        </p>
        <div style={{ maxWidth: 620 }}>
          <PrCurve curve={evaluation.pr_curve} />
        </div>
      </div>
    </div>
  );
}
