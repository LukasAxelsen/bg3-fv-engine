"""
models.py — Canonical Data Models for BG3 Game Entities
========================================================

Every record that passes through the VALOR pipeline is represented by one
of the Pydantic models defined here.  The crawler writes them; the
auto-formalizer reads them; the evaluator compares against them.  A single
source of truth avoids schema drift across stages.
"""

from __future__ import annotations

import enum
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────

class DamageType(str, enum.Enum):
    ACID = "Acid"
    BLUDGEONING = "Bludgeoning"
    COLD = "Cold"
    FIRE = "Fire"
    FORCE = "Force"
    LIGHTNING = "Lightning"
    NECROTIC = "Necrotic"
    PIERCING = "Piercing"
    POISON = "Poison"
    PSYCHIC = "Psychic"
    RADIANT = "Radiant"
    SLASHING = "Slashing"
    THUNDER = "Thunder"


class School(str, enum.Enum):
    ABJURATION = "Abjuration"
    CONJURATION = "Conjuration"
    DIVINATION = "Divination"
    ENCHANTMENT = "Enchantment"
    EVOCATION = "Evocation"
    ILLUSION = "Illusion"
    NECROMANCY = "Necromancy"
    TRANSMUTATION = "Transmutation"


class CastingResource(str, enum.Enum):
    ACTION = "Action"
    BONUS_ACTION = "Bonus Action"
    REACTION = "Reaction"


class SaveAbility(str, enum.Enum):
    STR = "Strength"
    DEX = "Dexterity"
    CON = "Constitution"
    INT = "Intelligence"
    WIS = "Wisdom"
    CHA = "Charisma"


class StackType(str, enum.Enum):
    STACK = "Stack"
    IGNORE = "Ignore"
    OVERWRITE = "Overwrite"
    ADDITIVE = "Additive"


class TickType(str, enum.Enum):
    START_TURN = "StartTurn"
    END_TURN = "EndTurn"
    START_ROUND = "StartRound"
    END_ROUND = "EndRound"


class DamageLayerKind(str, enum.Enum):
    """Three-tier classification used by bg3.wiki/wiki/Damage_Mechanics.

    * ``DS``  — Damage Source: a direct damage event (weapon attack, spell hit,
      thrown item) that can deal damage on its own.
    * ``DR``  — Damage Rider: bonus damage that "rides along" a Source; cannot
      deal damage independently.
    * ``DRS`` — Damage Rider treated as a Source: a rider that, when it fires,
      is itself classified as a Source and therefore re-attracts every
      eligible Rider for a second pass.  This is the root cause of the
      thousand-damage Honour-mode-disabled exploits.
    """

    DS = "DS"
    DR = "DR"
    DRS = "DRS"


# ── Dice Expression ───────────────────────────────────────────────────────

_DICE_RE = re.compile(
    r"^(?P<count>\d+)d(?P<sides>\d+)(?:\s*\+\s*(?P<bonus>\d+))?$"
)


class DiceExpression(BaseModel):
    """Parsed NdM+B dice notation."""

    count: int = Field(ge=1)
    sides: int = Field(ge=1)
    bonus: int = Field(default=0, ge=0)
    raw: str

    @classmethod
    def parse(cls, text: str) -> Optional[DiceExpression]:
        text = text.strip()
        m = _DICE_RE.match(text)
        if not m:
            return None
        return cls(
            count=int(m["count"]),
            sides=int(m["sides"]),
            bonus=int(m["bonus"]) if m["bonus"] else 0,
            raw=text,
        )

    @property
    def min_value(self) -> int:
        return self.count + self.bonus

    @property
    def max_value(self) -> int:
        return self.count * self.sides + self.bonus

    @property
    def expected_value(self) -> float:
        return self.count * (self.sides + 1) / 2 + self.bonus


# ── Upcast Scaling ────────────────────────────────────────────────────────

class UpcastScaling(BaseModel):
    """How a spell improves when cast with a higher-level slot."""

    extra_dice_per_level: Optional[DiceExpression] = None
    extra_damage_type: Optional[DamageType] = None
    description: str = ""


# ── Condition Reference ───────────────────────────────────────────────────

class ConditionRef(BaseModel):
    """A condition applied or removed by a spell."""

    name: str
    duration_turns: Optional[int] = None
    save_to_avoid: Optional[SaveAbility] = None
    on_save: Optional[str] = None


