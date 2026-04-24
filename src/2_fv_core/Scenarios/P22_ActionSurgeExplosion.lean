/-!
# P22 — Action Surge × Extra Attack × Haste: Combinatorial Action Explosion

## Background (bg3.wiki)

BG3's action economy allows stacking multiple "extra action" sources:

- **Extra Attack** (Fighter 5, Paladin 5, etc.): 2 attacks per Attack action
- **Extra Attack ×2** (Fighter 11): 3 attacks per Attack action (BG3-specific)
- **Action Surge** (Fighter 2): one additional Action per turn (1/short rest)
- **Haste** (spell): grants one additional Action (Attack, Dash, Hide only)
- **Thief 3 (Fast Hands)**: extra Bonus Action
- **Berserker 3 (Frenzy)**: bonus action melee attack during Rage

## Key Question

What is the maximum number of attacks a single character can make
in one turn?  Is the combinatorial explosion finite and computable?

## Academic Significance

This models a **resource graph** where each "action source" generates
attack slots, and multiclass stacking creates a combinatorial tree.
We enumerate all valid action sequences and prove an exact upper
bound — establishing that the game's action economy is bounded
despite the appearance of multiplicative stacking.

## Quantifier Structure

∀ (build : Build), validBuild build →
  maxAttacks build ≤ GLOBAL_UPPER_BOUND ∧
  ∃ (build : Build), maxAttacks build = GLOBAL_UPPER_BOUND
-/

namespace VALOR.Scenarios.P22

-- ── Build configuration ─────────────────────────────────────────────────

structure Build where
  extraAttackTier : Nat   -- 0 = none, 1 = Extra Attack, 2 = Extra Attack ×2
  hasActionSurge  : Bool  -- Fighter 2+
  hasHaste        : Bool  -- someone casts Haste on you
  hasFrenzy       : Bool  -- Berserker 3 Rage
  hasThief        : Bool  -- Thief 3 Fast Hands
  hasCrossbow     : Bool  -- Crossbow Expert: bonus action attack
  deriving DecidableEq, Repr

/-- Number of attacks per Attack action. -/
def attacksPerAction (b : Build) : Nat :=
  match b.extraAttackTier with
  | 0 => 1
  | 1 => 2
  | _ => 3  -- Fighter 11 in BG3

/-- Number of Attack actions per turn. -/
def attackActions (b : Build) : Nat :=
  let base := 1
  let surge := if b.hasActionSurge then 1 else 0
  let haste := if b.hasHaste then 1 else 0
  base + surge + haste

/-- Bonus action attacks.  At most 1 bonus action (2 if Thief). -/
def bonusAttacks (b : Build) : Nat :=
  let bonusActions := if b.hasThief then 2 else 1
  let sources := (if b.hasFrenzy then 1 else 0) +
                 (if b.hasCrossbow then 1 else 0)
  min sources bonusActions

/-- Total maximum attacks in one turn. -/
def maxAttacks (b : Build) : Nat :=
  attackActions b * attacksPerAction b + bonusAttacks b

-- ── Concrete builds ─────────────────────────────────────────────────────

/-- Fighter 11 with Action Surge + Haste: 3 attack actions × 3 attacks = 9. -/
def fighter11Haste : Build :=
  ⟨2, true, true, false, false, false⟩

/-- Fighter 11 / Thief 3: Surge + Haste + 2 bonus actions. -/
def fighter11Thief3 : Build :=
  ⟨2, true, true, false, true, true⟩

/-- Fighter 5 / Berserker 3 / Thief 4: Extra Attack + Surge + Haste + Frenzy. -/
def multiclass_fighter_berserker_thief : Build :=
  ⟨1, true, true, true, true, false⟩

/-- The "kitchen sink" build: Fighter 11 + Berserker 3 (Frenzy) + Thief 3 +
    Crossbow Expert + Haste + Action Surge.  Every attack-multiplier source
    enabled.  Note: the original draft of this file omitted Frenzy and
    therefore mis-claimed `maxAttacks = 11` — the correct value is 10 for
    that build (since `bonusAttacks = min(1, 2) = 1`).  We restore Frenzy
    so the kitchen-sink moniker actually reaches the global ceiling. -/
def kitchenSink : Build :=
  ⟨2, true, true, true, true, true⟩

-- ── Verified properties ─────────────────────────────────────────────────

/-- Pure Fighter 11 with Haste: 3 × 3 + 0 = 9 attacks. -/
theorem fighter11_haste_attacks :
    maxAttacks fighter11Haste = 9 := by native_decide

/-- With Thief's extra bonus action + crossbow: 3 × 3 + 2 = 11 attacks. -/
theorem kitchen_sink_attacks :
    maxAttacks kitchenSink = 11 := by native_decide

/-- Fighter 5 / Berserker 3 / Thief 4 with Haste:
    3 attack actions × 2 attacks + 1 frenzy = 7 attacks. -/
theorem multiclass_attacks :
    maxAttacks multiclass_fighter_berserker_thief = 7 := by native_decide

-- ── Global upper bound ──────────────────────────────────────────────────

/-- All possible builds: 3 Extra Attack tiers × 2⁵ booleans = 96 combinations.
    The original draft incorrectly claimed 192 (2⁶ × 3), conflating the count
    of booleans (5) with the count of feature flags including the tier (6). -/
def allBuilds : List Build := Id.run do
  let mut acc : List Build := []
  for ea in [0, 1, 2] do
    for as_ in [true, false] do
      for h in [true, false] do
        for f in [true, false] do
          for t in [true, false] do
            for cb in [true, false] do
              acc := ⟨ea, as_, h, f, t, cb⟩ :: acc
  return acc

theorem total_builds : allBuilds.length = 96 := by native_decide

def globalMax : Nat :=
  allBuilds.foldl (fun acc b => max acc (maxAttacks b)) 0

/-- The global maximum across ALL builds is 11 attacks per turn. -/
theorem global_max_is_11 : globalMax = 11 := by native_decide

/-- No build exceeds 11 attacks. -/
theorem no_build_exceeds_11 :
    allBuilds.all (fun b => maxAttacks b ≤ 11) = true := by native_decide

/-- Exactly how many builds achieve the maximum?  With the corrected
    arithmetic, only one build hits 11 attacks: every flag must be true and
    the Extra Attack tier must be 2 (Fighter 11). -/
def optimalBuildCount : Nat :=
  (allBuilds.filter (fun b => maxAttacks b == 11)).length

theorem unique_optimal_build : optimalBuildCount = 1 := by native_decide

-- ── Damage output comparison ────────────────────────────────────────────

/-- Fighter 11 (Greatsword 2d6+5) × 11 attacks = max 11 × 17 = 187 weapon damage. -/
theorem max_weapon_damage :
    11 * (12 + 5) = 187 := by native_decide

/-! ## Open problems

**P22a.** With Eldritch Blast at Level 17+ (4 beams), does a Warlock with
Haste + Quickened EB exceed 11 "attack" instances?  EB is not an Attack
action, so it may bypass the attack count limit.  Requires modelling EB
as separate from the Attack action.

**P22b.** Prove that for any build with N attacks and damage-per-attack D,
the maximum turn DPR = N · D is achieved by the build that maximises the
product — not necessarily the one with the most attacks.  This is a
Lagrange-multiplier argument subject to the 12-level budget constraint.
-/

end VALOR.Scenarios.P22
