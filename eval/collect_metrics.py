"""
collect_metrics.py — Aggregate ``results/round_*/metrics.json`` into plots and LaTeX tables.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Optional

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rich.console import Console
from rich.table import Table


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_round_metrics(results_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in sorted(results_dir.glob("round_*/metrics.json")):
        with open(p, encoding="utf-8") as f:
            rows.append(json.load(f))
    rows.sort(key=lambda r: int(r.get("round", 0)))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "rounds": 0,
            "final_formalization_accuracy": 0.0,
            "total_counterexamples": 0,
            "oracle_confirmation_rate": 0.0,
            "mean_correction_efficiency": 0.0,
        }

    last = rows[-1]
    total_ce = sum(int(r.get("counterexamples_found", 0) or 0) for r in rows)
    o_conf = sum(int(r.get("oracle_confirmations", 0) or 0) for r in rows)
    o_att = sum(int(r.get("oracle_attempts", 0) or 0) for r in rows)
    oracle_rate = o_conf / o_att if o_att else 0.0
    ceff = [
        float(r.get("correction_efficiency", 0) or 0)
        for r in rows
        if int(r.get("correction_attempts") or 0) > 0
    ]
    mean_ceff = sum(ceff) / len(ceff) if ceff else 1.0

    acc_curve = [float(r.get("formalization_accuracy_proxy", 0) or 0) for r in rows]

    return {
        "rounds": len(rows),
        "final_formalization_accuracy": float(last.get("formalization_accuracy_proxy", 0) or 0),
        "accuracy_curve": acc_curve,
        "total_counterexamples": total_ce,
        "oracle_confirmation_rate": oracle_rate,
        "mean_correction_efficiency": mean_ceff,
        "converged_rounds": sum(
            1 for r in rows if not r.get("new_divergences_this_round")
        ),
    }


def plot_convergence(rows: list[dict[str, Any]], out_path: Path) -> None:
    if not rows:
        return
    xs = [int(r["round"]) for r in rows]
    acc = [float(r.get("formalization_accuracy_proxy", 0) or 0) for r in rows]
    open_n = [len(r.get("open_divergences") or []) for r in rows]

    fig, ax1 = plt.subplots(figsize=(7, 4))
    ax1.plot(xs, acc, "o-", label="Formalization accuracy (proxy)")
    ax1.set_xlabel("Round")
    ax1.set_ylabel("Accuracy")
    ax1.set_ylim(-0.05, 1.05)

    ax2 = ax1.twinx()
    ax2.bar(xs, open_n, alpha=0.25, label="|Open divergences|")
    ax2.set_ylabel("Open divergences (count)")

    fig.suptitle("Convergence curve")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_exploit_rate(rows: list[dict[str, Any]], out_path: Path) -> None:
    if not rows:
        return
    xs = [int(r["round"]) for r in rows]
    ys = [int(r.get("counterexamples_found", 0) or 0) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(xs, ys)
    ax.set_xlabel("Round")
    ax.set_ylabel("Counterexamples (round)")
    ax.set_title("Exploit / counterexample discovery rate")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_accuracy_by_tier(
    eval_json: Optional[Path],
    out_path: Path,
) -> None:
    """If ``--eval-json`` points to evaluate_accuracy output, bar-plot by tier."""
    if not eval_json or not eval_json.is_file():
        return
    data = json.loads(eval_json.read_text(encoding="utf-8"))
    by_t = data.get("aggregate", {}).get("by_complexity", {})
    if not by_t:
        return
    tiers = list(by_t.keys())
    accs = [by_t[t]["exact_match_rate"] for t in tiers]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(tiers, accs)
    ax.set_ylabel("Exact match rate")
    ax.set_title("Accuracy by spell complexity tier")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def export_booktabs_summary(summary: dict[str, Any], out_path: Path) -> None:
    lines = [
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Metric & Value \\",
        r"\midrule",
        f"Rounds & {summary['rounds']} \\\\",
        f"Final formalization accuracy & {summary['final_formalization_accuracy']:.3f} \\\\",
        f"Total counterexamples & {summary['total_counterexamples']} \\\\",
        f"Oracle confirmation rate & {summary['oracle_confirmation_rate']:.3f} \\\\",
        f"Mean correction efficiency & {summary['mean_correction_efficiency']:.3f} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_llm_eval_report(path: Optional[Path]) -> Optional[dict[str, Any]]:
    """Load an ``llm_to_lean --mode eval --out-json …`` report if present."""
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fold_llm_eval_into_summary(
    summary: dict[str, Any], report: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Add the LLM accuracy fields (provider/model/micro/macro/n) to ``summary``."""
    if not report:
        return summary
    summary = {**summary}
    summary["llm_provider"] = report.get("provider", "unknown")
    summary["llm_model"] = report.get("model", "")
    summary["llm_n_entries"] = report.get("n_entries", 0)
    summary["llm_total_facts"] = report.get("total_facts", 0)
    summary["llm_correct_facts"] = report.get("correct_facts", 0)
    summary["llm_micro_accuracy"] = report.get("micro_accuracy", 0.0)
    summary["llm_macro_accuracy"] = report.get("macro_accuracy", 0.0)
    return summary


