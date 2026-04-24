"""
Probability scenarios — bridge entries that compile to N-trial Lua dice harnesses
and analyse the resulting JSONL via empirical pass-rate vs. the Lean-proven
theoretical probability.

This module powers the README's in-game self-verification tutorial.  Currently
registered:

* ``p14_adv_dc11`` — the headline P14 claim.  Lean theorem ``adv_dc11`` proves
  ``probAdvantage400 11 = 300`` (i.e. exactly 75 %) for "succeed-on-≥-11 with
  advantage on a d20 check."  The Lua harness rolls two d20s per trial, takes
  the maximum, and counts ≥ 11 as success.  The analyser checks
  ``|empirical_rate − 0.75| ≤ tolerance``.

Adding a new probability scenario only requires registering a
``ProbabilityScenario`` instance: declare the name, the theoretical
probability (with provenance to the Lean theorem), the per-trial Lua snippet,
and the per-line success extractor.  The CLI gives the same UX for every
scenario.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

#: JSONL schema version used by probability scenario logs (independent of the
#: counterexample-replay schema in ``lua_generator.py``).
PROBABILITY_LOG_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProbabilityScenario:
    """A probability claim that the bridge can replay statistically.

    Attributes:
        name: Stable identifier (used on the CLI).
        theoretical: The probability proved by Lean.
        lean_theorem: Citation for the theoretical value (file:theorem).
        description: Human-readable claim.
        trial_lua: Lua snippet that, when executed, defines a Lua function
            ``valor_trial(rng) -> table`` returning a record at least
            containing ``success`` (boolean) and any extra diagnostics.
            ``rng`` is a pre-seeded Lua RNG conforming to the standard
            ``math.random``-style interface.
        success_extractor: Given one parsed JSONL log row, returns ``True``
            iff that trial counted as a success.
    """

    name: str
    theoretical: float
    lean_theorem: str
    description: str
    trial_lua: str
    success_extractor: Callable[[Mapping[str, Any]], bool]


def _adv_dc11_extractor(row: Mapping[str, Any]) -> bool:
    return bool(row.get("success", False))


P14_ADV_DC11 = ProbabilityScenario(
    name="p14_adv_dc11",
    theoretical=0.75,
    lean_theorem="Scenarios/P14_AdvantageAlgebra.lean:adv_dc11",
    description=(
        "P(success | DC=11, advantage on d20) = 300/400 = 0.75 "
        "(probAdvantage400 11 = 300)."
    ),
    trial_lua=(
        "function valor_trial(rng)\n"
        "  local d1 = rng(1, 20)\n"
        "  local d2 = rng(1, 20)\n"
        "  local hi = d1 > d2 and d1 or d2\n"
        "  return { d1 = d1, d2 = d2, hi = hi, success = (hi >= 11) }\n"
        "end\n"
    ),
    success_extractor=_adv_dc11_extractor,
)


_REGISTRY: dict[str, ProbabilityScenario] = {
    P14_ADV_DC11.name: P14_ADV_DC11,
}


def get_scenario(name: str) -> ProbabilityScenario:
    """Look up a scenario by name; raises ``KeyError`` if missing."""
    if name not in _REGISTRY:
        raise KeyError(
            f"Unknown probability scenario {name!r}. "
            f"Known: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def all_scenarios() -> dict[str, ProbabilityScenario]:
    """Expose the registered scenarios (read-only copy)."""
    return dict(_REGISTRY)


# ── Lua generation ──────────────────────────────────────────────────────────


def compile_probability_lua(
    scenario: ProbabilityScenario,
    output_path: Path,
    *,
    trials: int,
    seed: int = 1,
) -> Path:
    """
    Write a Lua script that performs ``trials`` trials of ``scenario`` and
    appends one JSONL line per trial under ``VALOR_CONFIG.logs_dir``.

    The script returns no ``actions`` table, so ``main.lua`` will execute the
    body once (which writes all trials inline) and not dispatch through
    ``VALOR.Execute``.
    """
    if trials <= 0:
        raise ValueError(f"trials must be positive (got {trials})")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log_filename = f"valor_prob_{scenario.name}.jsonl"
    body_lines = [
        "-- VALOR generated probability scenario",
        f"-- Scenario: {scenario.name}",
        f"-- Lean theorem: {scenario.lean_theorem}",
        f"-- Theoretical: {scenario.theoretical}",
        f"-- Trials: {trials} | Seed: {seed}",
        f"-- Schema version: {PROBABILITY_LOG_SCHEMA_VERSION}",
        "",
        "-- Deterministic local RNG so different machines reproduce the same sequence.",
        "-- Park-Miller / minimal-standard LCG; sufficient for d20 sampling.",
        f"local _state = {seed}",
        "local function rng(lo, hi)",
        "  _state = (_state * 48271) % 2147483647",
        "  return lo + (_state % (hi - lo + 1))",
        "end",
        "",
        scenario.trial_lua,
        "",
        "local function append_log(line)",
        '  local root = (VALOR_CONFIG and VALOR_CONFIG.logs_dir) or "VALOR_Logs"',
        f'  local path = root .. "/{log_filename}"',
        "  local prev = (Ext and Ext.IO and Ext.IO.LoadFile and Ext.IO.LoadFile(path)) or \"\"",
        "  if Ext and Ext.IO and Ext.IO.SaveFile then",
        "    Ext.IO.SaveFile(path, prev .. line .. \"\\n\")",
        "  end",
        "end",
        "",
        f"for i = 1, {trials} do",
        "  local result = valor_trial(rng)",
        "  result.trial_index = i - 1",
        f'  result.scenario = "{scenario.name}"',
        f"  result.schema_version = {PROBABILITY_LOG_SCHEMA_VERSION}",
        "  if Ext and Ext.Json and Ext.Json.Stringify then",
        "    append_log(Ext.Json.Stringify(result))",
        "  end",
        "end",
        "",
        "if VALOR and VALOR.Log then",
        f'  VALOR.Log("INFO", "{scenario.name}: completed {trials} trials")',
        "end",
        "",
    ]
    output_path.write_text("\n".join(body_lines), encoding="utf-8")
    logger.info(
        "Wrote probability replay script: %s (scenario=%s, trials=%d)",
        output_path,
        scenario.name,
        trials,
    )
    return output_path


# ── Analysis ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProbabilityResult:
    """Outcome of comparing an empirical probability log to the theoretical value."""

    scenario: str
    trials: int
    successes: int
    empirical: float
    theoretical: float
    tolerance: float
    deviation: float
    agree: bool

    def summary(self) -> str:
        verdict = "AGREE" if self.agree else "DIVERGE"
        return (
            f"{verdict}: scenario={self.scenario} trials={self.trials} "
            f"observed={self.empirical:.4f} ± {self._stderr():.4f} "
            f"theoretical={self.theoretical:.4f} "
            f"|delta|={self.deviation:.4f} tolerance={self.tolerance:.4f}"
        )

    def _stderr(self) -> float:
        if self.trials <= 0:
            return float("nan")
        p = self.empirical
        return (p * (1 - p) / self.trials) ** 0.5


def _iter_log_rows(log_path: Path, scenario_name: str | None) -> list[dict[str, Any]]:
    raw = log_path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning("Skipping non-JSON log line %d in %s: %s", line_no, log_path, e)
            continue
        if not isinstance(row, Mapping):
            continue
        if scenario_name is not None:
            if "scenario" in row and row["scenario"] != scenario_name:
                continue
        rows.append(dict(row))
    return rows


def analyze_probability_log(
    log_path: Path,
    scenario: ProbabilityScenario,
    *,
    tolerance: float = 0.04,
    expected_override: float | None = None,
) -> ProbabilityResult:
    """
    Read every JSONL trial in ``log_path``, compute the empirical pass rate,
    and decide whether it is within ``tolerance`` of the theoretical value
    (or ``expected_override`` if provided — used for sanity-check tests).
    """
    rows = _iter_log_rows(log_path, scenario.name)
    successes = sum(1 for r in rows if scenario.success_extractor(r))
    trials = len(rows)
    empirical = (successes / trials) if trials > 0 else 0.0
    expected = expected_override if expected_override is not None else scenario.theoretical
    deviation = abs(empirical - expected)
    return ProbabilityResult(
        scenario=scenario.name,
        trials=trials,
        successes=successes,
        empirical=empirical,
        theoretical=expected,
        tolerance=tolerance,
        deviation=deviation,
        agree=deviation <= tolerance,
    )


# ── Test-only helper ───────────────────────────────────────────────────────


def _simulate_log_python(
    scenario: ProbabilityScenario,
    output_path: Path,
    *,
    trials: int,
    seed: int = 1,
) -> Path:
    """
    Generate a synthetic JSONL log by running the LCG defined in
    ``compile_probability_lua`` directly in Python — used by regression tests
    to exercise the analyser without launching the game.

    Currently specialised for ``p14_adv_dc11``-style scenarios that only need
    a uniform integer in [1, 20].  Adding new scenarios that use
    ``valor_trial`` differently requires either a tiny Lua interpreter (out of
    scope) or an additional success-extracting Python shim per scenario.
    """
    if scenario.name != P14_ADV_DC11.name:  # pragma: no cover - guarded for clarity
        raise NotImplementedError(
            "_simulate_log_python currently only supports p14_adv_dc11"
        )
    state = seed
    lines: list[str] = []
    for i in range(trials):
        # Replicate the Lua LCG step for both d20s.
        state = (state * 48271) % 2147483647
        d1 = 1 + (state % 20)
        state = (state * 48271) % 2147483647
        d2 = 1 + (state % 20)
        hi = max(d1, d2)
        record = {
            "trial_index": i,
            "scenario": scenario.name,
            "schema_version": PROBABILITY_LOG_SCHEMA_VERSION,
            "d1": d1,
            "d2": d2,
            "hi": hi,
            "success": hi >= 11,
        }
        lines.append(json.dumps(record))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
