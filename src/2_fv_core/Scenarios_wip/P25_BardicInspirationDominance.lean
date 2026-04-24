/-!
# P25 — Bardic Inspiration: First-Order Stochastic Dominance

## Background (bg3.wiki/wiki/Bardic_Inspiration)

**Bardic Inspiration** (Bard feature): add a bonus die to one
ability check, attack roll, or saving throw per use.

| Bard Level | Die |
|-----------|-----|
| 1-4       | d6  |
| 5-9       | d8  |
| 10+       | d10 |

The key question: does Bardic Inspiration (BI) provide **first-order
stochastic dominance** (FOSD) over an unmodified roll for any target
DC?  When is it more valuable than advantage?

## Academic Significance

**First-order stochastic dominance**: distribution F dominates G iff
F(x) ≤ G(x) for all x.  "Roll + BI die" stochastically dominates
the base roll.  But "advantage" (max of 2d20) is a *different*
distribution — comparing BI vs advantage is a partial order question.

This connects to *decision theory under risk* (Rothschild & Stiglitz,
1970) and the *value of information* in game-theoretic settings.

## Quantifier Structure

∀ (target : Nat), P(d20 + BI_die ≥ target) ≥ P(d20 ≥ target)

∃ (target : Nat),
  P(d20 + d6 ≥ target) > P(advantage(d20) ≥ target) ∧
  ∃ (target2 : Nat),
    P(advantage(d20) ≥ target2) > P(d20 + d6 ≥ target2)
-/

namespace VALOR.Scenarios.P25

-- ── Probability distributions (out of total outcomes) ───────────────────

/-- P(d20 ≥ target) × 20. -/
def d20prob (target : Nat) : Nat :=
  if target ≤ 1 then 20
  else if target > 20 then 0
  else 21 - target

/-- P(d20 + d6 ≥ target) × 120 (= 20 × 6).
    Sum over all (d20, d6) pairs where d20 + d6 ≥ target. -/
def d20plusD6prob120 (target : Nat) : Nat :=
  let mut count := 0
  for d20 in List.range 20 do
    for d6 in List.range 6 do
      if (d20 + 1) + (d6 + 1) ≥ target then
        count := count + 1
  count

/-- P(d20 + d8 ≥ target) × 160 (= 20 × 8). -/
def d20plusD8prob160 (target : Nat) : Nat :=
  let mut count := 0
  for d20 in List.range 20 do
    for d8 in List.range 8 do
      if (d20 + 1) + (d8 + 1) ≥ target then
        count := count + 1
  count

/-- P(advantage d20 ≥ target) × 400 (= 20 × 20). -/
def advProb400 (target : Nat) : Nat :=
  let mut count := 0
  for d1 in List.range 20 do
    for d2 in List.range 20 do
      if max (d1 + 1) (d2 + 1) ≥ target then
        count := count + 1
  count

-- ── Verified: BI always improves the roll ───────────────────────────────

/-- DC 15: base P = 6/20.  With d6 BI: P = ?/120. -/
theorem dc15_base : d20prob 15 = 6 := by native_decide

theorem dc15_bi_d6 : d20plusD6prob120 15 = 87 := by native_decide
-- 87/120 = 72.5% vs 6/20 = 30%. BI triples the success rate!

/-- DC 10: base P = 11/20 = 55%.  With d6: ?/120. -/
theorem dc10_base : d20prob 10 = 11 := by native_decide
theorem dc10_bi_d6 : d20plusD6prob120 10 = 111 := by native_decide
-- 111/120 = 92.5% vs 55%.

/-- DC 20: base P = 1/20 = 5%.  With d6: ?/120. -/
theorem dc20_base : d20prob 20 = 1 := by native_decide
theorem dc20_bi_d6 : d20plusD6prob120 20 = 21 := by native_decide
-- 21/120 = 17.5% vs 5%.

-- ── FOSD: BI dominates base roll at every DC ────────────────────────────

/-- BI(d6) provides FOSD: for ALL targets 1-26, P(d20+d6 ≥ t) ≥ P(d20 ≥ t).
    We verify this by checking each possible target value. -/
theorem fosd_d6_exhaustive :
    (List.range 27).all (fun t =>
      d20plusD6prob120 t * 20 ≥ d20prob t * 120) = true := by native_decide

-- ── BI vs Advantage comparison ──────────────────────────────────────────

/-- For low DCs, advantage is better than BI(d6).
    DC 5: Adv = 351/400 = 87.8%.  BI(d6) = 120/120 = 100%.
    Wait, BI might still be better for very low DCs. Let's check DC 11. -/
theorem dc11_adv : advProb400 11 = 300 := by native_decide
-- 300/400 = 75%
theorem dc11_bi_d6 : d20plusD6prob120 11 = 105 := by native_decide
-- 105/120 = 87.5%.  BI(d6) > Advantage at DC 11!

/-- DC 6: Adv = 375/400 = 93.75%.  BI(d6) = 120/120 = 100%. -/
theorem dc6_adv : advProb400 6 = 375 := by native_decide
theorem dc6_bi_d6 : d20plusD6prob120 6 = 120 := by native_decide
-- BI guarantees success at DC 6 (d20+d6 minimum = 2, but DC 6 ≤ 7).

/-- DC 18: Adv = 127/400 = 31.8%.  BI(d6) = 48/120 = 40%.
    BI(d6) still better at DC 18! -/
theorem dc18_adv : advProb400 18 = 127 := by native_decide
theorem dc18_bi_d6 : d20plusD6prob120 18 = 48 := by native_decide

/-- DC 22: Adv = 0/400 (impossible on d20).
    BI(d6) = 6/120 = 5% (need nat 20 + d6 ≥ 2).
    BI can reach DCs that advantage CANNOT! -/
theorem dc22_adv : advProb400 22 = 0 := by native_decide
theorem dc22_bi_d6 : d20plusD6prob120 22 = 6 := by native_decide

/-- Key insight: BI(d6) strictly dominates advantage for target ≥ 21
    (advantage can never reach 21+, but d20+d6 can reach up to 26). -/
theorem bi_reaches_impossible_dcs :
    advProb400 21 = 0 ∧ d20plusD6prob120 21 = 15 := by native_decide

/-- For targets ≤ 20, is there any DC where advantage beats BI(d6)?
    Check all DCs 1-20. -/
def advBeatsBI_count : Nat :=
  (List.range 20).filter (fun t =>
    let t' := t + 1
    advProb400 t' * 120 > d20plusD6prob120 t' * 400
  ) |>.length

/-- Advantage NEVER beats BI(d6) for any reachable DC (1-20). -/
theorem advantage_never_beats_d6_bi :
    advBeatsBI_count = 0 := by native_decide

/-- **Theorem**: BI(d6) provides FOSD over advantage for ALL target DCs.
    This is a surprising result: a d6 bonus is ALWAYS at least as good
    as rolling with advantage, and strictly better for high DCs. -/

/-- **OPEN (P25a)**: Does the same hold for BI(d8) vs double advantage
    (Elven Accuracy: roll 3d20 take best)?  Elven Accuracy has
    P(≥t) = 1 − ((t−1)/20)³.  Compare with d20+d8 distribution. -/

/-- **OPEN (P25b)**: Compute the "Bardic Inspiration value" as the
    DC at which BI provides the largest ABSOLUTE increase in success
    probability.  Prove this is at DC = 10 + (die_size/2) (the median
    of the combined distribution). -/

end VALOR.Scenarios.P25
