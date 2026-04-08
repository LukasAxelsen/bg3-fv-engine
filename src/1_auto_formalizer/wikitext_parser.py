"""
wikitext_parser.py — MediaWiki {{Feature page}} Template Extractor
===================================================================

Parses the raw wikitext returned by the bg3.wiki API into structured
``Spell`` / ``Condition`` models.  This is a *deterministic* parser—no
LLM involved—operating on the well-defined ``{{Feature page}}`` template
syntax used by every spell, condition, and feature article on bg3.wiki.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .models import (
    CastingResource,
    ConditionRef,
    DamageType,
    DiceExpression,
    SaveAbility,
    School,
    Spell,
    UpcastScaling,
)


# ── Template extraction ───────────────────────────────────────────────────

def _extract_template_params(wikitext: str) -> dict[str, str]:
    """
    Pull the top-level ``{{Feature page|...}}`` parameters into a dict.

    Handles nested ``{{…}}`` by tracking brace depth so inner templates
    (e.g. ``{{DamageText|1d6|Fire}}``) don't split the outer parameter.
    """
    start = wikitext.find("{{Feature page")
    if start == -1:
        return {}

    depth = 0
    i = start
    end = len(wikitext)
    while i < end:
        if wikitext[i : i + 2] == "{{":
            depth += 1
            i += 2
        elif wikitext[i : i + 2] == "}}":
            depth -= 1
            if depth == 0:
                end = i
                break
            i += 2
        else:
            i += 1

    body = wikitext[start:end]
    # Remove the opening "{{Feature page"
    body = re.sub(r"^\{\{Feature page\s*", "", body)

    params: dict[str, str] = {}
    current_key: Optional[str] = None
    current_val_parts: list[str] = []

    for segment in _split_params(body):
        segment = segment.strip()
        if "=" in segment:
            eq = segment.index("=")
            if current_key is not None:
                params[current_key] = "\n".join(current_val_parts).strip()
            current_key = segment[:eq].strip().lstrip("| ").strip()
            current_val_parts = [segment[eq + 1 :]]
        elif current_key is not None:
            current_val_parts.append(segment)

    if current_key is not None:
        params[current_key] = "\n".join(current_val_parts).strip()

    return params


def _split_params(body: str) -> list[str]:
    """Split by top-level ``|`` respecting nested ``{{…}}``."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if body[i : i + 2] == "{{":
            depth += 1
            buf.append("{{")
            i += 2
            continue
        if body[i : i + 2] == "}}":
            depth -= 1
            buf.append("}}")
            i += 2
            continue
        if ch == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf))
    return parts


# ── Wikitext cleanup helpers ─────────────────────────────────────────────

def _strip_wiki_markup(text: str) -> str:
    """Remove ``[[…]]``, ``{{…}}``, and HTML tags, keeping display text."""
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_templates(text: str) -> str:
    """Remove all ``{{…}}`` templates, leaving raw text."""
    while "{{" in text:
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return text.strip()


_DAMAGE_TEMPLATE_RE = re.compile(
    r"\{\{DamageText\|([^|]+)\|([^}]+)\}\}"
)


# ── Parsing logic ─────────────────────────────────────────────────────────

def _parse_damage(params: dict[str, str]) -> tuple[Optional[DiceExpression], Optional[DamageType]]:
    dice = None
    dmg_type = None

    raw_dice = params.get("damage", "").strip()
    if raw_dice:
        dice = DiceExpression.parse(raw_dice)

    raw_type = params.get("damage type", "").strip()
    if raw_type:
        try:
            dmg_type = DamageType(raw_type)
        except ValueError:
            pass

    return dice, dmg_type


def _parse_casting_resource(params: dict[str, str]) -> tuple[Optional[CastingResource], Optional[int]]:
    cost = params.get("cost", "").lower()
    resource = None
    slot_level = None

    if "reaction" in cost:
        resource = CastingResource.REACTION
    elif "bonus" in cost:
        resource = CastingResource.BONUS_ACTION
    elif "action" in cost:
        resource = CastingResource.ACTION

    slot_match = re.search(r"spell(\d+)", cost)
    if slot_match:
        slot_level = int(slot_match.group(1))

    return resource, slot_level


_SAVE_MAP = {
    "STR": SaveAbility.STR, "Strength": SaveAbility.STR,
    "DEX": SaveAbility.DEX, "Dexterity": SaveAbility.DEX,
    "CON": SaveAbility.CON, "Constitution": SaveAbility.CON,
    "INT": SaveAbility.INT, "Intelligence": SaveAbility.INT,
    "WIS": SaveAbility.WIS, "Wisdom": SaveAbility.WIS,
    "CHA": SaveAbility.CHA, "Charisma": SaveAbility.CHA,
}


def _parse_save(params: dict[str, str]) -> tuple[Optional[SaveAbility], Optional[str]]:
    raw = params.get("save", "").strip()
    ability = _SAVE_MAP.get(raw)
    on_save = _strip_wiki_markup(params.get("on save", "")) or None
    return ability, on_save


