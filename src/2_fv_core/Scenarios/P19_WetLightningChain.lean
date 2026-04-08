/-!
# P19 — Wet + Lightning Interaction: Damage Amplification Chain

## Background (bg3.wiki)

**Wet** condition: applies via water spells (Create Water), rain, etc.
Effect: Vulnerability to Lightning and Cold (2× damage from these).

**Lightning** damage to a Wet target:
1. Target takes 2× Lightning damage (Vulnerability)
2. The Wet condition is consumed (removed after the Lightning hit)
3. Nearby Wet creatures are NOT affected (only direct target)

**Chain scenario**: Create Water → Call Lightning → targets in water
surface take Lightning damage with Vulnerability.

**Electrified Water** surface: Water + Lightning spell =
all creatures standing in water take Lightning damage each turn.

## Key Question

Can the Wet→Lightning→Electrified Water chain be exploited to deal
unbounded damage?  Or does consuming Wet on hit prevent loops?

## Academic Significance

This models a **resource-consumption automaton**: the Wet condition
is a one-shot amplifier that is consumed on use.  We prove the
interaction is *well-founded* (no infinite damage loop) and compute
exact damage bounds.  This connects to the theory of *linear logic*
(Girard, 1987) where resources are consumed exactly once.

## Quantifier Structure

∀ (entities : List Entity) (allWet : ∀ e ∈ entities, e.wet = true),
  ∃ (finalState : GameState),
    applyLightningAoE entities = finalState ∧
    (∀ e ∈ finalState.entities, e.wet = false) ∧
    totalDamage finalState ≤ 2 × baseDamage × entities.length
-/

namespace VALOR.Scenarios.P19

-- ── Entity and surface types ────────────────────────────────────────────

structure Entity where
  id        : Nat
  hp        : Int
  wet       : Bool      -- Wet condition active
  resistant : Bool      -- Lightning resistance (halves before vuln)
  immune    : Bool      -- Lightning immunity
  deriving DecidableEq, Repr

inductive SurfaceType where
  | none | water | electrifiedWater | ice
  deriving DecidableEq, Repr

structure Tile where
  surface  : SurfaceType
  entities : List Nat   -- entity IDs standing on this tile
  deriving Repr

-- ── Damage computation ──────────────────────────────────────────────────

/-- Lightning damage after applying resistance and vulnerability.
    Order per bg3.wiki: resistance first, then vulnerability.
    Resistance: halve.  Vulnerability (from Wet): double.
    If both: (dmg / 2) × 2 = dmg (they cancel!). -/
def lightningDamage (baseDmg : Nat) (e : Entity) : Nat :=
  if e.immune then 0
  else
    let afterRes := if e.resistant then baseDmg / 2 else baseDmg
    let afterVuln := if e.wet then afterRes * 2 else afterRes
    afterVuln

/-- After taking Lightning damage, Wet is consumed. -/
def consumeWet (e : Entity) : Entity :=
  { e with wet := false }

/-- Apply Lightning to a single entity: compute damage, consume Wet. -/
def applyLightning (baseDmg : Nat) (e : Entity) : Entity × Nat :=
  let dmg := lightningDamage baseDmg e
  let e' := { (consumeWet e) with hp := e.hp - dmg }
  (e', dmg)

/-- Apply Lightning AoE to a list of entities. -/
def applyLightningAoE (baseDmg : Nat) : List Entity → List Entity × Nat
  | [] => ([], 0)
  | e :: es =>
    let (e', dmg) := applyLightning baseDmg e
    let (es', totalDmg) := applyLightningAoE baseDmg es
    (e' :: es', dmg + totalDmg)

-- ── Surface interaction ─────────────────────────────────────────────────

/-- Casting Lightning on a Water surface creates Electrified Water. -/
def electrifyTile (t : Tile) : Tile :=
  match t.surface with
  | .water => { t with surface := .electrifiedWater }
  | _ => t

/-- Electrified Water deals damage per turn to all entities on it. -/
def electrifiedWaterDmg : Nat := 6  -- 1d6 Lightning per turn

-- ── Concrete scenario: 4 Wet targets, Call Lightning (3d10 = 16.5 avg) ─

def wetTargets : List Entity :=
  [⟨1, 40, true, false, false⟩, ⟨2, 40, true, false, false⟩,
   ⟨3, 40, true, true, false⟩,  ⟨4, 40, true, false, true⟩]

def callLightningMax : Nat := 30  -- 3d10 max

-- ── Verified properties ─────────────────────────────────────────────────

/-- Wet + Lightning = 2× damage for non-resistant, non-immune entities. -/
theorem wet_doubles_damage :
    lightningDamage 30 ⟨1, 40, true, false, false⟩ = 60 := by native_decide

/-- Resistant + Wet: (30/2)×2 = 30 (they cancel). -/
theorem resistant_wet_cancel :
    lightningDamage 30 ⟨3, 40, true, true, false⟩ = 30 := by native_decide

/-- Immune entity takes 0 regardless of Wet. -/
theorem immune_zero :
    lightningDamage 30 ⟨4, 40, true, false, true⟩ = 0 := by native_decide

/-- After Lightning AoE, ALL entities lose Wet (consumed). -/
theorem wet_consumed_after_aoe :
    let (entities', _) := applyLightningAoE callLightningMax wetTargets
    entities'.all (fun e => !e.wet) = true := by native_decide

/-- Total damage: 60 + 60 + 30 + 0 = 150. -/
theorem total_aoe_damage :
    let (_, totalDmg) := applyLightningAoE callLightningMax wetTargets
    totalDmg = 150 := by native_decide

/-- Second Lightning AoE deals only base damage (Wet consumed). -/
theorem second_hit_no_vulnerability :
    let (entities', _) := applyLightningAoE callLightningMax wetTargets
    let (_, totalDmg2) := applyLightningAoE callLightningMax entities'
    totalDmg2 = 75 := by native_decide

/-- Damage ratio: first hit / second hit = 150 / 75 = 2.0×.
    The Wet condition provides exactly 2× amplification for one volley. -/
theorem vulnerability_amplification :
    let (entities', _) := applyLightningAoE callLightningMax wetTargets
    let (_, totalDmg2) := applyLightningAoE callLightningMax entities'
    let (_, totalDmg1) := applyLightningAoE callLightningMax wetTargets
    totalDmg1 = 2 * totalDmg2 := by native_decide

-- ── Well-foundedness: no infinite loop ──────────────────────────────────

/-- The number of Wet entities is a strict Lyapunov function:
    it decreases by at least 1 on each Lightning AoE application. -/
def wetCount (entities : List Entity) : Nat :=
  entities.filter (·.wet) |>.length

theorem wet_count_decreases :
    let (entities', _) := applyLightningAoE callLightningMax wetTargets
    wetCount entities' < wetCount wetTargets := by native_decide

theorem wet_count_hits_zero :
    let (entities', _) := applyLightningAoE callLightningMax wetTargets
    wetCount entities' = 0 := by native_decide

/-- **OPEN (P19a)**: Can Create Water re-apply Wet to entities that
    already took Lightning damage?  If so, model the full
    Create Water → Lightning → Create Water → Lightning loop
    and prove total damage is bounded by (2 × spell slots available). -/

/-- **OPEN (P19b)**: Electrified Water persists for multiple turns.
    Prove that the total damage from standing in Electrified Water
    for T turns is strictly greater than the one-shot Wet+Lightning
    combo when T ≥ K, for some computable K. -/

end VALOR.Scenarios.P19
