"""
Compile a Lean ``CounterexamplePath`` into a BG3 Script Extender Lua replay script.

The generated script returns a ``script_data`` table that is dispatched by the
in-game oracle's ``main.lua`` to ``VALOR.Execute``.  Each action carries the
original Lean event JSON in ``__lean_event``, and ``script_data.entity_id_map``
maps Lean ``EntityId.val`` integers to engine GUIDs.  The oracle's
``execute.lua`` (schema_version = 2) writes one JSONL line per action with both
the canonical Lean view (``event`` + slim ``post_state`` keyed by Lean integer
ids) and the raw engine view (``pre_state_guid_map`` / ``post_state_guid_map``).

This module only calls helpers actually exported by ``sandbox.lua`` — it never
references ``Sandbox.ResetForValorTest`` etc., which previously caused the
oracle to crash when bridging.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Mapping

try:
    from .lean_parser import CounterexamplePath
except ImportError:  # pragma: no cover - flat PYTHONPATH to this directory
    from lean_parser import CounterexamplePath

logger = logging.getLogger(__name__)

#: Bridge wire-format version.  Bumped when the JSONL schema changes.
BRIDGE_SCHEMA_VERSION = 2

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

# Lean ``ConditionTag`` constructor names → engine status IDs (best-effort,
# used by the oracle to translate observed engine statuses into the Lean
# vocabulary so analyzer comparisons are apples-to-apples).
DEFAULT_STATUS_TRANSLATION: dict[str, str] = {
    "HASTE": "hastened",
    "SLOW": "lethargic",
    "HEX": "hexed",
    "BURNING": "burning",
    "WET": "wet",
    "FROZEN": "frozen",
    "PRONE": "prone",
    "STUNNED": "stunned",
    "BLINDED": "blinded",
    "SILENCED": "silenced",
    "INVISIBLE": "invisible",
    "BLESS": "blessed",
    "CURSE": "cursed",
    "SLEEPING": "sleeping",
    "DOWNED": "downed",
    "FRIGHTENED": "frightened",
    "CHARMED": "charmed",
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


def _worst_case_damage(rolls: list[Any]) -> int:
    """
    Sum the worst-case (maximum) damage over a list of Lean ``DamageRoll``s.

    A Lean ``DamageRoll`` serialises as ``{"dice": {"count": n, "sides": s, "bonus": b}, "dmgType": ...}``.
    We honour the ``Engine.lean`` worst-case semantics: ``count * sides + bonus``.
    """
    total = 0
    for r in rolls:
        if not isinstance(r, Mapping):
            continue
        dice = r.get("dice") or {}
        if not isinstance(dice, Mapping):
            continue
        count = int(dice.get("count", 0))
        sides = int(dice.get("sides", 0))
        bonus = int(dice.get("bonus", 0))
        total += count * sides + bonus
    return total


# ── Action builders (Lean event → execute.lua action dict) ─────────────────


def _action_cast_spell(event: Mapping[str, Any], uuid_for) -> dict[str, Any]:
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
    return {
        "type": "use_spell",
        "caster": uuid_for(caster),
        "spell": uid,
        "target": uuid_for(target_id),
        "__lean_event": dict(event),
    }


def _action_weapon_attack(event: Mapping[str, Any], uuid_for) -> dict[str, Any]:
    a = int(event.get("attacker", 0))
    t = int(event.get("target", 1))
    return {
        "type": "attack",
        "attacker": uuid_for(a),
        "target": uuid_for(t),
        "always_hit": 0,
        "__lean_event": dict(event),
    }


def _action_apply_condition(event: Mapping[str, Any], uuid_for) -> dict[str, Any]:
    source = int(event.get("source", 0))
    target = int(event.get("target", 1))
    cond = event.get("condition") or {}
    tag = cond.get("tag") if isinstance(cond, Mapping) else None
    status = _slug(str(tag)) if tag is not None else "UNKNOWN_STATUS"
    turns = cond.get("turnsLeft") if isinstance(cond, Mapping) else None
    duration = 1 if turns is None else int(turns)
    return {
        "type": "apply_status",
        "target": uuid_for(target),
        "status": status,
        "duration": duration,
        "source": uuid_for(source),
        "__lean_event": dict(event),
    }


def _action_take_damage(event: Mapping[str, Any], uuid_for) -> dict[str, Any]:
    """
    Map Lean ``takeDamage`` to ``set_hitpoints`` using the worst-case damage
    sum (consistent with ``Entity.applyDamage`` in ``Engine.lean``).

    Note: this is a fully-deterministic re-creation of the Lean engine's
    behaviour for replay purposes; the oracle independently records the
    engine's actual HP transition into ``post_state`` so the analyser can
    flag any divergence.
    """
    target = int(event.get("target", 1))
    rolls = event.get("rolls") or []
    dmg = _worst_case_damage(rolls if isinstance(rolls, list) else [])
    return {
        "type": "apply_damage",
        "target": uuid_for(target),
        "amount": dmg,
        "__lean_event": dict(event),
    }


def _build_action(event: Mapping[str, Any], uuid_for) -> dict[str, Any]:
    tag = _event_tag(event)
    if tag == "castSpell":
        return _action_cast_spell(event, uuid_for)
    if tag == "weaponAttack":
        return _action_weapon_attack(event, uuid_for)
    if tag == "applyCondition":
        return _action_apply_condition(event, uuid_for)
    if tag == "takeDamage":
        return _action_take_damage(event, uuid_for)
    return {
        "type": "noop",
        "reason": f"Unsupported event tag {tag!r}; extend lua_generator._build_action",
        "__lean_event": dict(event),
    }


# ── Predicted post-state (consumed by execute.lua for assertions) ──────────


def _slim_predicted_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Match the ``{entities: [{id, hp, concentratingOn, conditionTags}]}``
    shape that ``log_analyzer._slim_entities`` normalises to."""
    entities = state.get("entities")
    slim: list[dict[str, Any]] = []
    if isinstance(entities, list):
        for e in entities:
            if not isinstance(e, Mapping):
                continue
            eid = e.get("id")
            val: int | None = None
            if isinstance(eid, Mapping) and "val" in eid:
                val = int(eid["val"])
            elif isinstance(eid, int):
                val = eid
            conds = e.get("conditions") or []
            tags: list[str] = []
            if isinstance(conds, list):
                for c in conds:
                    if isinstance(c, Mapping) and "tag" in c:
                        tags.append(str(c["tag"]))
            tags.sort()
            slim.append(
                {
                    "id": val,
                    "hp": e.get("hp"),
                    "concentratingOn": e.get("concentratingOn"),
                    "conditionTags": tags,
                }
            )
    return {"entities": slim}


