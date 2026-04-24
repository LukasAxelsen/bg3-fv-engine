"""End-to-end regression test for the P14 ``adv_dc11`` close-the-loop tutorial.

This test bypasses the actual game by simulating the deterministic LCG that
the bridge bakes into ``valor_p14.lua`` directly in Python, writing a JSONL
log that has the *same shape* as what ``execute.lua`` would emit, then
running the analyser.  The contract under test is:

  bridge generator output  ⇄  oracle JSONL schema  ⇄  analyser pass-rate logic

If any of the three drift, this test fails — protecting the README's
in-game self-verification tutorial from silently breaking again.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine_bridge.probability_scenarios import (
    P14_ADV_DC11,
    PROBABILITY_LOG_SCHEMA_VERSION,
    _simulate_log_python,
    analyze_probability_log,
    compile_probability_lua,
    get_scenario,
)


class TestRegistry:
    def test_p14_registered(self) -> None:
        sc = get_scenario("p14_adv_dc11")
        assert sc is P14_ADV_DC11
        assert sc.theoretical == 0.75
        assert sc.lean_theorem.endswith(":adv_dc11")


class TestCompileProbabilityLua:
    def test_emits_trial_loop(self, tmp_path: Path) -> None:
        out = tmp_path / "p14.lua"
        compile_probability_lua(P14_ADV_DC11, out, trials=1000, seed=42)
        text = out.read_text()
        assert "valor_trial" in text
        assert "for i = 1, 1000 do" in text
        assert "_state = 42" in text
        assert "Schema version: " in text
        # Only sandbox-safe APIs referenced.
        assert "Sandbox.ResetForValorTest" not in text
        assert "Sandbox.ApplyDamageRolls" not in text

    def test_rejects_zero_trials(self, tmp_path: Path) -> None:
        try:
            compile_probability_lua(P14_ADV_DC11, tmp_path / "x.lua", trials=0)
        except ValueError:
            return
        raise AssertionError("expected ValueError for trials=0")


class TestSimulatedLog:
    def test_python_simulator_matches_jsonl_schema(self, tmp_path: Path) -> None:
        log = tmp_path / "sim.jsonl"
        _simulate_log_python(P14_ADV_DC11, log, trials=10, seed=1)
        rows = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
        assert len(rows) == 10
        for r in rows:
            assert r["scenario"] == "p14_adv_dc11"
            assert r["schema_version"] == PROBABILITY_LOG_SCHEMA_VERSION
            assert isinstance(r["d1"], int) and 1 <= r["d1"] <= 20
            assert isinstance(r["d2"], int) and 1 <= r["d2"] <= 20
            assert r["hi"] == max(r["d1"], r["d2"])
            assert r["success"] == (r["hi"] >= 11)


class TestAnalyzeProbabilityLog:
    def test_aligned_with_theoretical_at_1000_trials(self, tmp_path: Path) -> None:
        log = tmp_path / "p14.jsonl"
        _simulate_log_python(P14_ADV_DC11, log, trials=1000, seed=1)
        result = analyze_probability_log(log, P14_ADV_DC11, tolerance=0.04)
        # Standard error at p=0.75, n=1000 is sqrt(0.75 * 0.25 / 1000) ≈ 0.0137.
        # Tolerance 0.04 is ~3σ, so this should virtually always agree.
        assert result.trials == 1000
        assert 0.70 <= result.empirical <= 0.80, result.summary()
        assert result.agree, result.summary()
        assert "AGREE" in result.summary()

    def test_diverges_when_log_is_biased(self, tmp_path: Path) -> None:
        # Hand-craft a 1000-trial log where every trial fails.
        log = tmp_path / "biased.jsonl"
        log.write_text(
            "\n".join(
                json.dumps(
                    {
                        "trial_index": i,
                        "scenario": "p14_adv_dc11",
                        "schema_version": PROBABILITY_LOG_SCHEMA_VERSION,
                        "d1": 1,
                        "d2": 2,
                        "hi": 2,
                        "success": False,
                    }
                )
                for i in range(1000)
            ),
            encoding="utf-8",
        )
        result = analyze_probability_log(log, P14_ADV_DC11, tolerance=0.04)
        assert result.empirical == 0.0
        assert not result.agree
        assert "DIVERGE" in result.summary()

    def test_ignores_other_scenarios_in_same_log(self, tmp_path: Path) -> None:
        # If the log file accidentally contains rows from a different scenario,
        # we should filter them out by `scenario` field.
        log = tmp_path / "mixed.jsonl"
        rows = []
        # 100 trials of P14 (always success) — empirical 1.0
        for i in range(100):
            rows.append(
                {
                    "trial_index": i,
                    "scenario": "p14_adv_dc11",
                    "schema_version": PROBABILITY_LOG_SCHEMA_VERSION,
                    "d1": 20,
                    "d2": 20,
                    "hi": 20,
                    "success": True,
                }
            )
        # Plus 1000 unrelated rows — must be ignored.
        for i in range(1000):
            rows.append({"scenario": "noise", "success": False, "trial_index": i})
        log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        result = analyze_probability_log(log, P14_ADV_DC11, tolerance=0.04)
        assert result.trials == 100
        assert result.successes == 100
        assert result.empirical == 1.0
        # 1.0 vs 0.75 = 0.25 deviation > 0.04 tolerance.
        assert not result.agree

    def test_expected_override(self, tmp_path: Path) -> None:
        log = tmp_path / "p14.jsonl"
        _simulate_log_python(P14_ADV_DC11, log, trials=400, seed=7)
        # Force the analyser to compare against an absurd expected probability;
        # the agree decision should flip.
        bad_expect = analyze_probability_log(
            log, P14_ADV_DC11, tolerance=0.04, expected_override=0.0
        )
        assert not bad_expect.agree
        # And with the real expected it should still agree (large enough N).
        good = analyze_probability_log(log, P14_ADV_DC11, tolerance=0.05)
        assert good.agree, good.summary()
