"""
evaluate_accuracy.py — Auto-formalization accuracy vs hand-annotated Lean benchmarks.

Compares gold axioms from ``dataset/manual_annotations/*.json`` against
axioms extracted from prediction Lean sources (e.g. ``Axioms/*.lean``).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.table import Table


# ── Benchmark schema ───────────────────────────────────────────────────────
# Each JSON file: id (axiom name), spell_name, complexity in
# {simple, compound, interaction}, gold_lean (full axiom block).


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_benchmarks(benchmark_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(benchmark_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["_source_file"] = str(path)
        out.append(data)
    return out


def read_prediction_lean_sources(predictions_dir: Path) -> str:
    parts: list[str] = []
    for p in sorted(predictions_dir.rglob("*.lean")):
        parts.append(p.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def _doc_start_before_axiom(src: str, axiom_pos: int) -> int:
    """If a ``/-- … -/`` block sits immediately above this axiom, return its start index."""
    before = src[:axiom_pos].rstrip()
    if not before.endswith("-/"):
        return axiom_pos
    close_idx = before.rfind("-/")
    open_idx = before.rfind("/--", 0, close_idx + 1)
    if open_idx == -1:
        return axiom_pos
    return open_idx


def extract_axiom_block(src: str, axiom_name: str) -> Optional[str]:
    """Return the doc-comment (if any) + axiom declaration for ``axiom_name``."""
    m = re.search(rf"(?m)^[ \t]*axiom\s+{re.escape(axiom_name)}\b", src)
    if not m:
        return None
    start = _doc_start_before_axiom(src, m.start())
    block = src[start:]
    # Next spell/section in BG3Rules.lean starts with a new `/--` line; otherwise next `axiom`.
    doc_heads = list(re.finditer(r"(?m)^/--", block))
    if len(doc_heads) > 1:
        block = block[: doc_heads[1].start()]
    else:
        axiom_heads = list(re.finditer(r"(?m)^[ \t]*axiom\s+\w", block))
        if len(axiom_heads) > 1:
            block = block[: axiom_heads[1].start()]
    end_m = re.search(r"(?m)^end\s+", block)
    if end_m:
        block = block[: end_m.start()]
    return block.rstrip()


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def decompose_clauses(lean_fragment: str) -> set[str]:
    """
    Clause-level bag for F1: split on implication chains and conjunctions.
    Heuristic for Lean proposition structure (preconditions / effects).
    """
    # Strip doc comment
    frag = re.sub(r"/--.*?-/", "", lean_fragment, flags=re.DOTALL)
    frag = frag.strip()
    # Remove leading 'axiom name ... :' header line roughly
    frag = re.sub(r"^axiom\s+\w+\b[\s\S]*?:", "", frag, count=1).strip()
    pieces: list[str] = []
    for segment in re.split(r"\s*(?:→|->|∧|/\\)\s*", frag):
        segment = segment.strip()
        if segment and segment not in ("by", "sorry"):
            pieces.append(normalize_ws(segment))
    if not pieces:
        pieces = [normalize_ws(frag)]
    return set(pieces)


def clause_f1(gold: str, pred: str) -> dict[str, float]:
    g, p = decompose_clauses(gold), decompose_clauses(pred)
    if not g and not p:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not g or not p:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    inter = len(g & p)
    prec = inter / len(p) if p else 0.0
    rec = inter / len(g) if g else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"precision": prec, "recall": rec, "f1": f1}


def run_lake_build(lean_root: Path, timeout: int = 600) -> tuple[bool, str]:
    lake = shutil.which("lake")
    if not lake:
        return False, "lake not found on PATH"
    proc = subprocess.run(
        [lake, "build"],
        cwd=str(lean_root),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    ok = proc.returncode == 0
    msg = (proc.stdout or "") + (proc.stderr or "")
    return ok, msg


@dataclass
class SpellEvalRow:
    benchmark_id: str
    spell_name: str
    complexity: str
    exact_match: bool
    clause_f1: float
    semantic_typecheck: bool
    prediction_found: bool
    notes: str = ""


@dataclass
class AccuracyReport:
    rows: list[SpellEvalRow] = field(default_factory=list)
    lake_build_ok: bool = False
    lake_build_message: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "lake_build_ok": self.lake_build_ok,
            "lake_build_message": self.lake_build_message[:2000],
            "per_spell": [
                {
                    "id": r.benchmark_id,
                    "spell_name": r.spell_name,
                    "complexity": r.complexity,
                    "exact_match": r.exact_match,
                    "clause_f1": r.clause_f1,
                    "semantic_typecheck": r.semantic_typecheck,
                    "prediction_found": r.prediction_found,
                    "notes": r.notes,
                }
                for r in self.rows
            ],
            "aggregate": self._aggregate(),
        }

    def _aggregate(self) -> dict[str, Any]:
        def mean(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        ex = [1.0 if r.exact_match else 0.0 for r in self.rows]
        f1s = [r.clause_f1 for r in self.rows]
        sem = [1.0 if r.semantic_typecheck else 0.0 for r in self.rows]

        by_tier: dict[str, dict[str, float]] = {}
        for tier in ("simple", "compound", "interaction"):
            sub = [r for r in self.rows if r.complexity == tier]
            if not sub:
                continue
            by_tier[tier] = {
                "n": float(len(sub)),
                "exact_match_rate": mean([1.0 if x.exact_match else 0.0 for x in sub]),
                "mean_clause_f1": mean([x.clause_f1 for x in sub]),
                "semantic_rate": mean([1.0 if x.semantic_typecheck else 0.0 for x in sub]),
            }

        return {
            "count": len(self.rows),
            "exact_match_rate": mean(ex),
            "mean_clause_f1": mean(f1s),
            "semantic_typecheck_rate": mean(sem),
            "by_complexity": by_tier,
        }


def evaluate(
    benchmarks: list[dict[str, Any]],
    prediction_src: str,
    lean_root: Optional[Path],
    run_lean: bool,
) -> AccuracyReport:
    report = AccuracyReport(rows=[])
    if run_lean and lean_root is not None:
        report.lake_build_ok, report.lake_build_message = run_lake_build(lean_root)
    elif run_lean:
        report.lake_build_message = "lean_root not set"
        report.lake_build_ok = False

    for b in benchmarks:
        bid = str(b["id"])
        spell = str(b.get("spell_name", bid))
        tier = str(b.get("complexity", "simple")).lower()
        if tier not in ("simple", "compound", "interaction"):
            tier = "simple"

        gold = str(b["gold_lean"])
        pred_block = extract_axiom_block(prediction_src, bid)
        found = pred_block is not None
        pred = pred_block or ""

        em = normalize_ws(gold) == normalize_ws(pred) if pred else False
        f1 = clause_f1(gold, pred)["f1"] if pred else 0.0

        # Semantic: project type-checks (Lean) and predicted axiom present in bundle.
        sem = bool(report.lake_build_ok and found)

        report.rows.append(
            SpellEvalRow(
                benchmark_id=bid,
                spell_name=spell,
                complexity=tier,
                exact_match=em,
                clause_f1=f1,
                semantic_typecheck=sem,
                prediction_found=found,
                notes="" if found else "missing axiom in predictions",
            )
        )

    return report


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Measure auto-formalization accuracy.")
    parser.add_argument(
        "--benchmarks",
        type=Path,
        default=_repo_root() / "dataset" / "manual_annotations",
        help="Directory of per-spell JSON benchmarks",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=_repo_root() / "src" / "2_fv_core" / "Axioms",
        help="Directory of Lean files containing predicted axioms",
    )
    parser.add_argument(
        "--lean-root",
        type=Path,
        default=_repo_root() / "src" / "2_fv_core",
        help="Lean package root for lake build (semantic metric)",
    )
    parser.add_argument(
        "--skip-lake",
        action="store_true",
        help="Do not run lake build (semantic metric will be False)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full JSON report to this path",
    )
    args = parser.parse_args(argv)

    bench_dir: Path = args.benchmarks
    if not bench_dir.is_dir():
        print(f"No benchmark directory: {bench_dir}", file=sys.stderr)
        return 1

    benchmarks = load_benchmarks(bench_dir)
    if not benchmarks:
        print(f"No *.json benchmarks under {bench_dir}", file=sys.stderr)
        return 1

    pred_dir: Path = args.predictions
    if not pred_dir.is_dir():
        print(f"No predictions directory: {pred_dir}", file=sys.stderr)
        return 1

    lean_root: Path = args.lean_root
    pred_src = read_prediction_lean_sources(pred_dir)
    report = evaluate(
        benchmarks,
        pred_src,
        lean_root if lean_root.is_dir() else None,
        run_lean=not args.skip_lake,
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report.to_json_dict(), indent=2), encoding="utf-8")

    console = Console()
    agg = report.to_json_dict()["aggregate"]
    table = Table(title="Auto-formalization accuracy")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Benchmarks", str(int(agg["count"])))
    table.add_row("Exact match rate", f"{agg['exact_match_rate']:.3f}")
    table.add_row("Mean clause F1", f"{agg['mean_clause_f1']:.3f}")
    table.add_row("Semantic (lake OK ∧ axiom present)", f"{agg['semantic_typecheck_rate']:.3f}")
    table.add_row("lake build", "ok" if report.lake_build_ok else "failed / skipped")
    console.print(table)

    tier_table = Table(title="Stratified by complexity")
    tier_table.add_column("Tier")
    tier_table.add_column("n")
    tier_table.add_column("EM")
    tier_table.add_column("F1")
    tier_table.add_column("Semantic")
    for tier, stats in agg.get("by_complexity", {}).items():
        tier_table.add_row(
            tier,
            str(int(stats["n"])),
            f"{stats['exact_match_rate']:.3f}",
            f"{stats['mean_clause_f1']:.3f}",
            f"{stats['semantic_rate']:.3f}",
        )
    if agg.get("by_complexity"):
        console.print(tier_table)

    detail = Table(title="Per spell")
    detail.add_column("id")
    detail.add_column("tier")
    detail.add_column("EM")
    detail.add_column("F1")
    detail.add_column("sem")
    detail.add_column("found")
    for r in report.rows:
        detail.add_row(
            r.benchmark_id,
            r.complexity,
            "Y" if r.exact_match else "N",
            f"{r.clause_f1:.2f}",
            "Y" if r.semantic_typecheck else "N",
            "Y" if r.prediction_found else "N",
        )
    console.print(detail)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
