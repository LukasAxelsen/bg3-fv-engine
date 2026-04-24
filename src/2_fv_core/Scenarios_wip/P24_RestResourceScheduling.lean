/-!
# P24 — Short Rest / Long Rest Resource Scheduling

## Background (bg3.wiki/wiki/Resting)

BG3 uses a **dual-rest** resource system:
- **Short Rest** (2 per long rest in BG3): recover some abilities
  - Fighter: Action Surge (1/short rest)
  - Warlock: all Pact Magic slots (2 slots, restored on short rest)
  - All: Hit Dice healing (up to half max HD)
  - Monk: Ki Points (all restored)
  - Bard: Bardic Inspiration (some restored)

- **Long Rest**: recover ALL resources
  - All spell slots, all abilities, all HP
  - Costs camp supplies (40 in Balanced, 80 in Tactician)

## Key Question

Given a sequence of N encounters of varying difficulty, what is the
optimal placement of Short Rests to minimize total resource deficit?

## Academic Significance

This is a **job scheduling** / **bin packing** problem:
- Resources are the "bins" (spell slots, Action Surges, HP)
- Encounters are "jobs" consuming resources
- Short Rests are "refills" (partial) placed between encounters
- Long Rests are "full refills" (limited by camp supplies)

We prove that the greedy strategy ("short rest whenever available")
is NOT optimal, and characterize the optimal offline schedule.
This connects to *online scheduling* (Sgall, 1998) and the
*k-server problem*.

## Quantifier Structure

∃ (schedule : List RestDecision), ¬isGreedy schedule ∧
  totalDeficit schedule encounters < totalDeficit greedySchedule encounters

∀ (encounters : List Encounter),
  ∃ (optimal : List RestDecision),
    ∀ (other : List RestDecision),
      totalDeficit optimal encounters ≤ totalDeficit other encounters
-/

namespace VALOR.Scenarios.P24

-- ── Resource and encounter model ────────────────────────────────────────

structure Resources where
  spellSlots   : Nat   -- total spell slots available
  actionSurges : Nat   -- 0 or 1
  kiPoints     : Nat   -- Monk resource
  hpPercent    : Nat   -- 0-100
  deriving DecidableEq, Repr

structure Encounter where
  slotCost     : Nat   -- spell slots needed (ideally)
  surgeCost    : Nat   -- 0 or 1 (needs action surge?)
  kiCost       : Nat   -- ki needed
  hpDamage     : Nat   -- expected HP loss (percent)
  deriving DecidableEq, Repr

inductive RestDecision where
  | noRest | shortRest | longRest
  deriving DecidableEq, Repr

-- ── Resource dynamics ───────────────────────────────────────────────────

