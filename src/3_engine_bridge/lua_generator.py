"""
Compile a Lean ``CounterexamplePath`` into a BG3 Script Extender Lua replay script.

Maps abstract events to Osiris calls, injects sandbox setup from ``sandbox.lua``, and
emits per-step assertions so the in-game oracle can detect drift from the formal model.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from .lean_parser import CounterexamplePath
except ImportError:  # pragma: no cover - flat PYTHONPATH to this directory
    from lean_parser import CounterexamplePath

logger = logging.getLogger(__name__)

# Spell display name → BG3 spell UID / resource id (Osiris ``UseSpell``).
SPELL_UID_MAP: dict[str, str] = {
    "Fireball": "Projectile_Fireball",
    "Haste": "Target_Haste",
    "Hex": "Target_Hex",
    "Counterspell": "Target_Counterspell",
    "Hellish Rebuke": "Target_HellishRebuke",
    "Eldritch Blast": "Projectile_EldritchBlast",
}

# Lean ``EntityId.val`` → placeholder engine UUIDs (replace in mod integration).
DEFAULT_ENTITY_UUIDS: dict[int, str] = {
    0: "00000000-0000-4000-8000-000000000000",
    1: "00000000-0000-4000-8000-000000000001",
    2: "00000000-0000-4000-8000-000000000002",
}


def _slug(s: str) -> str:
    s = s.strip().lower().replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", s)


def _entity_uuid(entity_id: int, overrides: Mapping[int, str] | None) -> str:
    m = dict(DEFAULT_ENTITY_UUIDS)
    if overrides:
        m.update({int(k): v for k, v in overrides.items()})
    return m.get(entity_id, f"00000000-0000-4000-8000-{entity_id:012d}")


def _lua_string(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _event_tag(event: Mapping[str, Any]) -> str | None:
    tag = event.get("tag")
    if isinstance(tag, str):
        return tag
    if len(event) == 1:
        return str(next(iter(event.keys())))
    return None


def _emit_cast_spell(event: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    caster = int(event.get("caster", 0))
    spell = str(event.get("spellName", event.get("spell", "")))
    uid = SPELL_UID_MAP.get(spell, _slug(spell) or "UNKNOWN_SPELL")
    target_block = event.get("target") or {}
    target_id = 1
    if isinstance(target_block, Mapping):
        if target_block.get("tag") == "single" and "target" in target_block:
            target_id = int(target_block["target"])
        elif target_block.get("tag") == "self":
            target_id = caster
    return [f"Osi.UseSpell({uuid_for(caster)}, {_lua_string(uid)}, {uuid_for(target_id)})"]


def _emit_weapon_attack(event: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    a = int(event.get("attacker", 0))
    t = int(event.get("target", 1))
    return [f"Osi.Attack({uuid_for(a)}, {uuid_for(t)})"]


def _emit_apply_condition(event: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    source = int(event.get("source", 0))
    target = int(event.get("target", 1))
    cond = event.get("condition") or {}
    tag = cond.get("tag") if isinstance(cond, Mapping) else None
    status = _slug(str(tag)) if tag is not None else "UNKNOWN_STATUS"
    turns = cond.get("turnsLeft") if isinstance(cond, Mapping) else None
    duration = 1 if turns is None else int(turns)
    return [f"Osi.ApplyStatus({uuid_for(target)}, {_lua_string(status)}, {duration}, {uuid_for(source)})"]


def _emit_take_damage(event: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    target = int(event.get("target", 1))
    rolls = event.get("rolls") or []
    payload = json.dumps(rolls, ensure_ascii=False)
    return [
        "if Sandbox and Sandbox.ApplyDamageRolls then",
        f"  Sandbox.ApplyDamageRolls({uuid_for(target)}, {payload})",
        "else",
        f"  error('VALOR: Sandbox.ApplyDamageRolls missing for takeDamage @ entity {target}')",
        "end",
    ]


def _emit_event_lines(event: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    tag = _event_tag(event)
    if tag == "castSpell":
        return _emit_cast_spell(event, uuid_for)
    if tag == "weaponAttack":
        return _emit_weapon_attack(event, uuid_for)
    if tag == "applyCondition":
        return _emit_apply_condition(event, uuid_for)
    if tag == "takeDamage":
        return _emit_take_damage(event, uuid_for)
    return [f"-- Unsupported event tag {tag!r}; extend lua_generator._emit_event_lines"]


def _expected_snapshot_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    entities = state.get("entities")
    slim: list[dict[str, Any]] = []
    if isinstance(entities, list):
        for e in entities:
            if not isinstance(e, Mapping):
                continue
            eid = e.get("id")
            val = None
            if isinstance(eid, Mapping) and "val" in eid:
                val = int(eid["val"])
            conds = e.get("conditions") or []
            tags: list[str] = []
            if isinstance(conds, list):
                for c in conds:
                    if isinstance(c, Mapping) and "tag" in c:
                        tags.append(str(c["tag"]))
            slim.append(
                {
                    "id": val,
                    "hp": e.get("hp"),
                    "concentratingOn": e.get("concentratingOn"),
                    "conditionTags": tags,
                }
            )
    return {"entities": slim}


def _emit_assertions(step_index: int, expected: Mapping[str, Any], uuid_for: Callable[[int], str]) -> list[str]:
    uuid_lines: list[str] = []
    for ent in expected.get("entities", []) or []:
        if isinstance(ent, Mapping) and ent.get("id") is not None:
            i = int(ent["id"])
            uuid_lines.append(f"    [{i}] = {uuid_for(i)},")

    return [
        f"-- Post-step assertions (Lean predicted vs engine) step {step_index}",
        "-- HP via Osiris; status checks rely on execute.lua JSON snapshots + log_analyzer.py",
        "do",
        f"  local __expected = {json.dumps(expected, ensure_ascii=False)}",
        "  local __uuids = {",
        *uuid_lines,
        "  }",
        "  for _, ent in ipairs(__expected.entities or {}) do",
        "    local guid = __uuids[ent.id]",
        "    local hp = Osi.GetHitpoints(guid)",
        f"    assert(hp == ent.hp, string.format("
        f'"VALOR VALUE_MISMATCH step {step_index} entity %s hp expected %s got %s", '
        f"tostring(ent.id), tostring(ent.hp), tostring(hp)))",
        "  end",
        "end",
    ]


def compile_to_lua(path: CounterexamplePath, output_dir: Path) -> Path:
    """
    Write a Lua script that replays ``path`` with sandbox setup and per-step asserts.

    Returns the path to the written ``.lua`` file under ``output_dir``.
    """
    out_dir = output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_uuid_map = path.metadata.get("entity_uuids") if isinstance(path.metadata, Mapping) else None
    uuid_overrides = meta_uuid_map if isinstance(meta_uuid_map, Mapping) else None

    def uuid_for(eid: int) -> str:
        return _lua_string(_entity_uuid(int(eid), uuid_overrides))

    axiom = path.axiom_name or "unknown_axiom"
    fname = f"valor_ce_{_slug(axiom)}_{int(time.time())}.lua"
    target = out_dir / fname

    lines: list[str] = [
        "-- VALOR generated counterexample replay (Lean → Lua bridge)",
        f"-- Axiom: {axiom}",
        "",
        "-- Preamble: deterministic harness (see Mods/VALOR_Injector/sandbox.lua)",
        "if Sandbox and Sandbox.ResetForValorTest then",
        "  Sandbox.ResetForValorTest()",
        "elseif Sandbox and Sandbox.InitTestEnvironment then",
        "  Sandbox.InitTestEnvironment()",
        "else",
        "  Ext.Print('[VALOR] Warning: sandbox setup functions not found')",
        "end",
        "",
    ]

    for i, step in enumerate(path.steps):
        exp_post = _expected_snapshot_from_state(step.state)
        lines.append(f"-- Step {i}: apply event then assert post-state snapshot")
        lines.extend(_emit_event_lines(step.event, uuid_for))
        lines.append("Ext.Timer.WaitFor(250)")
        lines.extend(_emit_assertions(i, exp_post, uuid_for))
        lines.append("")

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote Lua replay script: %s (%d steps)", target, len(path.steps))
    return target
