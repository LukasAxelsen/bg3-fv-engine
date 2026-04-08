/-!
# P12 — Divine Smite + Critical Hit: Exact Damage Computation

## Background (bg3.wiki)

**Divine Smite** (Paladin): Expend a spell slot to deal extra Radiant
damage on a melee hit. Base: 2d8 Radiant for Level 1 slot, +1d8 per
slot level above 1st (max 5d8 at slot level 4+). Extra 1d8 vs Undead/Fiend.

**Critical Hit**: All damage DICE are doubled (modifiers are NOT doubled).

**Interaction**: On a crit with Divine Smite:
- Weapon dice doubled
- Smite dice doubled
- Undead bonus dice doubled
- Flat modifiers (STR, enchantment) NOT doubled

## Scenario: Paladin 6 / Sorcerer 6, Greatsword, Level 4 Smite, vs Undead

Build:
- Greatsword: 2d6 Slashing + 5 (STR 20) + 2 (Great Weapon Master)
- Divine Smite Level 4: 5d8 Radiant
- Undead bonus: 1d8 Radiant
- Total dice: 2d6 + 6d8 = 12 dice on normal hit

On Critical Hit: dice doubled = 4d6 + 12d8

## Properties Verified

- `normal_hit_max`: Maximum damage on a normal hit
- `crit_hit_max`: Maximum damage on a critical hit
- `crit_doubles_dice_only`: Modifiers are NOT doubled
- `undead_bonus_also_doubled`: The extra d8 vs undead IS doubled on crit
- `smite_level_scaling`: Each slot level adds exactly 1d8

## Quantifier Structure

∀ (slotLevel : Nat) (isUndead : Bool) (isCrit : Bool),
  smiteDamage slotLevel isUndead isCrit = expectedDamage slotLevel isUndead isCrit
-/

namespace VALOR.Scenarios.P12

-- ── Dice representation ─────────────────────────────────────────────────

structure DicePool where
  d6count  : Nat
  d8count  : Nat
  flatMod  : Nat  -- STR + enchantment + GWM etc.
  deriving DecidableEq, Repr

def DicePool.maxDamage (p : DicePool) : Nat :=
  p.d6count * 6 + p.d8count * 8 + p.flatMod

def DicePool.minDamage (p : DicePool) : Nat :=
  p.d6count + p.d8count + p.flatMod

/-- Average × 10 to stay in Nat. -/
def DicePool.avgX10 (p : DicePool) : Nat :=
  p.d6count * 35 + p.d8count * 45 + p.flatMod * 10

/-- Double all dice (critical hit). Flat modifiers stay unchanged. -/
def DicePool.critDouble (p : DicePool) : DicePool :=
  { p with d6count := p.d6count * 2, d8count := p.d8count * 2 }

-- ── Smite damage computation ────────────────────────────────────────────

/-- Divine Smite dice count: 1 + slot level (capped at 5d8 for slot 4+).
    Plus 1d8 if target is Undead or Fiend. -/
def smiteDice (slotLevel : Nat) (isUndead : Bool) : Nat :=
  let base := min (1 + slotLevel) 5
  if isUndead then base + 1 else base

-- ── Full attack damage pool ─────────────────────────────────────────────

/-- Greatsword + STR 20 + Great Weapon Master. -/
def greatswordBase : DicePool :=
  { d6count := 2, d8count := 0, flatMod := 7 }  -- 2d6 + 5 (STR) + 2 (GWM style)

/-- Full attack pool with smite. -/
def fullAttack (slotLevel : Nat) (isUndead : Bool) : DicePool :=
  let smiteD8 := smiteDice slotLevel isUndead
  { greatswordBase with d8count := smiteD8 }

/-- Critical hit version. -/
def fullAttackCrit (slotLevel : Nat) (isUndead : Bool) : DicePool :=
  (fullAttack slotLevel isUndead).critDouble

-- ── Concrete scenario: Level 4 slot, Undead target ──────────────────────