# ── Core Entity: Spell ────────────────────────────────────────────────────

class Spell(BaseModel):
    """
    Complete mechanical record for a single BG3 spell.

    Every field is either directly parsed from the wiki's ``{{Feature page}}``
    template or derived from it.  No fabricated data.
    """

    name: str
    wiki_url: str
    uid: str = Field(description="Internal game UID, e.g. 'Projectile_Fireball'")

    level: int = Field(ge=0, le=9, description="0 = cantrip")
    school: Optional[School] = None

    summary: str = ""
    description: str = ""

    damage_dice: Optional[DiceExpression] = None
    damage_type: Optional[DamageType] = None

    casting_resource: Optional[CastingResource] = None
    spell_slot_level: Optional[int] = Field(default=None, ge=1, le=9)

    requires_attack_roll: bool = False
    save_ability: Optional[SaveAbility] = None
    on_save: Optional[str] = None

    range_m: Optional[float] = None
    aoe_m: Optional[float] = None
    aoe_shape: Optional[str] = None

    concentration: bool = False
    ritual: bool = False

    upcast: Optional[UpcastScaling] = None
    conditions: list[ConditionRef] = Field(default_factory=list)
    spell_flags: list[str] = Field(default_factory=list)

    classes: list[str] = Field(default_factory=list)

    notes: list[str] = Field(default_factory=list)
    bugs: list[str] = Field(default_factory=list)

    raw_wikitext: str = Field(
        default="",
        description="Verbatim wikitext for provenance and re-parsing",
    )

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Spell name must not be empty")
        return v.strip()


# ── Core Entity: Condition (Status Effect) ────────────────────────────────

class Condition(BaseModel):
    """Mechanical record for a BG3 condition / status effect."""

    name: str
    wiki_url: str

    stack_id: Optional[str] = None
    stack_type: Optional[StackType] = None
    tick_type: Optional[TickType] = None

    description: str = ""
    effects: list[str] = Field(default_factory=list)
    status_properties: list[str] = Field(default_factory=list)

    raw_wikitext: str = ""


# ── Core Entity: Passive Feature / Class Feature ──────────────────────────

class PassiveFeature(BaseModel):
    """A passive feature, invocation, or feat that modifies combat."""

    name: str
    wiki_url: str
    description: str = ""
    effects: list[str] = Field(default_factory=list)
    raw_wikitext: str = ""


# ── Core Entity: Damage-Layer Item (DS / DR / DRS classification) ────────

class DRSItem(BaseModel):
    """
    A single entry from bg3.wiki's *Damage Mechanics → DRS effects* tables.

    The model is shared between the data layer (parser / SQLite) and the
    proof layer: ``Axioms/DRSItems.lean`` is generated from a
    serialisation of these records, so any change in this schema must be
    reflected in both ends and is checked for drift by the test suite.
    """

    name: str = Field(description="Display name of the item or ability.")
    wiki_url: str = Field(description="Canonical bg3.wiki URL for provenance.")
    layer_kind: DamageLayerKind = Field(
        description="DS, DR or DRS classification per the wiki."
    )
    rider_dice: Optional[DiceExpression] = Field(
        default=None,
        description="Dice expression for the rider damage (where applicable).",
    )
    damage_type: Optional[DamageType] = Field(
        default=None,
        description="Damage type emitted by this layer.",
    )
    honour_demotes_to_dr: bool = Field(
        default=False,
        description=(
            "True iff the wiki documents that this DRS effect is treated as a "
            "plain DR in Honour mode (the documented Patch 5 behaviour)."
        ),
    )
    source_category: str = Field(
        default="",
        description="Free-form provenance: 'weapon', 'item', 'class feature', 'spell', etc.",
    )
    notes: str = Field(default="", description="Verbatim wiki note column.")

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("DRSItem name must not be empty")
        return v.strip()


# ── Database Envelope ─────────────────────────────────────────────────────

class CrawlRecord(BaseModel):
    """Wrapper that adds crawl metadata to any entity."""

    page_title: str
    page_id: int
    wiki_url: str
    entity_type: str = Field(description="'spell', 'condition', 'passive', 'drs_item'")
    raw_wikitext: str
    parsed: Optional[Spell | Condition | PassiveFeature | DRSItem] = None
    crawled_at: str = ""
    parse_errors: list[str] = Field(default_factory=list)