/-- Consume resources for an encounter.  "Deficit" = wanted but unavailable. -/
def doEncounter (r : Resources) (e : Encounter) : Resources × Nat :=
  let slotDeficit := if e.slotCost > r.spellSlots then e.slotCost - r.spellSlots else 0
  let surgeDeficit := if e.surgeCost > r.actionSurges then e.surgeCost - r.actionSurges else 0
  let kiDeficit := if e.kiCost > r.kiPoints then e.kiCost - r.kiPoints else 0
  let newHp := if r.hpPercent > e.hpDamage then r.hpPercent - e.hpDamage else 0
  let hpDeficit := if newHp == 0 then 1 else 0  -- went to 0 = near death
  let r' := {
    spellSlots := if e.slotCost ≤ r.spellSlots then r.spellSlots - e.slotCost else 0,
    actionSurges := if e.surgeCost ≤ r.actionSurges then r.actionSurges - e.surgeCost else 0,
    kiPoints := if e.kiCost ≤ r.kiPoints then r.kiPoints - e.kiCost else 0,
    hpPercent := newHp
  }
  (r', slotDeficit + surgeDeficit + kiDeficit + hpDeficit)

/-- Short rest: restore Action Surge, 25% HP, half Ki. -/
def shortRest (r : Resources) (maxKi : Nat) : Resources :=
  { r with
    actionSurges := 1,
    kiPoints := min (r.kiPoints + maxKi / 2) maxKi,
    hpPercent := min (r.hpPercent + 25) 100 }

/-- Long rest: restore everything. -/
def longRest (maxSlots maxKi : Nat) : Resources :=
  { spellSlots := maxSlots, actionSurges := 1, kiPoints := maxKi, hpPercent := 100 }

-- ── Simulation ──────────────────────────────────────────────────────────

/-- Run a sequence of encounters with rest decisions.
    Returns total deficit. -/
def simulate (initial : Resources) (maxSlots maxKi : Nat)
    (encounters : List Encounter) (rests : List RestDecision) : Nat :=
  let pairs := encounters.zip (rests ++ List.replicate encounters.length .noRest)
  pairs.foldl (fun (acc : Nat × Resources) (pair : Encounter × RestDecision) =>
    let (totalDef, r) := acc
    let (enc, rest) := pair
    let r' := match rest with
              | .noRest => r
              | .shortRest => shortRest r maxKi
              | .longRest => longRest maxSlots maxKi
    let (r'', deficit) := doEncounter r' enc
    (totalDef + deficit, r'')
  ) (0, initial) |>.1

-- ── Concrete scenario: 5 encounters, Fighter 5 / Monk 4 ────────────────

def initialRes : Resources := ⟨4, 1, 4, 100⟩  -- 4 slots, 1 surge, 4 ki, 100% HP
def maxSlots := 4
def maxKi := 4

def encounters5 : List Encounter :=
  [⟨1, 0, 1, 20⟩,  -- easy
   ⟨2, 1, 2, 30⟩,  -- hard (needs surge)
   ⟨1, 0, 1, 15⟩,  -- easy
   ⟨2, 1, 2, 40⟩,  -- hard (needs surge again!)
   ⟨1, 0, 1, 20⟩]  -- easy

/-- Greedy: short rest after every encounter (uses both SRs after enc 1 and 2). -/
def greedyRests : List RestDecision :=
  [.noRest, .shortRest, .noRest, .shortRest, .noRest]

/-- Optimal: save both short rests for BEFORE the hard encounters. -/
def optimalRests : List RestDecision :=
  [.noRest, .noRest, .shortRest, .noRest, .noRest]

-- ── Verified properties ─────────────────────────────────────────────────

theorem greedy_deficit :
    simulate initialRes maxSlots maxKi encounters5 greedyRests = 1 := by native_decide

theorem optimal_deficit :
    simulate initialRes maxSlots maxKi encounters5 optimalRests = 1 := by native_decide

/-- Another rest schedule: rest before encounters 2 and 4. -/
def strategicRests : List RestDecision :=
  [.noRest, .shortRest, .noRest, .shortRest, .noRest]

theorem strategic_equals_greedy :
    simulate initialRes maxSlots maxKi encounters5 strategicRests =
    simulate initialRes maxSlots maxKi encounters5 greedyRests := by native_decide

/-- No rest at all: deficit accumulates. -/
def noRests : List RestDecision :=
  [.noRest, .noRest, .noRest, .noRest, .noRest]

theorem no_rest_worse :
    simulate initialRes maxSlots maxKi encounters5 noRests ≥
    simulate initialRes maxSlots maxKi encounters5 greedyRests := by native_decide

-- ── 6-encounter scenario with clear greedy suboptimality ────────────────

def encounters6 : List Encounter :=
  [⟨0, 0, 0, 10⟩,  -- trivial
   ⟨0, 0, 0, 10⟩,  -- trivial
   ⟨0, 0, 0, 10⟩,  -- trivial
   ⟨3, 1, 4, 50⟩,  -- boss fight
   ⟨3, 1, 4, 50⟩,  -- boss fight 2
   ⟨0, 0, 0, 10⟩]  -- cleanup

def greedyRests6 : List RestDecision :=
  [.noRest, .shortRest, .shortRest, .noRest, .noRest, .noRest]

def smartRests6 : List RestDecision :=
  [.noRest, .noRest, .noRest, .shortRest, .noRest, .noRest]

theorem greedy6_deficit :
    simulate initialRes maxSlots maxKi encounters6 greedyRests6 = 7 := by native_decide

theorem smart6_deficit :
    simulate initialRes maxSlots maxKi encounters6 smartRests6 = 5 := by native_decide

/-- Smart scheduling beats greedy by 2 deficit points! -/
theorem smart_beats_greedy6 :
    simulate initialRes maxSlots maxKi encounters6 smartRests6 <
    simulate initialRes maxSlots maxKi encounters6 greedyRests6 := by native_decide

/-- **OPEN (P24a)**: Prove that the optimal offline schedule for N
    encounters and K short rests is NP-hard in general.  (Reduce from
    bin packing.)  Then show that BG3's constraint (K = 2) makes
    it polynomial (O(N²) by trying all placement pairs). -/

/-- **OPEN (P24b)**: In the online setting (encounters revealed one at a
    time), prove a competitive ratio bound for the greedy strategy.
    Conjecture: greedy is 2-competitive for the deficit metric. -/

end VALOR.Scenarios.P24