def _parse_level(params: dict[str, str]) -> int:
    raw = params.get("level", "0").strip().lower()
    if raw in ("cantrip", "0"):
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _parse_conditions(params: dict[str, str]) -> list[ConditionRef]:
    refs: list[ConditionRef] = []
    for i in range(1, 10):
        key = f"condition {i}" if i > 1 else "condition 1"
        name = params.get(key, "").strip()
        if not name:
            name = params.get(f"condition {i}", "").strip()
        if not name:
            break
        dur_raw = params.get(f"condition {i} duration", "").strip()
        dur = int(dur_raw) if dur_raw.isdigit() else None
        refs.append(ConditionRef(name=_strip_wiki_markup(name), duration_turns=dur))
    # Also handle bare "condition" key (no number)
    if not refs:
        bare = params.get("condition", "").strip()
        if bare:
            refs.append(ConditionRef(name=_strip_wiki_markup(bare)))
    return refs


def _parse_classes(params: dict[str, str]) -> list[str]:
    raw = params.get("classes", "")
    parts = [c.strip() for c in raw.split(",") if c.strip()]
    return parts


def _parse_notes(params: dict[str, str], key: str = "notes") -> list[str]:
    raw = params.get(key, "").strip()
    if not raw:
        return []
    lines = raw.split("\n")
    result: list[str] = []
    for line in lines:
        line = line.strip().lstrip("*").strip()
        if line:
            result.append(_strip_wiki_markup(line))
    return result


def _parse_upcast(params: dict[str, str]) -> Optional[UpcastScaling]:
    raw = params.get("higher levels", "").strip()
    if not raw:
        return None
    m = _DAMAGE_TEMPLATE_RE.search(raw)
    if m:
        dice = DiceExpression.parse(m.group(1))
        try:
            dmg_type = DamageType(m.group(2))
        except ValueError:
            dmg_type = None
        return UpcastScaling(
            extra_dice_per_level=dice,
            extra_damage_type=dmg_type,
            description=_strip_wiki_markup(raw),
        )
    return UpcastScaling(description=_strip_wiki_markup(raw))


def _parse_flags(params: dict[str, str]) -> list[str]:
    raw = params.get("spell flags", "")
    return [f.strip() for f in raw.split(",") if f.strip()]


# ── Public API ────────────────────────────────────────────────────────────

def parse_spell(page_title: str, wikitext: str) -> tuple[Optional[Spell], list[str]]:
    """
    Parse a single spell's wikitext into a ``Spell`` model.

    Returns ``(spell, errors)`` where *errors* lists any fields that could
    not be parsed.  A spell is returned even if some optional fields fail.
    """
    errors: list[str] = []
    params = _extract_template_params(wikitext)

    if not params:
        return None, [f"No {{{{Feature page}}}} template found in '{page_title}'"]

    entity_type = params.get("type", "").strip().lower()
    if entity_type and entity_type != "spell":
        return None, [f"Page '{page_title}' is type='{entity_type}', not 'spell'"]

    level = _parse_level(params)
    school: Optional[School] = None
    raw_school = params.get("school", "").strip()
    if raw_school:
        try:
            school = School(raw_school)
        except ValueError:
            errors.append(f"Unknown school: {raw_school}")

    damage_dice, damage_type = _parse_damage(params)
    casting_resource, slot_level = _parse_casting_resource(params)
    save_ability, on_save = _parse_save(params)
    conditions = _parse_conditions(params)
    upcast = _parse_upcast(params)
    flags = _parse_flags(params)

    range_m: Optional[float] = None
    raw_range = params.get("range m", "").strip()
    if raw_range:
        try:
            range_m = float(raw_range)
        except ValueError:
            errors.append(f"Invalid range: {raw_range}")

    aoe_m: Optional[float] = None
    raw_aoe = params.get("aoe m", "").strip()
    if raw_aoe:
        try:
            aoe_m = float(raw_aoe)
        except ValueError:
            errors.append(f"Invalid AoE: {raw_aoe}")

    aoe_shape = params.get("aoe", "").strip() or None
    concentration = params.get("concentration", "").strip().lower() == "yes"
    ritual = params.get("ritual", "").strip().lower() == "yes"
    attack_roll = params.get("attack roll", "").strip().lower() == "yes"

    uid = params.get("uid", "").strip()
    if not uid:
        errors.append("Missing UID")
        uid = f"Unknown_{page_title.replace(' ', '_')}"

    wiki_url = f"https://bg3.wiki/wiki/{page_title.replace(' ', '_')}"

    try:
        spell = Spell(
            name=page_title,
            wiki_url=wiki_url,
            uid=uid,
            level=level,
            school=school,
            summary=_strip_wiki_markup(params.get("summary", "")),
            description=_strip_wiki_markup(params.get("description", "")),
            damage_dice=damage_dice,
            damage_type=damage_type,
            casting_resource=casting_resource,
            spell_slot_level=slot_level,
            requires_attack_roll=attack_roll,
            save_ability=save_ability,
            on_save=on_save,
            range_m=range_m,
            aoe_m=aoe_m,
            aoe_shape=aoe_shape,
            concentration=concentration,
            ritual=ritual,
            upcast=upcast,
            conditions=conditions,
            spell_flags=flags,
            classes=_parse_classes(params),
            notes=_parse_notes(params, "notes"),
            bugs=_parse_notes(params, "bugs"),
            raw_wikitext=wikitext,
        )
        return spell, errors
    except Exception as exc:
        return None, errors + [f"Model validation failed: {exc}"]
