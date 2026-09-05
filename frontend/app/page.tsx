"use client";
import { useEffect, useState } from "react";
import EvidenceGraph from "@/components/EvidenceGraph";
import { CostCurve, PrCurve, RecallByLevel } from "@/components/Charts";
import { Ablation, Fairness, Prevalence, SeedVariance } from "@/components/Studies";

const inr = (n: number) =>
  n >= 1e5
    ? `₹${(n / 1e5).toFixed(2)} L`
    : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const pct = (n: number, d = 1) => `${(n * 100).toFixed(d)}%`;

type Alert = {
  account_id: string; score: number; action: string; band: string; rationale: string;
  requires_human: boolean; severity: string; claims: number; claimed_inr: number;
  orders: number; linked_accounts: number; community_size: number;
  ground_truth_is_ring: boolean | null; effect: string;
};

export default function Page() {
  const [overview, setOverview] = useState<any>(null);
  const [evaluation, setEvaluation] = useState<any>(null);
  const [studies, setStudies] = useState<any>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [graph, setGraph] = useState<any>(null);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/api/overview").then((r) => r.json()),
      fetch("/api/evaluation").then((r) => r.json()),
      fetch("/api/alerts?limit=250").then((r) => r.json()),
      fetch("/api/studies").then((r) => r.json()).catch(() => ({ available: false })),
    ]).then(([o, e, a, s]) => {
      setOverview(o); setEvaluation(e); setAlerts(a.alerts); setStudies(s);
      if (a.alerts.length) setSelected(a.alerts[0].account_id);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null); setGraph(null); setFlash("");
    fetch(`/api/accounts/${selected}`).then((r) => r.json()).then(setDetail);
    fetch(`/api/accounts/${selected}/graph?max_nodes=26`).then((r) => r.json()).then(setGraph);
  }, [selected]);

  const review = async (verdict: string) => {
    if (!selected) return;
    const r = await fetch(`/api/accounts/${selected}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, note: `${verdict} from dashboard`, reviewer: "analyst" }),
    }).then((x) => x.json());
    setFlash(`Ledger entry #${r.index} · chain head ${r.chain_head.slice(0, 12)}…`);
    fetch(`/api/accounts/${selected}`).then((x) => x.json()).then(setDetail);
  };

  if (!overview || !evaluation) {
    return <div className="loading">Building population, backtesting and scoring…</div>;
  }

  const m = overview.model;
  const op = overview.at_operating_point;
  const bp = overview.banded_policy;
  const rules = overview.rules_baseline;
  const cv = overview.customer_visible;
  const sv = studies?.available ? studies.seed_variance.summary : null;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="wordmark"><span className="dot" />RingSentinel</div>
          <span className="chip brand">Track 2 · AI Risk Manager</span>
          <span className="chip good">Defence only · cannot move money</span>
          <span className={`chip ${overview.ledger.verified ? "good" : "bad"}`}>
            Ledger {overview.ledger.verified ? "verified" : "BROKEN"} · {overview.ledger.entries}
          </span>
          <div className="spacer" />
          <div className="runmeta">
            train ≤ day {overview.split.train_cutoff_day} · score day {overview.split.score_day}
            <br />
            {overview.split.n_test.toLocaleString()} held-out accounts ·{" "}
            {pct(overview.split.test_prevalence, 2)} prevalence
          </div>
        </div>
      </header>

      <div className="wrap">
        <div className="verdict">
          <h2>A hand-written rule set matches this model against careless fraud rings — and
            collapses against disciplined ones.</h2>
          <p>
            Organised refund abuse is not one bad customer; it is one operator running many
            accounts and spreading claims thinly enough that none looks abnormal. RingSentinel
            scores the <span className="accent">ring</span>, not the account. Everything below is
            measured on accounts first seen <em>after</em> the training cutoff — and where the
            model actually earns its keep is the right-hand side of the first chart.
          </p>
        </div>

        <div className="grid kpis section">
          <div className="card card-pad kpi">
            <div className="label">Average precision</div>
            <div className="value">{sv ? sv.model_ap.mean.toFixed(3) : m.average_precision.toFixed(3)}</div>
            <div className="sub">
              {sv ? <>± {sv.model_ap.std.toFixed(3)} across 7 seeds · rule baseline{" "}
                <b>{sv.rules_ap.mean.toFixed(3)}</b></>
                : <>rule baseline <b>{rules.average_precision.toFixed(3)}</b></>}
            </div>
          </div>
          <div className="card card-pad kpi">
            <div className="label">Precision / recall</div>
            <div className="value">{pct(op.precision)} / {pct(op.recall)}</div>
            <div className="sub">at cost-optimal threshold <b>{m.cost_optimal_threshold.toFixed(2)}</b></div>
          </div>
          <div className="card card-pad kpi">
            <div className="label">Abuse exposure caught</div>
            <div className="value pos">{inr(m.exposure_caught_inr)}</div>
            <div className="sub">of <b>{inr(m.abuse_exposure_inr)}</b> claimed by ring accounts</div>
          </div>
          <div className="card card-pad kpi">
            <div className="label">Net benefit</div>
            <div className="value">{inr(bp.net_benefit_inr)}</div>
            <div className="sub">3-band policy, after <b>{inr(bp.review_cost_inr)}</b> of review</div>
          </div>
          <div className="card card-pad kpi">
            <div className="label">Customers wrongly restricted</div>
            <div className={`value ${cv.on_legitimate_accounts <= 5 ? "pos" : "neg"}`}>
              {cv.on_legitimate_accounts}
            </div>
            <div className="sub">
              of {cv.total_actions} customer-visible actions · <b>{pct(cv.precision, 1)}</b> precision.
              The {cv.raw_model_false_positives} raw false positives are absorbed into review.
            </div>
          </div>
        </div>

        <div className="section eyebrow">The finding</div>
        <div className="grid split">
          <div className="card">
            <div className="card-head">
              <h2>Recall by adversary evasion level</h2>
              <p className="note">
                Ten levels of attacker share one population. Level 0 puts seventeen accounts on one
                device; level 9 splits into disjoint pairs, burns a fresh device on 86% of orders
                and waits sixteen days before extracting. Left of the dashed line, the rule
                baseline is indistinguishable from the model.
              </p>
            </div>
            <div className="card-body">
              <RecallByLevel model={evaluation.recall_by_evasion_level}
                             rules={evaluation.rules_recall_by_evasion_level} />
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h2>Model vs. rule baseline</h2>
              <p className="note">
                The baseline is deliberately good — it uses the same graph and its thresholds are
                tuned on the training split.
              </p>
            </div>
            <div className="card-body">
              <table>
                <thead>
                  <tr><th>Metric</th><th className="num">Model</th><th className="num">Rules</th></tr>
                </thead>
                <tbody>
                  <tr><td>Average precision</td>
                    <td className="num">{m.average_precision.toFixed(3)}</td>
                    <td className="num">{rules.average_precision.toFixed(3)}</td></tr>
                  <tr><td>Precision</td>
                    <td className="num">{op.precision.toFixed(3)}</td>
                    <td className="num">{rules.at_cost_optimal.precision.toFixed(3)}</td></tr>
                  <tr><td>Recall</td>
                    <td className="num">{op.recall.toFixed(3)}</td>
                    <td className="num">{rules.at_cost_optimal.recall.toFixed(3)}</td></tr>
                  <tr><td>False positives</td>
                    <td className="num">{op.fp}</td>
                    <td className="num">{rules.at_cost_optimal.fp}</td></tr>
                  <tr><td>Missed rings</td>
                    <td className="num">{op.fn}</td>
                    <td className="num">{rules.at_cost_optimal.fn}</td></tr>
                  <tr><td>Net benefit</td>
                    <td className="num">{inr(m.net_benefit_inr)}</td>
                    <td className="num">{inr(rules.net_benefit_inr)}</td></tr>
                </tbody>
              </table>
              <p className="footnote">
                The baseline has <em>higher</em> precision. It buys that by only flagging the
                obvious, and pays with {rules.at_cost_optimal.fn} missed rings against the model&rsquo;s{" "}
                {op.fn}.
              </p>
            </div>
          </div>
        </div>

        <div className="section eyebrow">Triage queue</div>
        <div className="grid split">
          <div className="card">
            <div className="card-head">
              <h2>Alerts</h2>
              <p className="note">
                {bp.auto_actioned} auto-actioned · {bp.queued_for_review} queued to a human ·{" "}
                {bp.missed} missed. Ground truth is shown so you can audit the calls; the system
                never sees it.
              </p>
            </div>
            <div className="card-body" style={{ paddingLeft: 0, paddingRight: 0 }}>
              <div className="scroller">
                <table>
                  <thead>
                    <tr>
                      <th>Account</th><th className="num">Score</th><th>Action</th>
                      <th className="num">Claims</th><th className="num">Linked</th><th>Truth</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((a) => (
                      <tr key={a.account_id}
                          className={`pick ${selected === a.account_id ? "on" : ""}`}
                          onClick={() => setSelected(a.account_id)}>
                        <td className="mono">{a.account_id}</td>
                        <td className="num">{a.score.toFixed(3)}</td>
                        <td><span className={`pill ${a.action}`}>
                          {a.action.replace(/_/g, " ")}</span></td>
                        <td className="num">{a.claims}</td>
                        <td className="num">{a.linked_accounts}</td>
                        <td><span className={`pill ${a.ground_truth_is_ring ? "ring" : "legit"}`}>
                          {a.ground_truth_is_ring ? "ring" : "legit"}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="card sticky">
            <div className="card-head">
              <h2>Evidence · <span className="mono" style={{ fontSize: 13 }}>{selected}</span></h2>
            </div>
            <div className="card-body">
              {!detail ? (
                <div className="loading" style={{ padding: 40 }}>Loading evidence…</div>
              ) : (
                <>
                  <div className="narr">{detail.narration?.text}</div>
                  <div className="meta-line">
                    Narration source <b>{detail.narration?.source}</b> · {detail.narration?.validation}
                  </div>

                  <div style={{ marginTop: 14 }}>
                    {graph && <EvidenceGraph nodes={graph.nodes} edges={graph.edges} />}
                  </div>

                  <dl className="kv" style={{ marginTop: 14 }}>
                    <dt>Decision</dt>
                    <dd>
                      <span className={`pill ${detail.decision?.action}`}>
                        {detail.decision?.action?.replace(/_/g, " ")}
                      </span>
                      {detail.decision?.requires_human && (
                        <span className="chip" style={{ marginLeft: 6 }}>human confirmation</span>
                      )}
                    </dd>
                    <dt>Effect</dt><dd>{detail.action_effect?.effect}</dd>
                    <dt>Reversal</dt><dd>{detail.action_effect?.reversal}</dd>
                    <dt>Evidence</dt>
                    <dd><b>{detail.evidence.sufficiency}</b> — {detail.evidence.sufficiency_reason}</dd>
                    <dt>Rationale</dt><dd>{detail.decision?.rationale}</dd>
                  </dl>

                  <div className="eyebrow" style={{ marginTop: 16 }}>Contributing factors</div>
                  <ul className="plain">
                    {detail.evidence.contributing_factors.map((f: any) => (
                      <li key={f.feature}>
                        · {f.statement}{" "}
                        <span className="dim">
                          {f.population_median > 0
                            ? `— typical account ${f.population_median}${
                                f.lift ? `, ${f.lift}× that` : ""}`
                            : "— typical account: none"}
                        </span>
                      </li>
                    ))}
                  </ul>

                  <div className="eyebrow" style={{ marginTop: 16 }}>Audit trail</div>
                  <ul className="plain audit">
                    {detail.ledger.map((e: any) => (
                      <li key={e.index}>#{e.index} {e.event_type} · {e.entry_hash}…</li>
                    ))}
                  </ul>

                  <div style={{ marginTop: 16 }}>
                    <button className="btn primary" onClick={() => review("confirm")}>
                      Confirm abuse
                    </button>
                    <button className="btn" onClick={() => review("clear")}>Clear account</button>
                    <button className="btn" onClick={() => review("escalate")}>Escalate</button>
                    {flash && <div className="flash">{flash}</div>}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {studies?.available && (
          <>
            <div className="section eyebrow">Does it hold up?</div>
            <div className="grid split">
              <SeedVariance study={studies.seed_variance} />
              <Ablation study={studies.ablation} />
            </div>
            <div className="grid split section">
              <Prevalence study={studies.prevalence_sensitivity} />
              <Fairness study={studies.fairness} />
            </div>
          </>
        )}

        <div className="section eyebrow">Operating point</div>
        <div className="grid split">
          <div className="card">
            <div className="card-head">
              <h2>Choosing the threshold in rupees</h2>
              <p className="note">
                Not by F1. Each point prices catching an abuser (₹5,920 recovered) against
                restricting a real customer (₹2,400 in forgone lifetime value and support). Both
                are declared assumptions, not measurements.
              </p>
            </div>
            <div className="card-body">
              <CostCurve curve={evaluation.cost_curve} optimal={m.cost_optimal_threshold} />
            </div>
          </div>
          <div className="card">
            <div className="card-head">
              <h2>Precision–recall, held-out fold</h2>
              <p className="note">
                {overview.split.n_test.toLocaleString()} accounts at{" "}
                {pct(overview.split.test_prevalence, 2)} prevalence. Average precision is the
                honest headline here; ROC AUC flatters every classifier at this imbalance.
              </p>
            </div>
            <div className="card-body">
              <PrCurve curve={evaluation.pr_curve} />
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
