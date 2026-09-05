"""Command line entry point: `ringsentinel <command>`.

Every reported number in this repository is reproducible with:

    ringsentinel generate      # write the synthetic population
    ringsentinel evaluate      # replay backtest, metrics, cost curve
    ringsentinel serve         # API for the dashboard
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

import pandas as pd

from .config import ARTIFACTS_DIR, COSTS, SimulationConfig
from .evaluation.replay import run_replay
from .evaluation.studies import (
    ablation,
    fairness_by_cohort,
    prevalence_sensitivity,
    seed_variance,
)
from .simulator.generate import generate

DATASET_DIR = ARTIFACTS_DIR / "dataset"
EVAL_DIR = ARTIFACTS_DIR / "evaluation"


def _write_dataset(dataset, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    dataset.accounts.to_csv(out / "accounts.csv", index=False)
    dataset.orders.to_csv(out / "orders.csv", index=False)
    dataset.claims.to_csv(out / "claims.csv", index=False)
    (out / "meta.json").write_text(json.dumps(dataset.meta, indent=2))


def cmd_generate(args: argparse.Namespace) -> int:
    cfg = SimulationConfig(seed=args.seed)
    dataset = generate(cfg)
    _write_dataset(dataset, DATASET_DIR)
    print(dataset.summary())
    print(f"\nwritten to {DATASET_DIR}")
    return 0


def _summarise(report: dict) -> str:
    m, r = report["model"], report["rules_baseline"]
    lines = [
        "=" * 78,
        "RINGSENTINEL - REPLAY BACKTEST",
        "=" * 78,
        f"Split           : train <= day {report['split']['train_cutoff_day']}, "
        f"score at day {report['split']['score_day']}",
        f"Train / test    : {report['split']['n_train']:,} / {report['split']['n_test']:,} "
        f"accounts (test prevalence {report['split']['test_prevalence']:.2%})",
        "",
        f"{'':22}{'MODEL':>12}{'RULES':>12}",
        f"{'average precision':22}{m['average_precision']:>12.4f}{r['average_precision']:>12.4f}",
        f"{'precision':22}{m['at_cost_optimal']['precision']:>12.4f}"
        f"{r['at_cost_optimal']['precision']:>12.4f}",
        f"{'recall':22}{m['at_cost_optimal']['recall']:>12.4f}"
        f"{r['at_cost_optimal']['recall']:>12.4f}",
        f"{'F1':22}{m['at_cost_optimal']['f1']:>12.4f}{r['at_cost_optimal']['f1']:>12.4f}",
        f"{'false positives':22}{m['at_cost_optimal']['fp']:>12,}"
        f"{r['at_cost_optimal']['fp']:>12,}",
        f"{'net benefit (INR)':22}{m['net_benefit_inr']:>12,.0f}{r['net_benefit_inr']:>12,.0f}",
        "",
        f"Cost-optimal threshold : {m['cost_optimal_threshold']:.3f}",
        f"Abuse exposure caught  : INR {m['exposure_caught_inr']:,.0f} of "
        f"INR {m['abuse_exposure_inr']:,.0f} ({m['exposure_recall']:.1%})",
        f"Legit value disrupted  : INR {m['legit_value_disrupted_inr']:,.0f}",
        "",
        "RECALL BY ADVERSARY EVASION LEVEL",
        "-" * 78,
    ]
    model_lv = {d["evasion_level"]: d for d in report["recall_by_evasion_level"]}
    rules_lv = {d["evasion_level"]: d for d in report["rules_recall_by_evasion_level"]}
    lines.append(f"{'level':>7}{'ring accts':>12}{'model':>10}{'rules':>10}   {'delta':>8}")
    for lv in sorted(model_lv):
        mm = model_lv[lv]
        rr = rules_lv.get(lv, {"recall": 0.0})
        delta = mm["recall"] - rr["recall"]
        lines.append(
            f"{lv:>7}{mm['ring_accounts']:>12}{mm['recall']:>10.3f}"
            f"{rr['recall']:>10.3f}   {delta:>+8.3f}"
        )

    bp = report["banded_policy"]
    lines += [
        "",
        "SHIPPED POLICY (three bands, human in the loop)",
        "-" * 78,
        f"auto-actioned      : {bp['auto_actioned']:,} accounts "
        f"(precision {bp['auto_precision']:.3f})",
        f"queued for review  : {bp['queued_for_review']:,} accounts "
        f"(cost INR {bp['review_cost_inr']:,.0f})",
        f"missed entirely    : {bp['missed']:,} accounts",
        f"recall incl. review: {bp['recall_including_review']:.3f}",
        f"net benefit        : INR {bp['net_benefit_inr']:,.0f}",
        "",
        "Cost assumptions (see docs/MODEL_CARD.md; all are assumptions, not measurements):",
        f"  true positive recovery  INR {COSTS.true_positive_recovery_inr:,.0f}",
        f"  false positive cost     INR {COSTS.false_positive_cost_inr:,.0f}",
        f"  manual review           INR {COSTS.manual_review_cost_inr:,.0f}",
        "=" * 78,
    ]
    return "\n".join(lines)


def cmd_evaluate(args: argparse.Namespace) -> int:
    if args.from_disk and (DATASET_DIR / "accounts.csv").exists():
        from .simulator.generate import Dataset

        dataset = Dataset(
            accounts=pd.read_csv(DATASET_DIR / "accounts.csv"),
            orders=pd.read_csv(DATASET_DIR / "orders.csv"),
            claims=pd.read_csv(DATASET_DIR / "claims.csv"),
            meta=json.loads((DATASET_DIR / "meta.json").read_text()),
        )
    else:
        dataset = generate(SimulationConfig(seed=args.seed))

    result = run_replay(dataset, args.train_cutoff_day, args.score_day)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "report.json").write_text(json.dumps(result.report, indent=2, default=str))
    result.model.save(EVAL_DIR / "model.pkl")

    summary = _summarise(result.report)
    (EVAL_DIR / "summary.txt").write_text(summary)
    print(summary)
    print(f"\nreport  -> {EVAL_DIR / 'report.json'}")
    print(f"model   -> {EVAL_DIR / 'model.pkl'}")
    return 0


def cmd_study(args: argparse.Namespace) -> int:
    """Robustness studies: seed variance, ablation, prevalence, fairness."""
    out: dict = {}
    seeds = [SimulationConfig.seed + i for i in range(args.n_seeds)]

    print("=" * 78)
    print("STUDY 1/4  seed variance")
    print("-" * 78)
    out["seed_variance"] = seed_variance(seeds, args.train_cutoff_day, args.score_day)

    print("\n" + "=" * 78)
    print("STUDY 2/4  feature-family ablation")
    print("-" * 78)
    out["ablation"] = ablation(SimulationConfig.seed, args.train_cutoff_day, args.score_day)

    print("\n" + "=" * 78)
    print("STUDY 3/4  prevalence sensitivity   4/4  fairness by cohort")
    print("-" * 78)
    dataset = generate(SimulationConfig(seed=SimulationConfig.seed))
    result = run_replay(
        dataset, args.train_cutoff_day, args.score_day, verbose=False, skip_importance=True
    )
    out["prevalence_sensitivity"] = prevalence_sensitivity(result)
    out["fairness"] = fairness_by_cohort(result, dataset)

    for row in out["prevalence_sensitivity"]["results"]:
        print(
            f"  prevalence {row['achieved_prevalence']:.4f}: "
            f"precision {row['precision_mean']:.3f} "
            f"[{row['precision_p2_5']:.3f}, {row['precision_p97_5']:.3f}]  "
            f"recall {row['recall_mean']:.3f}"
        )
    print()
    for row in out["fairness"]["by_cohort"]:
        print(
            f"  {row['cohort']:10} n={row['legitimate_accounts']:5d}  "
            f"restricted={row['restricted']:3d} ({row['restriction_rate']:.4%})  "
            f"disparate impact vs solo = {row['disparate_impact_vs_solo']}"
        )

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    path = EVAL_DIR / "studies.json"
    path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwritten -> {path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("ringsentinel.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Studies take minutes; block-buffered stdout hides all progress when the
    # output is piped to a file or a log.
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(prog="ringsentinel", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write the synthetic population to artifacts/")
    g.add_argument("--seed", type=int, default=SimulationConfig.seed)
    g.set_defaults(func=cmd_generate)

    e = sub.add_parser("evaluate", help="run the replay backtest and write metrics")
    e.add_argument("--train-cutoff-day", type=int, default=55)
    e.add_argument("--score-day", type=int, default=120)
    e.add_argument("--seed", type=int, default=SimulationConfig.seed)
    e.add_argument("--from-disk", action="store_true", help="reuse artifacts/dataset")
    e.set_defaults(func=cmd_evaluate)

    st = sub.add_parser(
        "study", help="robustness studies (variance, ablation, prevalence, fairness)"
    )
    st.add_argument("--n-seeds", type=int, default=7)
    st.add_argument("--train-cutoff-day", type=int, default=55)
    st.add_argument("--score-day", type=int, default=120)
    st.set_defaults(func=cmd_study)

    s = sub.add_parser("serve", help="run the API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