def scenario_normal := fullAttack 4 true
def scenario_crit   := fullAttackCrit 4 true

-- ── Verified properties ─────────────────────────────────────────────────

/-- Smite dice at slot 4 vs undead: min(1+4, 5) + 1 = 6. -/
theorem smite_dice_slot4_undead :
    smiteDice 4 true = 6 := by native_decide

/-- Normal hit pool: 2d6 + 6d8 + 7 flat. -/
theorem normal_pool :
    scenario_normal = { d6count := 2, d8count := 6, flatMod := 7 } := by native_decide

/-- Normal hit max: 2×6 + 6×8 + 7 = 12 + 48 + 7 = 67. -/
theorem normal_max :
    scenario_normal.maxDamage = 67 := by native_decide

/-- Normal hit min: 2 + 6 + 7 = 15. -/
theorem normal_min :
    scenario_normal.minDamage = 15 := by native_decide

/-- Crit pool: 4d6 + 12d8 + 7 flat (dice doubled, flat unchanged). -/
theorem crit_pool :
    scenario_crit = { d6count := 4, d8count := 12, flatMod := 7 } := by native_decide

/-- Crit max: 4×6 + 12×8 + 7 = 24 + 96 + 7 = 127. -/
theorem crit_max :
    scenario_crit.maxDamage = 127 := by native_decide

/-- Crit min: 4 + 12 + 7 = 23. -/
theorem crit_min :
    scenario_crit.minDamage = 23 := by native_decide

/-- Critical doubles dice, not flat: diff in max = crit_max - normal_max = 60.
    This equals the dice-only portion: (4-2)×6 + (12-6)×8 = 12 + 48 = 60. -/
theorem crit_bonus_is_dice_only :
    scenario_crit.maxDamage - scenario_normal.maxDamage = 60 := by native_decide

/-- Flat modifier is unchanged on crit. -/
theorem crit_preserves_flat :
    scenario_crit.flatMod = scenario_normal.flatMod := by native_decide

-- ── Smite scaling verification ──────────────────────────────────────────

/-- Each slot level adds exactly 1d8 (8 max damage) until cap at slot 4. -/
theorem smite_scaling_1 : smiteDice 1 false = 2 := by native_decide
theorem smite_scaling_2 : smiteDice 2 false = 3 := by native_decide
theorem smite_scaling_3 : smiteDice 3 false = 4 := by native_decide
theorem smite_scaling_4 : smiteDice 4 false = 5 := by native_decide
theorem smite_scaling_5 : smiteDice 5 false = 5 := by native_decide  -- cap!
theorem smite_scaling_6 : smiteDice 6 false = 5 := by native_decide  -- still cap

/-- Undead bonus is exactly +1d8 regardless of slot level. -/
theorem undead_bonus (slotLevel : Nat) (h : slotLevel ≥ 1 ∧ slotLevel ≤ 6) :
    smiteDice slotLevel true = smiteDice slotLevel false + 1 := by
  simp [smiteDice]
  omega

-- ── Cross-scenario comparison ───────────────────────────────────────────

/-- Crit Smite (127 max) vs max-damage Fireball (48): Smite deals 2.65× more.
    This justifies the Paladin "nova round" strategy in competitive play. -/
theorem smite_crit_vs_fireball :
    scenario_crit.maxDamage > 48 * 2 := by native_decide

/-- **OPEN (P12a)**: What is the maximum possible single-hit damage in BG3?
    Candidates: Assassin auto-crit from stealth + Smite + Sneak Attack +
    Colossus Slayer + weapon enchantments + DRS effects.
    Requires enumerating all damage sources that apply on a melee hit. -/

/-- **OPEN (P12b)**: Prove that for any target with resistance to Radiant,
    a Smite crit still outdamages a non-crit by at least 2×.
    (Resistance halves the Radiant portion only, not the weapon damage.) -/

end VALOR.Scenarios.P12
