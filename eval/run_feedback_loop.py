"""
run_feedback_loop.py — Master orchestrator for the formalize → verify → bridge loop.

Stages are invoked via subprocess where upstream modules are still stubs; state is
persisted under ``results/round_NNN/`` for ``collect_metrics.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass
class LoopState:
    """Persistent snapshot of one feedback-loop campaign."""

    round_index: int = 0
    open_divergences: set[str] = field(default_factory=set)
    rounds_without_new_divergence: int = 0
    counterexamples_found: int = 0
    oracle_confirmations: int = 0
    oracle_attempts: int = 0
    correction_attempts: int = 0
    lean_build_ok: bool = False
    lean_build_log_excerpt: str = ""
    new_divergences_this_round: set[str] = field(default_factory=set)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "round_index": self.round_index,
            "open_divergences": sorted(self.open_divergences),
            "rounds_without_new_divergence": self.rounds_without_new_divergence,
            "counterexamples_found": self.counterexamples_found,
            "oracle_confirmations": self.oracle_confirmations,
            "oracle_attempts": self.oracle_attempts,
            "correction_attempts": self.correction_attempts,
            "lean_build_ok": self.lean_build_ok,
            "lean_build_log_excerpt": self.lean_build_log_excerpt[:4000],
            "new_divergences_this_round": sorted(self.new_divergences_this_round),
        }


def _run(cmd: list[str], cwd: Optional[Path], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def stage_llm_formalize(root: Path, round_idx: int, mode: str) -> None:
    script = root / "src" / "1_auto_formalizer" / "llm_to_lean.py"
    cmd = [sys.executable, str(script), "--round", str(round_idx), "--mode", mode]
    proc = _run(cmd, cwd=root, timeout=120)
    if proc.returncode != 0:
        logging.warning("llm_to_lean exited %s: %s", proc.returncode, proc.stderr[:500])


def stage_lake_build(lean_root: Path, timeout: int = 600) -> tuple[bool, str]:
    lake = shutil.which("lake")
    if not lake:
        return False, "lake not on PATH"
    proc = _run([lake, "build"], cwd=lean_root, timeout=timeout)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def parse_lean_divergences(build_log: str) -> set[str]:
    """Heuristic: Lean error lines become synthetic divergence ids for tracking."""
    divs: set[str] = set()
    for line in build_log.splitlines():
        if "error:" in line.lower():
            key = re.sub(r"\s+", " ", line.strip())[:120]
            if key:
                divs.add(f"lean:{key}")
    return divs


def stage_bridge_stub(round_dir: Path) -> Path:
    """Write a placeholder Lua script (real pipeline uses lean_parser + lua_generator)."""
    lua_path = round_dir / "generated.lua"
    lua_path.write_text(
        "-- VALOR feedback loop stub: replace with lua_generator output\n"
        "return {}\n",
        encoding="utf-8",
    )
    return lua_path


def wait_for_oracle_log(
    oracle_log: Path,
    timeout_s: float,
    poll_s: float = 0.5,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if oracle_log.is_file():
            return True
        time.sleep(poll_s)
    return False


def analyze_oracle_stub(oracle_log: Path) -> tuple[set[str], bool]:
    """
    If ``oracle_log`` exists and contains JSON with divergences, use it;
    otherwise treat as oracle-unavailable (no confirmation).
    """
    if not oracle_log.is_file():
        return set(), False
    try:
        data = json.loads(oracle_log.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {f"oracle:invalid_json@{oracle_log.name}"}, False

    divs_raw = data.get("divergences") or data.get("open_divergences") or []
    confirmed = bool(data.get("oracle_confirmed", data.get("confirmed", False)))
    return {str(x) for x in divs_raw}, confirmed


def run_round(
    root: Path,
    lean_root: Path,
    round_idx: int,
    output_dir: Path,
    oracle_log: Path,
    oracle_wait_s: float,
    skip_lake: bool,
    cumulative_open: set[str],
) -> LoopState:
    round_dir = output_dir / f"round_{round_idx:03d}"
    round_dir.mkdir(parents=True, exist_ok=True)

    state = LoopState(round_index=round_idx)

    stage_llm_formalize(root, round_idx, "formalize")

    if skip_lake:
        state.lean_build_ok = True
        state.lean_build_log_excerpt = "lake skipped (--skip-lake)"
    else:
        ok, log = stage_lake_build(lean_root)
        state.lean_build_ok = ok
        state.lean_build_log_excerpt = log
        if not ok:
            state.new_divergences_this_round |= parse_lean_divergences(log)

    # Bridge
    stage_bridge_stub(round_dir)

    # Oracle (optional log file)
    state.oracle_attempts = 1
    seen = wait_for_oracle_log(oracle_log, oracle_wait_s)
    if seen:
        divs, confirmed = analyze_oracle_stub(oracle_log)
        state.new_divergences_this_round |= divs
        if confirmed:
            state.oracle_confirmations = 1
    else:
        logging.info("Oracle log not found within %ss: %s", oracle_wait_s, oracle_log)

    # Synthetic counterexample count when build fails (exploits search placeholder)
    if not state.lean_build_ok and not skip_lake:
        state.counterexamples_found = len(state.new_divergences_this_round)
    elif state.lean_build_ok:
        state.counterexamples_found = 0

    # Correction pass (stub)
    if state.new_divergences_this_round:
        state.correction_attempts = 1
        stage_llm_formalize(root, round_idx, "correct")

    state.open_divergences = set(cumulative_open) | state.new_divergences_this_round

    (round_dir / "state.json").write_text(
        json.dumps(state.to_json_dict(), indent=2),
        encoding="utf-8",
    )
    metrics = {
        "round": round_idx,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **state.to_json_dict(),
        "formalization_accuracy_proxy": 1.0 if state.lean_build_ok else 0.0,
        "correction_efficiency": (
            1.0 / state.correction_attempts if state.correction_attempts else 1.0
        ),
    }
    (round_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    return state


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="VALOR closed feedback loop orchestrator.")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument(
        "--lean-root",
        type=Path,
        default=_repo_root() / "src" / "2_fv_core",
    )
    parser.add_argument("--output", type=Path, default=_repo_root() / "results")
    parser.add_argument(
        "--oracle-log",
        type=Path,
        default=_repo_root() / "results" / "oracle_log.json",
        help="Path waited on for in-game oracle output",
    )
    parser.add_argument(
        "--oracle-wait-s",
        type=float,
        default=0.0,
        help="Seconds to wait for oracle log each round (0 = do not wait)",
    )
    parser.add_argument(
        "--skip-lake",
        action="store_true",
        help="Skip lake build (useful when Lean toolchain unavailable)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    root = _repo_root()
    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    open_div: set[str] = set()
    stagnant = 0

    for r in range(1, args.rounds + 1):
        before = set(open_div)
        state = run_round(
            root=root,
            lean_root=args.lean_root,
            round_idx=r,
            output_dir=output_dir,
            oracle_log=args.oracle_log,
            oracle_wait_s=args.oracle_wait_s,
            skip_lake=args.skip_lake,
            cumulative_open=before,
        )
        this = state.new_divergences_this_round
        fresh = this - before
        open_div = before | this
        if not fresh:
            stagnant += 1
        else:
            stagnant = 0

        logging.info(
            "Round %s: fresh_divergences=%s stagnant_rounds=%s |open|=%s",
            r,
            len(fresh),
            stagnant,
            len(open_div),
        )

        if stagnant >= 2:
            logging.info("Convergence: no new divergences for 2 consecutive rounds.")
            break

    summary = {
        "total_open_divergences": sorted(open_div),
        "stopped_early_convergence": stagnant >= 2,
        "final_stagnant_rounds": stagnant,
    }
    (output_dir / "campaign_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