# ── Lua serialisation helpers ──────────────────────────────────────────────


def _to_lua(value: Any, indent: int = 0) -> str:
    """Serialise a Python value to a Lua literal expression.

    Lists become 1-indexed arrays; dicts become tables with string keys.  Ints,
    floats, bools, ``None`` and strings serialise to their Lua equivalents.
    """
    pad = "  " * indent
    inner_pad = "  " * (indent + 1)
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if not value:
            return "{}"
        parts = [_to_lua(v, indent + 1) for v in value]
        return "{\n" + ",\n".join(f"{inner_pad}{p}" for p in parts) + f"\n{pad}}}"
    if isinstance(value, Mapping):
        if not value:
            return "{}"
        items: list[str] = []
        for k, v in value.items():
            if isinstance(k, int):
                key = f"[{k}]"
            else:
                key = f"[{json.dumps(str(k), ensure_ascii=False)}]"
            items.append(f"{inner_pad}{key} = {_to_lua(v, indent + 1)}")
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    # Fallback: stringify
    return json.dumps(str(value), ensure_ascii=False)


def compile_to_lua(path: CounterexamplePath, output_dir: Path) -> Path:
    """
    Write a Lua script that replays ``path`` with sandbox setup and a
    structured ``script_data`` return value.

    Returns the path to the written ``.lua`` file under ``output_dir``.
    """
    out_dir = output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_uuid_map = (
        path.metadata.get("entity_uuids") if isinstance(path.metadata, Mapping) else None
    )
    uuid_overrides = meta_uuid_map if isinstance(meta_uuid_map, Mapping) else None

    def uuid_for(eid: int) -> str:
        return _entity_uuid(int(eid), uuid_overrides)

    axiom = path.axiom_name or "unknown_axiom"

    # Collect every Lean entity id we need a GUID for (so the oracle can map
    # observed snapshots back into Lean's vocabulary).
    used_ids: set[int] = set()
    for step in path.steps:
        ev = step.event or {}
        for k in ("caster", "attacker", "target", "source"):
            v = ev.get(k)
            if isinstance(v, int):
                used_ids.add(v)
        tgt = ev.get("target")
        if isinstance(tgt, Mapping):
            inner = tgt.get("target")
            if isinstance(inner, int):
                used_ids.add(inner)
        for ent in (step.state or {}).get("entities", []) or []:
            if isinstance(ent, Mapping):
                eid = ent.get("id")
                if isinstance(eid, Mapping) and isinstance(eid.get("val"), int):
                    used_ids.add(int(eid["val"]))
                elif isinstance(eid, int):
                    used_ids.add(eid)

    entity_id_map = {int(i): uuid_for(int(i)) for i in sorted(used_ids)}
    actions: list[dict[str, Any]] = []
    expected_states: list[dict[str, Any]] = []

    for step in path.steps:
        actions.append(_build_action(step.event, uuid_for))
        expected_states.append(_slim_predicted_state(step.state))

    script_data: dict[str, Any] = {
        "schema_version": BRIDGE_SCHEMA_VERSION,
        "axiom_name": axiom,
        "entity_id_map": entity_id_map,
        "status_translation": dict(DEFAULT_STATUS_TRANSLATION),
        "actions": actions,
        "expected_states": expected_states,
    }

    fname = f"valor_ce_{_slug(axiom)}_{int(time.time())}.lua"
    target = out_dir / fname

    lines: list[str] = [
        "-- VALOR generated counterexample replay (Lean → Lua bridge)",
        f"-- Axiom: {axiom}",
        f"-- Schema version: {BRIDGE_SCHEMA_VERSION}",
        "",
        "-- Preamble: deterministic harness (see Mods/VALOR_Injector/sandbox.lua).",
        "-- Only calls real exports of VALOR.Sandbox; if the mod has not loaded yet,",
        "-- we degrade gracefully with a warning rather than crashing.",
        "if VALOR and VALOR.Sandbox and VALOR.Sandbox.Setup then",
        '  VALOR.Sandbox.Setup({clear_entities_first = true})',
        "  if VALOR.Sandbox.ResetState then VALOR.Sandbox.ResetState() end",
        "else",
        "  if Ext and Ext.Print then",
        "    Ext.Print('[VALOR] Warning: VALOR.Sandbox not loaded; replay runs without harness reset')",
        "  end",
        "end",
        "",
        "return " + _to_lua(script_data) + "",
        "",
    ]

    target.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote Lua replay script: %s (%d steps)", target, len(path.steps))
    return target


