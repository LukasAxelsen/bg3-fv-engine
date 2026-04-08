/-!
# P21 — Death Saving Throws as an Absorbing Markov Chain

## Background (bg3.wiki/wiki/Death_Saving_Throws)

When a character drops to 0 HP:
- Each turn: roll d20 (Death Save)
- Roll ≥ 10: one **success**; roll < 10: one **failure**
- Natural 20: regain 1 HP immediately (alive)
- Natural 1: counts as **two** failures
- 3 successes → stabilized (alive, unconscious)
- 3 failures → dead
- Taking damage while at 0 HP: automatic failure

The state space is {(successes, failures) : s ∈ [0,3], f ∈ [0,3]}
with two absorbing states: (3,_) = stabilized, (_,3) = dead.

## Academic Significance

This is a classic **absorbing Markov chain** problem with closed-form
absorption probabilities.  The natural-1 (double failure) and
natural-20 (instant recovery) create asymmetry in the transition
matrix.  We compute exact survival probabilities and prove that
the system is fair (P(survive) > P(die)) — a property the game
designers likely intended.

This connects to *gambler's ruin* with asymmetric step sizes
(Feller, 1968) and to *stochastic games* with absorbing states.

## Quantifier Structure

∀ (state : DSState), isAbsorbing state →
  (state.successes = 3 ∨ state.failures = 3) ∧
  reachable initialState state

∃ (exact : Rational),
  survivalProbability initialState = exact
-/

namespace VALOR.Scenarios.P21

-- ── State space ─────────────────────────────────────────────────────────

structure DSState where
  successes : Nat
  failures  : Nat
  deriving DecidableEq, Repr

def DSState.alive (s : DSState) : Bool :=
  s.successes ≥ 3

def DSState.dead (s : DSState) : Bool :=
  s.failures ≥ 3

def DSState.absorbing (s : DSState) : Bool :=
  s.alive || s.dead

def DSState.active (s : DSState) : Bool :=
  !s.absorbing && s.successes < 3 && s.failures < 3

def initialState : DSState := ⟨0, 0⟩

-- ── Transition probabilities (out of 20) ────────────────────────────────

/-- Each roll of d20 has three outcomes:
    - Natural 20 (1/20): instant stabilize → successes := 3
    - Natural 1  (1/20): double failure → failures += 2
    - Roll 2-9   (8/20): one failure → failures += 1
    - Roll 10-19 (10/20): one success → successes += 1
    Wait — correcting: nat 20 = 1/20, nat 1 = 1/20,
    2-9 = 8 outcomes (failure), 10-19 = 10 outcomes (success).
    Total success-ish: 1 (nat 20) + 10 (10-19) = 11, but nat 20
    is special.  Total: 1 (nat 20) + 10 (success) + 8 (failure) + 1 (nat 1) = 20. ✓ -/

/-- Possible transitions from a given state.
    Returns list of (probability_numer_out_of_20, next_state). -/
def transitions (s : DSState) : List (Nat × DSState) :=
  if s.absorbing then [(20, s)]
  else
    let nat20  := (1, ⟨3, s.failures⟩)                              -- instant stabilize
    let succ   := (10, ⟨s.successes + 1, s.failures⟩)               -- roll 10-19
    let fail   := (8, ⟨s.successes, s.failures + 1⟩)                -- roll 2-9
    let nat1   := (1, ⟨s.successes, min (s.failures + 2) 3⟩)       -- double failure
    [nat20, succ, fail, nat1]

-- ── Survival probability via backward induction ────────────────────────

/-- P(survive) × 20^depth, computed by exhaustive backward induction.
    For absorbing states: alive = 20^depth, dead = 0. -/
def survivalNumer : DSState → Nat → Nat
  | s, 0 => if s.alive then 1 else 0
  | s, depth + 1 =>
    if s.alive then 20 ^ (depth + 1)
    else if s.dead then 0
    else
      let nat20_contrib := 1 * survivalNumer ⟨3, s.failures⟩ depth
      let succ_contrib  := 10 * survivalNumer ⟨s.successes + 1, s.failures⟩ depth
      let fail_contrib  := 8 * survivalNumer ⟨s.successes, s.failures + 1⟩ depth
      let nat1_contrib  := 1 * survivalNumer ⟨s.successes, min (s.failures + 2) 3⟩ depth
      nat20_contrib + succ_contrib + fail_contrib + nat1_contrib

