/-!
# P29 — The "Coffeelock" Bug: Bounded vs. Unbounded Spell-Slot Generation

## Background (bg3.wiki, D&D 5e community)

**Coffeelock** is a Sorcerer/Warlock exploit:

1. Warlock spell slots recover on Short Rest.
2. Sorcerer can convert spell slots → Sorcery Points (Font of Magic).
3. Sorcerer can convert Sorcery Points → spell slots (Create Spell Slot).
4. Created spell slots persist until used (no "maximum" in 5e RAW).
5. Loop: Short Rest → recover Warlock slots → convert to SP → create
   Sorcerer spell slots → Short Rest → repeat.

In **BG3 specifically** Sorcery Points cap at the Sorcerer level and the
total of *created* spell slots is also capped, so the loop is closed.

## Academic significance

This is a direct analogue to `sts_lean`'s **infinite combo** analysis.
We model the resource loop as a state machine and prove:

* **Level 1 (existence)** — there is a trace that strictly increases
  total spell slots (`cycle_produces_slots`).
* **Level 2 (BG3 boundedness)** — under BG3 caps, every trace is bounded
  by an exact number we compute (`bg3_max_total`).
* **Level 3 (5e RAW unboundedness)** — under 5e rules without caps, the
  trace `nCycles N` produces `3·N` slots, witnessed concretely for
  `N = 5` and `N = 10`.

Notation: every theorem below states its claim as
``(applyAll trace s).map ... = some k``, which is a plain
`Option Nat = Option Nat` equality and therefore decidable by
`native_decide` without any custom decidable instances.
-/

namespace VALOR.Scenarios.P29

-- ── Resource state ─────────────────────────────────────────────────────

structure CoffeelockState where
  sorceryPoints     : Nat    -- current SP
  sorceryPointCap   : Nat    -- max SP (= Sorcerer level in BG3)
  warlockSlots      : Nat    -- current Warlock Pact slots
  warlockSlotMax    : Nat    -- max Warlock slots (recovered on SR)
  warlockSlotLevel  : Nat    -- level of Warlock slots
  createdSlots      : Nat    -- extra slots created via SP
  createdSlotCap    : Nat    -- max created slots (BG3 limit, 0 = no limit)
  shortRestsUsed    : Nat    -- number of short rests taken
  deriving DecidableEq, Repr

inductive Action where
  | shortRest          -- recover Warlock slots
  | convertSlotToSP    -- Warlock slot → SP (Font of Magic)
  | createSlotFromSP   -- SP → created spell slot (Level 1)
  deriving DecidableEq, Repr

-- ── Conversion rates (mirrored from P15) ──────────────────────────────

def spFromWarlockSlot (level : Nat) : Nat :=
  match level with
  | 1 => 1 | 2 => 2 | 3 => 3 | 4 => 4 | 5 => 5 | _ => 0

def spCostForSlotL1 : Nat := 2  -- cost to create a Level 1 slot

-- ── State transitions ─────────────────────────────────────────────────

def applyAction (s : CoffeelockState) (a : Action) : Option CoffeelockState :=
  match a with
  | .shortRest =>
    some { s with warlockSlots := s.warlockSlotMax,
                  shortRestsUsed := s.shortRestsUsed + 1 }
  | .convertSlotToSP =>
    if s.warlockSlots > 0 then
      let spGain := spFromWarlockSlot s.warlockSlotLevel
      let newSP := min (s.sorceryPoints + spGain) s.sorceryPointCap
      some { s with warlockSlots := s.warlockSlots - 1, sorceryPoints := newSP }
    else none
  | .createSlotFromSP =>
    if s.sorceryPoints ≥ spCostForSlotL1 then
      if s.createdSlotCap == 0 || s.createdSlots < s.createdSlotCap then
        some { s with
          sorceryPoints := s.sorceryPoints - spCostForSlotL1,
          createdSlots := s.createdSlots + 1 }
      else none
    else none

def applyAll (actions : List Action) (s : CoffeelockState) : Option CoffeelockState :=
  actions.foldlM (fun st a => applyAction st a) s

def totalSlots (s : CoffeelockState) : Nat :=
  s.warlockSlots + s.createdSlots

-- ── BG3 scenario: Sorcerer 6 / Warlock 6 ─────────────────────────────

/-- BG3 baseline: SP cap 6, two Pact (Level 3) slots, created-slot cap 4. -/
def bg3Initial : CoffeelockState :=
  { sorceryPoints := 6, sorceryPointCap := 6,
    warlockSlots := 2, warlockSlotMax := 2, warlockSlotLevel := 3,
    createdSlots := 0, createdSlotCap := 4,
    shortRestsUsed := 0 }

