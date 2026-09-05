"use client";
import { AblationBars, PrevalenceCurve } from "./Charts";

const pct = (n: number, d = 1) => `${(n * 100).toFixed(d)}%`;

/** Seed variance: is the headline real, or one lucky population? */
export function SeedVariance({ study }: { study: any }) {
  const s = study.summary;
  const n = study.seeds.length;
  const row = (label: string, key: string, fmt: (v: number) => string) => (
    <tr key={key}>
      <td>{label}</td>
      <td className="num">{fmt(s[key].mean)}</td>
      <td className="num" style={{ color: "var(--ink-4)" }}>± {fmt(s[key].std)}</td>
      <td className="num" style={{ color: "var(--ink-4)" }}>
        {fmt(s[key].min)} – {fmt(s[key].max)}
      </td>
    </tr>
  );
  return (
    <div className="card">
      <div className="card-head">
        <h2>Is the headline real, or one lucky seed?</h2>
        <p className="note">
          The whole pipeline re-run on <b>{n} independently generated populations</b>. The seed
          committed in <code>artifacts/</code> scores 0.978 — near the top of this range. The
          honest headline is the mean.
        </p>
      </div>
      <div className="card-body">
        <table>
          <thead>
            <tr>
              <th>Metric</th><th className="num">Mean</th>
              <th className="num">SD</th><th className="num">Range</th>
            </tr>
          </thead>
          <tbody>
            {row("Model avg. precision", "model_ap", (v) => v.toFixed(3))}
            {row("Rule baseline avg. precision", "rules_ap", (v) => v.toFixed(3))}
            {row("Precision", "precision", (v) => v.toFixed(3))}
            {row("Recall", "recall", (v) => v.toFixed(3))}
            {row("False positives", "false_positives", (v) => v.toFixed(0))}
            {row("Recall · L0–L6", "recall_L0_L6", (v) => v.toFixed(3))}
            {row("Recall · L7–L9 (model)", "recall_L7_L9", (v) => v.toFixed(3))}
            {row("Recall · L7–L9 (rules)", "rules_recall_L7_L9", (v) => v.toFixed(3))}
          </tbody>
        </table>
        <div className="callout" style={{ marginTop: 14 }}>
          The distributions <b>do not overlap</b> where it matters: the model's worst seed on hard
          rings ({s.recall_L7_L9.min.toFixed(3)}) still beats the rule baseline's best
          ({s.rules_recall_L7_L9.max.toFixed(3)}).
        </div>
      </div>
    </div>
  );
}

/** Ablation: is the graph earning its keep? */
export function Ablation({ study }: { study: any }) {
  const rows = study.results;
  const beh = rows.find((r: any) => r.feature_set === "behavioural_only");
  const all = rows.find((r: any) => r.feature_set === "all");
  return (
    <div className="card">
      <div className="card-head">
        <h2>Is the graph earning its keep?</h2>
        <p className="note">
          Same model, trained on subsets of the feature families, scored on recall against
          sophisticated rings (L7–L9). If per-account behaviour alone got there, the entire graph
          layer would be decoration.
        </p>
      </div>
      <div className="card-body">
        <AblationBars rows={rows} />
        <div className="callout" style={{ marginTop: 12 }}>
          Behavioural features alone catch <b>{pct(beh?.recall_L7_L9 ?? 0)}</b> of sophisticated
          rings, against <b>{pct(all?.recall_L7_L9 ?? 0)}</b> with the full set. Graph features
          alone catch every naive ring but only 58% of hard ones — the graph and the
          identity-churn features solve different halves of the problem.
        </div>
      </div>
    </div>
  );
}

/** Prevalence: what happens when organised abuse is rarer than assumed? */
export function Prevalence({ study }: { study: any }) {
  const rows = study.results;
  const low = rows[0];
  const high = rows[rows.length - 1];
  return (
    <div className="card">
      <div className="card-head">
        <h2>What if abuse is rarer than we assumed?</h2>
        <p className="note">
          The benchmark runs at 5.3% prevalence, which is at the top of plausible. Model and
          threshold held fixed, the held-out fold resampled to each rate, 300 bootstraps.
        </p>
      </div>
      <div className="card-body">
        <PrevalenceCurve rows={rows} />
        <div className="callout" style={{ marginTop: 12 }}>
          Recall is invariant, as it must be. Precision is not: at{" "}
          <b>{pct(low.achieved_prevalence, 1)}</b> prevalence it falls from{" "}
          <b>{pct(high.precision_mean)}</b> to <b>{pct(low.precision_mean)}</b> — roughly one flag
          in three would be wrong. A real caveat, measured rather than hand-waved.
        </div>
      </div>
    </div>
  );
}

/** Fairness: who absorbs the false positives? */
export function Fairness({ study }: { study: any }) {
  const rows = study.by_cohort;
  const label: Record<string, string> = {
    solo: "Solo shopper",
    household: "Multi-account household",
    hub: "Hostel / PG / office address",
  };
  const max = Math.max(...rows.map((r: any) => r.review_rate), 0.001);
  return (
    <div className="card">
      <div className="card-head">
        <h2>Who gets hurt when we are wrong?</h2>
        <p className="note">
          Among <b>legitimate accounts only</b>. Accuracy says the model is right 91.5% of the
          time; it says nothing about who absorbs the rest. &ldquo;Restricted&rdquo; means a
          customer-visible action — monitoring and review-queue entries are invisible to them.
        </p>
      </div>
      <div className="card-body">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cohort</th>
                <th className="num">Accounts</th>
                <th className="num">Restricted</th>
                <th className="num">Rate</th>
                <th className="num">Queued</th>
                <th style={{ width: 120 }}>Review load</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any) => (
                <tr key={r.cohort}>
                  <td style={{ color: "var(--ink)", fontWeight: 550 }}>
                    {label[r.cohort] ?? r.cohort}
                  </td>
                  <td className="num">{r.legitimate_accounts.toLocaleString()}</td>
                  <td className="num" style={{ color: r.restricted ? "var(--bad)" : "var(--good)",
                                               fontWeight: 600 }}>
                    {r.restricted}
                  </td>
                  <td className="num">{(r.restriction_rate * 100).toFixed(3)}%</td>
                  <td className="num">{r.queued_for_review}</td>
                  <td>
                    <div className="bar-track">
                      <div className="bar-fill"
                           style={{
                             width: `${(r.review_rate / max) * 100}%`,
                             background: r.review_rate > 0 ? "var(--warn)" : "transparent",
                           }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="callout" style={{ marginTop: 14 }}>
          <b>No solo shopper is ever restricted or even queued.</b> The disparate-impact ratio
          against that reference group is not large — it is <b>undefined</b>, because the
          reference rate is exactly zero. Every wrongly restricted customer lives in a
          multi-account household; households are 22% of the legitimate population and absorb
          100% of restrictions and 92% of all flags. In India that shape means joint families,
          students in PG accommodation and shared housing — a fairness problem, not only an
          accuracy one, and invisible to anyone reporting precision alone.
        </div>
      </div>
    </div>
  );
}