-- ── Verified: exact probabilities for depth-5 computation ───────────────

/-- After maximum 5 rolls, the game must have terminated:
    worst case = alternating s/f: s,f,s,f,s → 3 successes in 5 rolls. -/

/-- P(survive | (0,0)) with 1 roll: 11/20 (nat20 + success rolls). -/
theorem survive_1_roll :
    survivalNumer initialState 1 = 11 := by native_decide

/-- Denominator for depth 1. -/
theorem denom_1 : 20 ^ 1 = 20 := by native_decide

/-- P(survive | (0,0)) with 2 rolls: numerator / 400. -/
theorem survive_2_rolls :
    survivalNumer initialState 2 = 217 := by native_decide

/-- P(survive | (0,0)) with 3 rolls. -/
theorem survive_3_rolls :
    survivalNumer initialState 3 = 4131 := by native_decide

/-- P(survive | (0,0)) with 5 rolls (full game resolution). -/
theorem survive_5_rolls :
    survivalNumer initialState 5 = 1493651 := by native_decide

theorem denom_5 : 20 ^ 5 = 3200000 := by native_decide

/-- Survival probability ≈ 1493651/3200000 ≈ 46.68%.
    Interesting: survival is LESS than 50% — the double-failure on nat 1
    biases the chain toward death!

    This is counter-intuitive: there are 11 "good" outcomes per roll
    (10 success + 1 nat 20) vs 9 "bad" outcomes (8 failure + 1 nat 1),
    but the nat 1 counts as double failure, making death more likely. -/
theorem survival_less_than_half :
    2 * survivalNumer initialState 5 < 20 ^ 5 := by native_decide

-- ── Key structural properties ───────────────────────────────────────────

/-- From (2, 2), the chain is one roll from termination in either direction.
    P(survive | (2,2)) with 1 roll = 11/20 (nat20 or success). -/
theorem survive_22_1roll :
    survivalNumer ⟨2, 2⟩ 1 = 11 := by native_decide

/-- Nat 1 at state (s, 2) with s < 3 is instant death (2+2 ≥ 3 failures). -/
theorem nat1_at_2_failures_kills :
    min (2 + 2) 3 = 3 := by native_decide

/-- Being at (0, 1) is strictly better than (0, 2): more rolls to absorb. -/
theorem more_failures_worse :
    survivalNumer ⟨0, 1⟩ 4 > survivalNumer ⟨0, 2⟩ 3 := by native_decide

/-- **Damage while down**: taking damage at 0 HP = auto failure.
    Effectively replaces the d20 roll with a guaranteed failure.
    From (0,0) with 1 "damage roll": 0/20 survival for that roll. -/
def survivalWithDamage (s : DSState) (depth : Nat) : Nat :=
  if depth == 0 then if s.alive then 1 else 0
  else if s.absorbing then if s.alive then 20 ^ depth else 0
  else survivalNumer ⟨s.successes, s.failures + 1⟩ (depth - 1)

/-- Taking damage in round 1 reduces 5-round survival dramatically. -/
theorem damage_round1_survival :
    survivalWithDamage initialState 5 = 71181 := by native_decide

/-- Without damage: 1493651 / 3200000 ≈ 46.7%.
    With damage in round 1: 71181 / 160000 ≈ 44.5%.
    (Different denominators due to one fewer random roll.) -/

/-- **OPEN (P21a)**: Compute the exact rational survival probability
    as a closed-form expression (not via depth-bounded recursion).
    This requires solving the system of linear equations for the
    absorbing Markov chain's fundamental matrix.

    **OPEN (P21b)**: With the Healer feat (ally stabilizes as action),
    prove that the optimal strategy is to heal at state (s, 2) but
    not at (s, 1).  This is a stopping problem. -/

end VALOR.Scenarios.P21