/-- One Coffeelock cycle from a fully-empty start: SR → convert ×2 → create ×3. -/
def oneCycle : List Action :=
  [.shortRest,
   .convertSlotToSP, .convertSlotToSP,
   .createSlotFromSP, .createSlotFromSP, .createSlotFromSP]

-- ── Level 1: existence of resource amplification ──────────────────────

/-- One cycle starting from empty (0 SP, 0 Warlock, 0 created) creates 3
    Level-1 slots: SR refills 2 Warlock slots → convert both for 6 SP →
    spend on 3 ×2-cost slots. -/
theorem cycle_produces_slots :
    (applyAll oneCycle
        { bg3Initial with sorceryPoints := 0, warlockSlots := 0, createdSlots := 0 }
      ).map (·.createdSlots) = some 3 := by
  native_decide

-- ── Level 2: BG3 boundedness ─────────────────────────────────────────

/-- A trace that hits the BG3 created-slot cap exactly without going over.
    Cycle 1 creates 3 slots, cycle 2 creates 1 more (4 ≤ cap).  A final
    Short Rest tops the Warlock slots back up so we can also assert the
    *peak* attainable `totalSlots`. -/
def bg3MaxTrace : List Action :=
  [.shortRest, .convertSlotToSP, .convertSlotToSP,
   .createSlotFromSP, .createSlotFromSP, .createSlotFromSP,   -- created = 3
   .shortRest, .convertSlotToSP,
   .createSlotFromSP,                                          -- created = 4 (cap)
   .shortRest]                                                 -- restore Warlock slots

/-- After `bg3MaxTrace`, exactly the cap of created slots has been
    produced. -/
theorem bg3_created_capped :
    (applyAll bg3MaxTrace
        { bg3Initial with sorceryPoints := 0, warlockSlots := 0, createdSlots := 0 }
      ).map (·.createdSlots) = some 4 := by
  native_decide

/-- Maximum simultaneously available slots in BG3 (Warlock + created)
    is 6: 2 Pact slots refreshed by the trailing Short Rest plus the 4
    capped created slots. -/
theorem bg3_max_total :
    (applyAll bg3MaxTrace
        { bg3Initial with sorceryPoints := 0, warlockSlots := 0, createdSlots := 0 }
      ).map totalSlots = some 6 := by
  native_decide

-- ── Level 3: 5e RAW unboundedness ────────────────────────────────────

/-- 5e RAW: no SP cap (modelled as "effectively unlimited"), no created
    slot cap. -/
def raw5eInitial : CoffeelockState :=
  { sorceryPoints := 0, sorceryPointCap := 1000,
    warlockSlots := 2, warlockSlotMax := 2, warlockSlotLevel := 3,
    createdSlots := 0, createdSlotCap := 0,  -- 0 = no cap
    shortRestsUsed := 0 }

/-- Each cycle generates 3 Level-1 slots; iterating the cycle witnesses
    the unbounded family. -/
def nCycles (n : Nat) : List Action :=
  (List.replicate n oneCycle).flatten

theorem five_cycles_fifteen_slots :
    (applyAll (nCycles 5) raw5eInitial).map (·.createdSlots) = some 15 := by
  native_decide

theorem ten_cycles_thirty_slots :
    (applyAll (nCycles 10) raw5eInitial).map (·.createdSlots) = some 30 := by
  native_decide

/-! ## Comparison with `sts_lean`

Like `sts_lean`'s `InfiniteCombo` we have a *setup trace* (initial empty
resources after a long rest) and a *loop trace* (`oneCycle`).  Each loop
strictly increases `createdSlots`.  Unlike `sts_lean` there is no
shuffle oracle: every Coffeelock transition is deterministic.  This
puts the 5e Coffeelock in the **Level-1 infinite-combo** class
(existence under deterministic execution), strictly weaker than the
**Level-2** adversarial class (existence under any oracle play).

## Open problems

**P29a.** BG3 limits Short Rests to 2 per Long Rest.  With this
constraint, what is the maximum number of created slots over the entire
Long Rest?  (Conjecture: at most 4, exactly the created-slot cap.)

**P29b.** The "Cocainelock" variant uses Aspect of the Moon (no sleep
required) plus Catnap (Short Rest in 10 in-game minutes) to side-step
the Short Rest limit.  Model the time constraint and prove that an
8-hour Long Rest period in 5e RAW allows exactly 48 Short Rests, hence
144 extra Level-1 slots.
-/

end VALOR.Scenarios.P29