# ── CLI ────────────────────────────────────────────────────────────────────


def _build_argparser() -> "argparse.ArgumentParser":  # pragma: no cover - thin wrapper
    import argparse

    p = argparse.ArgumentParser(
        prog="lua_generator",
        description=(
            "Compile a Lean counterexample (--input) or a registered probability "
            "scenario (--scenario) into a BG3 Script Extender Lua test script."
        ),
    )
    p.add_argument(
        "--input",
        type=Path,
        help="JSON file describing a CounterexamplePath ({steps:[{state,event}], axiom_name}).",
    )
    p.add_argument(
        "--scenario",
        type=str,
        help="Registered probability scenario name (e.g. p14_adv_dc11).",
    )
    p.add_argument(
        "--trials",
        type=int,
        default=1000,
        help="Number of trials for probability scenarios (default 1000).",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=1,
        help="Seed for the deterministic in-script LCG (default 1).",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output .lua path. Probability scenarios write here directly; "
        "counterexample mode uses this path's parent as output_dir. "
        "Required unless --list-scenarios is set.",
    )
    p.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List the registered probability scenarios and exit.",
    )
    return p


def _cli_main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    import argparse  # noqa: F401  (used by _build_argparser typing)

    args = _build_argparser().parse_args(argv)

    # Lazy import to avoid pulling probability_scenarios for normal counterexample use.
    try:
        from .probability_scenarios import (
            all_scenarios,
            compile_probability_lua,
            get_scenario,
        )
        from .lean_parser import CounterexamplePath, CounterexampleStep
    except ImportError:
        from probability_scenarios import (  # type: ignore[no-redef]
            all_scenarios,
            compile_probability_lua,
            get_scenario,
        )
        from lean_parser import CounterexamplePath, CounterexampleStep  # type: ignore[no-redef]

    if args.list_scenarios:
        for name, sc in all_scenarios().items():
            print(f"{name}\ttheoretical={sc.theoretical}\t{sc.description}")
        return 0

    if args.out is None:
        print("error: --out is required (use --list-scenarios to enumerate).", flush=True)
        return 2

    if args.scenario:
        sc = get_scenario(args.scenario)
        out = compile_probability_lua(
            sc, args.out, trials=args.trials, seed=args.seed
        )
        print(f"OK: wrote {sc.name} probability harness to {out}")
        return 0

    if args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        steps_payload = payload.get("steps") or []
        steps = [
            CounterexampleStep(state=s.get("state", {}), event=s.get("event", {}))
            for s in steps_payload
            if isinstance(s, Mapping)
        ]
        path = CounterexamplePath(
            steps=steps,
            axiom_name=payload.get("axiom_name") or payload.get("axiom"),
            metadata={k: v for k, v in payload.items() if k not in {"steps"}},
        )
        out_dir = args.out.parent if args.out.suffix == ".lua" else args.out
        target = compile_to_lua(path, out_dir)
        print(f"OK: wrote counterexample replay to {target}")
        return 0

    print(
        "error: provide either --scenario or --input (or --list-scenarios).",
        flush=True,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - module-as-script entrypoint
    raise SystemExit(_cli_main())