def export_llm_accuracy_table(report: Optional[dict[str, Any]], out_path: Path) -> None:
    """LaTeX booktabs table with one row per gold entry's per-entry accuracy."""
    if not report:
        return
    rows = report.get("entries", [])
    if not rows:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        r"\begin{tabular}{llrrr}",
        r"\toprule",
        r"Spell & ID & \#facts & Correct & Accuracy \\",
        r"\midrule",
    ]
    for r in rows:
        total = r.get("total_facts", 0)
        correct = r.get("correct_facts", 0)
        acc = (correct / total) if total else 1.0
        lines.append(
            f"{r.get('spell_name', '?')} & {r.get('entry_id', '?')} & {total} & {correct} & {acc:.3f} \\\\"
        )
    lines.extend(
        [
            r"\midrule",
            (
                f"\\textbf{{Total}} & & {report.get('total_facts', 0)} & "
                f"{report.get('correct_facts', 0)} & "
                f"{report.get('micro_accuracy', 0.0):.3f} \\\\"
            ),
            r"\bottomrule",
            r"\end{tabular}",
        ]
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Build paper figures from feedback-loop results.")
    p.add_argument("--results", type=Path, default=_repo_root() / "results")
    p.add_argument("--output", type=Path, default=_repo_root() / "docs")
    p.add_argument(
        "--eval-json",
        type=Path,
        default=None,
        help="Optional evaluate_accuracy JSON for complexity-tier figure",
    )
    p.add_argument(
        "--llm-eval-json",
        type=Path,
        default=None,
        help=(
            "Optional report from `llm_to_lean --mode eval --out-json …`. "
            "When present, accuracy fields are folded into metrics_summary.json "
            "and a LaTeX accuracy table is exported."
        ),
    )
    args = p.parse_args(argv)

    rows = load_round_metrics(args.results)
    summary = summarize(rows)
    llm_report = load_llm_eval_report(args.llm_eval_json)
    summary = fold_llm_eval_into_summary(summary, llm_report)

    out = args.output
    plot_convergence(rows, out / "fig_convergence.png")
    plot_exploit_rate(rows, out / "fig_exploit_rate.png")
    plot_accuracy_by_tier(args.eval_json, out / "fig_accuracy_by_tier.png")

    export_booktabs_summary(summary, out / "table_metrics.tex")
    export_llm_accuracy_table(llm_report, out / "table_llm_accuracy.tex")

    meta = {**summary}
    (out / "metrics_summary.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    console = Console()
    t = Table(title="Campaign metrics")
    t.add_column("Field")
    t.add_column("Value")
    for k, v in summary.items():
        if k == "accuracy_curve":
            continue
        if isinstance(v, float) and not math.isfinite(v):
            continue
        t.add_row(k, str(v))
    console.print(t)
    console.print(f"Wrote figures and tables under {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
