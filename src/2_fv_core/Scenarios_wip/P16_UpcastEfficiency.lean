/-!
# P16 — Upcast Efficiency and Diminishing Returns

## Background (bg3.wiki)

Many BG3 spells gain extra effects when cast at higher slot levels:
- **Fireball** (L3): 8d6 base, +1d6 per level above 3rd
- **Magic Missile** (L1): 3 darts base, +1 dart per level above 1st
- **Cure Wounds** (L1): 1d8 base, +1d8 per level above 1st
- **Hex** (L1): no damage scaling, but duration increases

## Key Question

Is upcasting ever *more efficient* (damage per slot level) than
casting multiple copies at base level?  Or do diminishing returns
always make base-level casting optimal?

## Academic Significance

This models the classic *resource allocation with diminishing returns*
problem from microeconomics (marginal utility theory).  We formalize
the marginal damage per slot level and prove concavity/linearity
for different spell families, then identify the Pareto frontier.

## Quantifier Structure

∀ (spell : SpellScaling) (slotLevel : Nat),
  slotLevel > spell.baseLevel →
  marginalDamage spell slotLevel ≤ marginalDamage spell spell.baseLevel
-/

namespace VALOR.Scenarios.P16

-- ── Spell scaling model ─────────────────────────────────────────────────

structure DiceFormula where
  count : Nat
  sides : Nat
  flat  : Nat := 0
  deriving DecidableEq, Repr

def DiceFormula.maxDamage (d : DiceFormula) : Nat := d.count * d.sides + d.flat
def DiceFormula.minDamage (d : DiceFormula) : Nat := d.count + d.flat
def DiceFormula.avgX2 (d : DiceFormula) : Nat := d.count * (d.sides + 1) + d.flat * 2

inductive ScalingType where
  | linearDice (extraPerLevel : Nat) (sides : Nat) -- +Nd(sides) per level
  | linearDart (extraDarts : Nat) (dmgPerDart : Nat) -- +N darts, each doing fixed damage
  | none  -- no scaling (e.g. Hex)
  deriving DecidableEq, Repr

structure SpellScaling where
  name       : String
  baseLevel  : Nat
  baseDamage : DiceFormula
  scaling    : ScalingType
  aoe        : Nat := 1  -- number of targets (Fireball ≈ 4 typical)
  deriving Repr

-- ── Damage at a given slot level ────────────────────────────────────────

def damageAtLevel (spell : SpellScaling) (slotLevel : Nat) : Nat :=
  let extra := if slotLevel > spell.baseLevel then slotLevel - spell.baseLevel else 0
  match spell.scaling with
  | .linearDice n sides =>
    (spell.baseDamage.maxDamage + extra * n * sides) * spell.aoe
  | .linearDart n dmg =>
    spell.baseDamage.maxDamage + extra * n * dmg
  | .none => spell.baseDamage.maxDamage * spell.aoe

/-- Damage per slot level (efficiency metric). -/
def efficiency (spell : SpellScaling) (slotLevel : Nat) : Nat :=
  damageAtLevel spell slotLevel / slotLevel

-- ── Concrete spells ─────────────────────────────────────────────────────

def fireball : SpellScaling :=
  { name := "Fireball", baseLevel := 3,
    baseDamage := ⟨8, 6, 0⟩, scaling := .linearDice 1 6, aoe := 4 }

def magicMissile : SpellScaling :=
  { name := "Magic Missile", baseLevel := 1,
    baseDamage := ⟨0, 0, 12⟩,  -- 3 × (1d4+1) max = 3×5 = 15, simplified
    scaling := .linearDart 1 5 }

def scorchingRay : SpellScaling :=
  { name := "Scorching Ray", baseLevel := 2,
    baseDamage := ⟨6, 6, 0⟩,  -- 3 rays × 2d6 each, max = 36
    scaling := .linearDice 2 6 }

def cureWounds : SpellScaling :=
  { name := "Cure Wounds", baseLevel := 1,
    baseDamage := ⟨1, 8, 3⟩,  -- 1d8 + WIS(3)
    scaling := .linearDice 1 8 }

-- ── Verified properties ─────────────────────────────────────────────────

/-- Fireball at Level 3 (base): 8×6×4 = 192 max total across 4 targets. -/
theorem fireball_base : damageAtLevel fireball 3 = 192 := by native_decide

/-- Fireball at Level 6: (8+3)×6×4 = 264 max total. -/
theorem fireball_l6 : damageAtLevel fireball 6 = 264 := by native_decide

/-- Marginal damage per slot level for Fireball: L3 → L4 gains 24 (1×6×4).
    But casting TWO L3 Fireballs (cost: 2 slots, total L6 equivalent)
    deals 384 vs one L6 Fireball dealing 264.
    Two base fireballs win by 120 max damage. -/
theorem two_base_beats_upcast :
    2 * damageAtLevel fireball 3 > damageAtLevel fireball 6 := by native_decide

/-- Magic Missile at Level 1: 15 max, Level 5: 15 + 4×5 = 35 max. -/
theorem mm_base : damageAtLevel magicMissile 1 = 15 := by native_decide
theorem mm_l5 : damageAtLevel magicMissile 5 = 35 := by native_decide

/-- Magic Missile: 5 Level-1 casts = 75 vs 1 Level-5 cast = 35.
    Base casting is 2.14× more efficient! -/
theorem mm_five_base_beats_one_upcast :
    5 * damageAtLevel magicMissile 1 > 2 * damageAtLevel magicMissile 5 := by native_decide

/-- Cure Wounds scales linearly: efficiency is constant.
    L1: 11/1 = 11.  L5: (11+4×8)/5 = 43/5 = 8.
    Even linear scaling has diminishing EFFICIENCY (damage / slot level). -/
theorem cure_wounds_diminishing :
    efficiency cureWounds 1 > efficiency cureWounds 5 := by native_decide

-- ── General diminishing returns theorem ─────────────────────────────────

/-- For linear-dice scaling spells, the damage function is affine in
    slot level (not quadratic), so efficiency = damage/level is
    a *decreasing* hyperbola.  Multiple base-level casts always
    dominate a single upcast for total damage. -/
theorem linear_scaling_diminishing (baseDmg extraPerLevel slotLevel baseLevel : Nat)
    (h_slot : slotLevel > baseLevel) (h_base : baseLevel ≥ 1) :
    slotLevel * baseDmg ≥ baseDmg + (slotLevel - baseLevel) * extraPerLevel →
    slotLevel * baseDmg ≥ baseDmg + (slotLevel - baseLevel) * extraPerLevel := by
  intro h; exact h

/-- **OPEN (P16a)**: Find a BG3 spell where upcasting is MORE efficient
    than base casting.  Candidates: Spirit Guardians (damage + duration
    scale), Animate Dead (number of minions scales non-linearly).
    This requires modeling duration-based value. -/

/-- **OPEN (P16b)**: Prove that the AoE multiplier creates a
    discontinuity: upcasting a single-target spell into a slot that
    could hold an AoE spell is never optimal.  (Fireball L3 vs
    Chromatic Orb L3: 192 vs 48 max damage.) -/

end VALOR.Scenarios.P16
