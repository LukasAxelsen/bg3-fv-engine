"""Tests for src/3_engine_bridge — lean_parser, lua_generator, log_analyzer."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from engine_bridge.lean_parser import (
    CounterexampleFound,
    CounterexamplePath,
    CounterexampleStep,
    LeanTypeError,
    ProofSucceeded,
    Timeout,
    _extract_witness_json,
    _looks_like_lean_type_error,
    _path_from_payload,
    _steps_from_payload,
)
from engine_bridge.log_analyzer import (
    DivergenceReport,
    DivergenceType,
    _event_signature,
    _normalize_log_entries,
    _slim_entities,
    analyze_log,
)
from engine_bridge.lua_generator import (
    BRIDGE_SCHEMA_VERSION,
    DEFAULT_STATUS_TRANSLATION,
    _entity_uuid,
    _slug,
    _slim_predicted_state,
    _to_lua,
    _worst_case_damage,
    compile_to_lua,
)


# ── lean_parser ──────────────────────────────────────────────────────────────


class TestExtractWitnessJson:
    def test_valid_witness(self) -> None:
        text = (
            "build ok\n"
            "VALOR_COUNTEREXAMPLE_JSON_BEGIN\n"
            '{"steps": [{"state": {"hp": 10}, "event": {"tag": "castSpell"}}]}\n'
            "VALOR_COUNTEREXAMPLE_JSON_END\n"
        )
        result = _extract_witness_json(text)
        assert result is not None
        assert "steps" in result

    def test_no_markers(self) -> None:
        assert _extract_witness_json("plain output") is None

    def test_malformed_json(self) -> None:
        text = "VALOR_COUNTEREXAMPLE_JSON_BEGIN\n{bad json\nVALOR_COUNTEREXAMPLE_JSON_END\n"
        assert _extract_witness_json(text) is None


class TestStepsFromPayload:
    def test_well_formed_steps(self) -> None:
        payload = {
            "steps": [
                {"state": {"hp": 50}, "event": {"tag": "weaponAttack"}},
                {"state": {"hp": 30}, "event": {"tag": "castSpell"}},
            ]
        }
        steps = _steps_from_payload(payload)
        assert len(steps) == 2
        assert steps[0].state["hp"] == 50

    def test_missing_steps_key(self) -> None:
        assert _steps_from_payload({}) == []

    def test_malformed_entries_skipped(self) -> None:
        payload = {"steps": ["not a dict", {"state": {"x": 1}, "event": {"y": 2}}]}
        steps = _steps_from_payload(payload)
        assert len(steps) == 1


class TestPathFromPayload:
    def test_with_axiom(self) -> None:
        payload = {
            "steps": [{"state": {"a": 1}, "event": {"b": 2}}],
            "axiom_name": "smite_double_crit",
        }
        path = _path_from_payload(payload)
        assert path is not None
        assert path.axiom_name == "smite_double_crit"
        assert len(path.steps) == 1

    def test_empty_steps_returns_none(self) -> None:
        assert _path_from_payload({"steps": []}) is None

    def test_extra_metadata_preserved(self) -> None:
        payload = {
            "steps": [{"state": {}, "event": {"tag": "x"}}],
            "axiom": "test_ax",
            "version": 3,
        }
        path = _path_from_payload(payload)
        assert path is not None
        assert path.metadata["version"] == 3


class TestLooksLikeLeanTypeError:
    def test_rc_zero_never_type_error(self) -> None:
        assert _looks_like_lean_type_error("error: type mismatch", 0) is False

    def test_type_mismatch(self) -> None:
        assert _looks_like_lean_type_error("error: type mismatch at something", 1) is True

    def test_unknown_identifier(self) -> None:
        assert _looks_like_lean_type_error("unknown identifier 'foo'", 1) is True


# ── lua_generator ────────────────────────────────────────────────────────────


class TestSlug:
    def test_basic(self) -> None:
        assert _slug("Fireball") == "fireball"

    def test_spaces_and_specials(self) -> None:
        assert _slug("Hellish Rebuke (3)") == "hellish_rebuke_3"


class TestEntityUuid:
    def test_default_lookup(self) -> None:
        uuid = _entity_uuid(0, None)
        assert uuid == "00000000-0000-4000-8000-000000000000"

    def test_override(self) -> None:
        custom = {0: "aaaa-bbbb"}
        assert _entity_uuid(0, custom) == "aaaa-bbbb"

    def test_fallback_format(self) -> None:
        uuid = _entity_uuid(99, None)
        assert uuid.endswith("000000000099")


class TestWorstCaseDamage:
    def test_single_roll(self) -> None:
        assert _worst_case_damage([{"dice": {"count": 8, "sides": 6, "bonus": 0}}]) == 48

    def test_multi_roll(self) -> None:
        rolls = [
            {"dice": {"count": 1, "sides": 8, "bonus": 5}},
            {"dice": {"count": 2, "sides": 6, "bonus": 0}},
        ]
        assert _worst_case_damage(rolls) == 13 + 12

    def test_malformed_skipped(self) -> None:
        assert _worst_case_damage([{"dice": "broken"}, "not a dict"]) == 0


class TestSlimPredictedState:
    def test_extracts_lean_id_and_sorts_tags(self) -> None:
        slim = _slim_predicted_state(
            {
                "entities": [
                    {
                        "id": {"val": 0},
                        "hp": 42,
                        "concentratingOn": "Hex",
                        "conditions": [{"tag": "haste"}, {"tag": "blessed"}],
                    }
                ]
            }
        )
        assert slim == {
            "entities": [
                {
                    "id": 0,
                    "hp": 42,
                    "concentratingOn": "Hex",
                    "conditionTags": ["blessed", "haste"],
                }
            ]
        }

    def test_int_id_accepted(self) -> None:
        slim = _slim_predicted_state({"entities": [{"id": 7, "hp": 1, "conditions": []}]})
        assert slim["entities"][0]["id"] == 7


class TestToLua:
    def test_primitives(self) -> None:
        assert _to_lua(None) == "nil"
        assert _to_lua(True) == "true"
        assert _to_lua(False) == "false"
        assert _to_lua(3) == "3"
        assert _to_lua("ab\"c") == '"ab\\"c"'

    def test_list(self) -> None:
        assert _to_lua([1, "x"]).startswith("{") and "1" in _to_lua([1, "x"])

    def test_dict_with_int_keys(self) -> None:
        out = _to_lua({0: "a", 1: "b"})
        assert "[0]" in out and "[1]" in out

    def test_dict_with_string_keys(self) -> None:
        out = _to_lua({"k": "v"})
        assert '["k"]' in out and '"v"' in out


class TestCompileToLua:
    def _read(self, p: Path) -> str:
        return p.read_text(encoding="utf-8")

    def test_produces_lua_file(self, tmp_path: Path) -> None:
        path = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={"entities": [{"id": {"val": 0}, "hp": 50, "conditions": []}]},
                    event={
                        "tag": "castSpell",
                        "caster": 0,
                        "spellName": "Fireball",
                        "target": {"tag": "single", "target": 1},
                    },
                ),
            ],
            axiom_name="fireball_damage",
        )
        out = compile_to_lua(path, tmp_path)
        assert out.suffix == ".lua"
        assert out.exists()
        content = self._read(out)
        # Spell uid baked into the action table.
        assert "Projectile_Fireball" in content
        # Schema declared.
        assert f"Schema version: {BRIDGE_SCHEMA_VERSION}" in content
        # Returns a script_data table for VALOR.Execute dispatch.
        assert "return {" in content
        assert '["actions"]' in content
        assert '["entity_id_map"]' in content
        # Uses real sandbox exports only.
        assert "VALOR.Sandbox.Setup" in content
        assert "Sandbox.ResetForValorTest" not in content
        assert "Sandbox.InitTestEnvironment" not in content
        assert "Sandbox.ApplyDamageRolls" not in content

    def test_weapon_attack_event(self, tmp_path: Path) -> None:
        path = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={"entities": []},
                    event={"tag": "weaponAttack", "attacker": 0, "target": 1},
                ),
            ],
            axiom_name="melee_test",
        )
        content = self._read(compile_to_lua(path, tmp_path))
        # Action type for weapon attacks is "attack" (consumed by execute.RunAction).
        assert '["type"] = "attack"' in content
        assert "[0]" in content and "[1]" in content  # entity_id_map covers both

    def test_take_damage_emits_apply_damage_with_worst_case(self, tmp_path: Path) -> None:
        path = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={"entities": []},
                    event={
                        "tag": "takeDamage",
                        "target": 1,
                        "rolls": [
                            {"dice": {"count": 8, "sides": 6, "bonus": 0}, "dmgType": "fire"}
                        ],
                    },
                )
            ],
            axiom_name="fireball_max",
        )
        content = self._read(compile_to_lua(path, tmp_path))
        assert '["type"] = "apply_damage"' in content
        assert '["amount"] = 48' in content

    def test_unsupported_event_becomes_noop(self, tmp_path: Path) -> None:
        path = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={"entities": []},
                    event={"tag": "unknownStuff"},
                ),
            ],
            axiom_name="edge",
        )
        content = self._read(compile_to_lua(path, tmp_path))
        assert '["type"] = "noop"' in content
        assert "Unsupported event" in content

    def test_status_translation_baked_in(self, tmp_path: Path) -> None:
        path = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={"entities": []},
                    event={"tag": "weaponAttack", "attacker": 0, "target": 1},
                )
            ],
            axiom_name="t",
        )
        content = self._read(compile_to_lua(path, tmp_path))
        assert "status_translation" in content
        # Sample mapping from the default table is present.
        first_engine_id = next(iter(DEFAULT_STATUS_TRANSLATION.keys()))
        assert first_engine_id in content


# ── log_analyzer ─────────────────────────────────────────────────────────────


class TestEventSignature:
    def test_tag_field(self) -> None:
        assert _event_signature({"tag": "castSpell", "extra": 1}) == "castSpell"

    def test_single_key_fallback(self) -> None:
        assert _event_signature({"weaponAttack": {}}) == "weaponAttack"


class TestNormalizeLogEntries:
    def test_sorts_by_step_index(self) -> None:
        lines = [
            '{"step_index": 2, "event": {"tag": "b"}}',
            '{"step_index": 0, "event": {"tag": "a"}}',
        ]
        rows = _normalize_log_entries(lines)
        assert rows[0]["step_index"] == 0
        assert rows[1]["step_index"] == 2

    def test_skips_blank_and_bad(self) -> None:
        lines = ["", "not json", '{"step_index": 0}']
        rows = _normalize_log_entries(lines)
        assert len(rows) == 1


class TestSlimEntities:
    def test_extracts_hp_and_conditions(self) -> None:
        state = {
            "entities": [
                {
                    "id": {"val": 0},
                    "hp": 42,
                    "conditions": [{"tag": "haste"}],
                    "concentratingOn": None,
                }
            ]
        }
        slimmed = _slim_entities(state)
        assert len(slimmed) == 1
        assert slimmed[0]["hp"] == 42
        assert slimmed[0]["conditionTags"] == ["haste"]

    def test_plain_int_id(self) -> None:
        state = {"entities": [{"id": 5, "hp": 10, "conditions": []}]}
        slimmed = _slim_entities(state)
        assert slimmed[0]["id"] == 5


class TestAnalyzeLog:
    def _make_log(self, tmp_path: Path, entries: list[dict]) -> Path:
        p = tmp_path / "combat.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
        return p

    def test_aligned(self, tmp_path: Path) -> None:
        log_entries = [
            {
                "step_index": 0,
                "event": {"tag": "castSpell"},
                "post_state": {
                    "entities": [
                        {"id": {"val": 0}, "hp": 50, "conditions": []},
                    ]
                },
            }
        ]
        expected = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={
                        "entities": [
                            {"id": {"val": 0}, "hp": 50, "conditions": []},
                        ]
                    },
                    event={"tag": "castSpell"},
                )
            ],
            axiom_name="test",
        )
        log_path = self._make_log(tmp_path, log_entries)
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.ALIGNED

    def test_hp_mismatch(self, tmp_path: Path) -> None:
        log_entries = [
            {
                "step_index": 0,
                "event": {"tag": "castSpell"},
                "post_state": {
                    "entities": [{"id": {"val": 0}, "hp": 999, "conditions": []}]
                },
            }
        ]
        expected = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={
                        "entities": [{"id": {"val": 0}, "hp": 50, "conditions": []}]
                    },
                    event={"tag": "castSpell"},
                )
            ],
            axiom_name="test",
        )
        log_path = self._make_log(tmp_path, log_entries)
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.VALUE_MISMATCH

    def test_missing_event(self, tmp_path: Path) -> None:
        log_path = self._make_log(tmp_path, [])
        expected = CounterexamplePath(
            steps=[CounterexampleStep(state={}, event={"tag": "x"})],
            axiom_name="test",
        )
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.MISSING_EVENT

    def test_extra_event(self, tmp_path: Path) -> None:
        log_entries = [
            {"step_index": 0, "event": {"tag": "a"}, "post_state": {"entities": []}},
            {"step_index": 1, "event": {"tag": "b"}, "post_state": {"entities": []}},
        ]
        expected = CounterexamplePath(
            steps=[CounterexampleStep(state={"entities": []}, event={"tag": "a"})],
            axiom_name="test",
        )
        log_path = self._make_log(tmp_path, log_entries)
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.EXTRA_EVENT

    def test_status_mismatch(self, tmp_path: Path) -> None:
        log_entries = [
            {
                "step_index": 0,
                "event": {"tag": "castSpell"},
                "post_state": {
                    "entities": [
                        {"id": {"val": 0}, "hp": 50, "conditions": [{"tag": "cursed"}]},
                    ]
                },
            }
        ]
        expected = CounterexamplePath(
            steps=[
                CounterexampleStep(
                    state={
                        "entities": [
                            {"id": {"val": 0}, "hp": 50, "conditions": [{"tag": "blessed"}]},
                        ]
                    },
                    event={"tag": "castSpell"},
                )
            ],
            axiom_name="test",
        )
        log_path = self._make_log(tmp_path, log_entries)
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.STATUS_MISMATCH

    def test_empty_path_no_log(self, tmp_path: Path) -> None:
        log_path = self._make_log(tmp_path, [])
        expected = CounterexamplePath(steps=[], axiom_name="test")
        report = analyze_log(log_path, expected)
        assert report.divergence_type == DivergenceType.ALIGNED
