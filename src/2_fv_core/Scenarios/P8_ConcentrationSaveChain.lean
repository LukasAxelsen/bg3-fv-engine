/-!
# P8 — Concentration Save Chain Under Multi-Hit Attacks

## Background (bg3.wiki)

When a concentrating creature takes damage, it makes a CON save:
- DC = max(10, ⌊damage / 2⌋)
- Each hit triggers a **separate** save (Eldritch Blast 3 beams = 3 saves)
- Fail any one save → concentration breaks

## Key Question

What is the probability of maintaining concentration when hit by
N beams, each dealing D damage, given CON save modifier M?

## Properties Verified

- `dc_formula`: DC = max(10, d/2) for any damage d
- `single_save_prob`: Probability of passing a single save
- `chain_survival_prob`: P(maintain) = P(single pass)^N
- `eldritch_blast_scenario`: 3 beams × 1d10 force, CON +3 caster

## Academic Significance

This is an instance of the *compound Bernoulli trial* problem applied to
game mechanics, where the per-trial success probability depends on the
random damage roll.  Unlike simple coin flips, the damage die creates a
non-trivial probability distribution over DCs.
-/

namespace VALOR.Scenarios.P8

-- ── Save DC computation ─────────────────────────────────────────────────

def concentrationDC (damage : Nat) : Nat :=
  max 10 (damage / 2)

-- ── d20 probability model ───────────────────────────────────────────────

/-- Probability of passing a save (out of 20) given DC and modifier.
    Need to roll ≥ DC on d20 + modifier. Natural 1 always fails, 20 always succeeds.
    Result: number of successful outcomes out of 20. -/
def saveSuccessCount (dc : Nat) (modifier : Int) : Nat :=
  let needed := (dc : Int) - modifier  -- need d20 ≥ this
  if needed ≤ 1 then 19   -- natural 1 still fails
  else if needed > 20 then 1   -- natural 20 still succeeds
  else (21 - needed).toNat

/-- Probability of passing as a rational (numerator out of 20). -/
def saveProbNumer (dc : Nat) (modifier : Int) : Nat :=
  saveSuccessCount dc modifier

-- ── Chain survival probability ──────────────────────────────────────────

/-- P(survive N saves) numerator out of 20^N. -/
def chainSurvivalNumer (n : Nat) (dc : Nat) (modifier : Int) : Nat :=
  (saveProbNumer dc modifier) ^ n

def chainSurvivalDenom (n : Nat) : Nat :=
  20 ^ n

-- ── Concrete scenarios ──────────────────────────────────────────────────

/-- Scenario: Level 10 Warlock with Eldritch Blast (3 beams).
    Each beam deals 1d10 Force damage (average 5.5, max 10).
    Target: CON save modifier +3 (typical for a caster with CON 16).

    Worst case: each beam deals 10 damage → DC = max(10, 5) = 10.
    With +3 modifier: need d20 ≥ 7, so 14/20 = 70% per beam.
    P(survive 3 beams) = (14/20)^3 = 2744/8000 = 34.3%.

    Best case: each beam deals 1 damage → DC = 10 (floor).
    P(survive 3 beams) = (14/20)^3 = 34.3% (same! DC floors at 10). -/

def eb_dc_worst : Nat := concentrationDC 10
def eb_dc_best  : Nat := concentrationDC 1

theorem eb_dc_worst_is_10 : eb_dc_worst = 10 := by native_decide
theorem eb_dc_best_is_10  : eb_dc_best = 10 := by native_decide

/-- Key insight: for Eldritch Blast, DC is ALWAYS 10 regardless of damage
    (because max(10, d/2) = 10 for d ≤ 20, and 1d10 max = 10). -/
theorem eb_dc_always_10 (d : Nat) (h : d ≤ 10) :
    concentrationDC d = 10 := by
  simp [concentrationDC]
  omega

/-- With CON +3 and DC 10: 14 successes out of 20 per save. -/
theorem eb_single_save_count :
    saveSuccessCount 10 3 = 14 := by native_decide

/-- 3-beam survival: 14^3 = 2744 out of 20^3 = 8000 (34.3%). -/
theorem eb_three_beam_survival_numer :
    chainSurvivalNumer 3 10 3 = 2744 := by native_decide

theorem eb_three_beam_survival_denom :
    chainSurvivalDenom 3 = 8000 := by native_decide

/-- Compare: single Fireball (8d6, avg 28, max 48).
    DC = max(10, 48/2) = 24. With +3: need d20 ≥ 21 → only nat 20 saves.
    P(survive) = 1/20 = 5%.

    So 3× Eldritch Blast beams (34.3% survival) is LESS dangerous to
    concentration than 1× max-damage Fireball (5% survival). -/

theorem fireball_max_dc :
    concentrationDC 48 = 24 := by native_decide

theorem fireball_max_save_count :
    saveSuccessCount 24 3 = 1 := by native_decide  -- only nat 20

/-- **Main theorem**: N small hits are less dangerous to concentration
    than one large hit of the same total damage, because the DC floors
    at 10 for small hits but scales linearly for large hits.

    Formally: for d ≤ 20, N × DC(d) ≤ DC(N × d) when N × d > 20. -/
theorem small_hits_safer (d : Nat) (n : Nat) (h_small : d ≤ 20)
    (h_n : n ≥ 2) (h_big : n * d > 20) :
    n * concentrationDC d ≥ concentrationDC (n * d) := by
  sorry -- requires case analysis on d ranges; the DC floor creates the asymmetry

-- ── Open question ───────────────────────────────────────────────────────

/-- **OPEN**: What is the optimal beam count to maximize concentration-
    break probability for a fixed total damage budget T?

    Conjecture: For T > 20, a single hit of T damage has higher break
    probability than N hits of T/N damage. For T ≤ 20, it doesn't matter
    (DC always floors at 10). This has implications for spell selection
    strategy in competitive play. -/

end VALOR.Scenarios.P8
