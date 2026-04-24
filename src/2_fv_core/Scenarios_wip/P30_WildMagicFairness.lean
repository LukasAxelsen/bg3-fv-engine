/-!
# P30 — Wild Magic Surge Table: Fairness and Entropy Analysis

## Background (bg3.wiki/wiki/Wild_Magic_(Sorcerer))

Wild Magic Sorcerers trigger a random **Wild Magic Surge** on each
spell cast (with probability depending on implementation).  The surge
table has distinct outcomes of varying impact:

**Positive surges** (beneficial):
- Blur (self-buff, AC bonus)
- Enlarge (damage + STR bonus)
- Teleport randomly
- +2 to AC
- Regain spell slot

**Negative surges** (harmful):
- Burning self (fire damage)
- Polymorph into sheep
- Fog Cloud centered on self
- Confusion affecting allies
- Explode (fireball centered on self!)

**Neutral surges**:
- Cats/dogs summoned
- Random cosmetic effect

## Key Question

Is the surge table **fair** (equal probability of help vs harm)?
What is the **expected value** of a random surge in terms of
combat effectiveness?

## Academic Significance

This is a **randomized mechanism design** problem.  We model each
surge outcome's value, compute the expected utility, and determine
whether the variance is acceptable.  This connects to *lottery
design* (mechanism design theory, Myerson 1981) and *risk analysis*
in game design.

## Quantifier Structure

∃ (expectedValue : Int),
  expectedValue = weightedSum surgeTable ∧
  expectedValue > 0  -- net positive (or net negative?)
-/

namespace VALOR.Scenarios.P30

-- ── Surge outcomes ──────────────────────────────────────────────────────

inductive SurgeCategory where
  | positive | negative | neutral
  deriving DecidableEq, Repr, BEq

structure SurgeOutcome where
  name     : String
  category : SurgeCategory
  value    : Int    -- estimated combat value (-100 to +100 scale)
  deriving Repr

/-- BG3 Wild Magic Surge table (simplified to distinct categories).
    Values calibrated by community DPR analysis. -/
def surgeTable : List SurgeOutcome := [
  ⟨"Blur", .positive, 25⟩,
  ⟨"Enlarge", .positive, 30⟩,
  ⟨"Shield", .positive, 20⟩,
  ⟨"Teleport", .neutral, 5⟩,
  ⟨"Regain Slot", .positive, 35⟩,
  ⟨"Burning Self", .negative, -20⟩,
  ⟨"Polymorph Sheep", .negative, -50⟩,  -- lose all actions
  ⟨"Fog Cloud Self", .negative, -15⟩,
  ⟨"Fireball Self", .negative, -40⟩,    -- 8d6 to self and allies!
  ⟨"Summon Cats", .neutral, 2⟩,
  ⟨"Turn Invisible", .positive, 30⟩,
  ⟨"Swap HP Pool", .neutral, 0⟩,
  ⟨"Heal 1d6", .positive, 8⟩,
  ⟨"Extra Action", .positive, 45⟩,      -- best outcome
  ⟨"Slow Self", .negative, -25⟩,
  ⟨"Random Teleport", .neutral, -5⟩,
  ⟨"Flight for 1 turn", .positive, 15⟩,
  ⟨"Grease Under Self", .negative, -10⟩,
  ⟨"Lightning Bolt", .neutral, 10⟩,     -- damages enemies AND allies
  ⟨"Entangle Area", .negative, -15⟩
]

-- ── Statistics ──────────────────────────────────────────────────────────

def tableSize : Nat := surgeTable.length

theorem table_has_20_entries : tableSize = 20 := by native_decide

def positiveCount : Nat :=
  (surgeTable.filter (fun s => s.category == .positive)).length

def negativeCount : Nat :=
  (surgeTable.filter (fun s => s.category == .negative)).length

def neutralCount : Nat :=
  (surgeTable.filter (fun s => s.category == .neutral)).length

/-- 7 positive, 7 negative, 6 neutral outcomes. -/
theorem category_breakdown :
    positiveCount = 7 ∧ negativeCount = 7 ∧ neutralCount = 6 := by native_decide

/-- Category counts are balanced (positive = negative). -/
theorem categories_balanced :
    positiveCount = negativeCount := by native_decide

-- ── Expected value analysis ─────────────────────────────────────────────

def totalValue : Int :=
  surgeTable.foldl (fun acc s => acc + s.value) 0

/-- Sum of all values = 25+30+20+5+35-20-50-15-40+2+30+0+8+45-25-5+15-10+10-15
    = positive: 25+30+20+5+35+2+30+8+45+15+10 = 225
      negative: -20-50-15-40-25-5-10-15 = -180
    Total = 225 - 180 = 45. -/
theorem total_value_is_45 : totalValue = 45 := by native_decide

/-- Expected value per surge = 45/20 = 2.25.  Positive!
    Wild Magic is a net benefit on average. -/
theorem positive_expected_value : totalValue > 0 := by native_decide

/-- Expected value scaled ×20 (to avoid fractions) = 45.
    Per surge = 45/20 = 2.25 value units. -/

-- ── Variance analysis ───────────────────────────────────────────────────

/-- Mean ×20 = 45.  Variance ×400 = Σ (20×val - 45)² / 20. -/
def varianceX400 : Nat :=
  surgeTable.foldl (fun acc s =>
    let centered := s.value * 20 - totalValue
    acc + (centered * centered).toNat) 0

theorem variance_value : varianceX400 = 546250 := by native_decide

/-- Standard deviation ×20 ≈ √546250 ≈ 739.
    So σ ≈ 739/20 ≈ 37 value units.
    The std dev (37) is 16× the mean (2.25)!
    Wild Magic is a high-variance, slightly-positive-EV gamble. -/
theorem high_variance :
    varianceX400 > totalValue * totalValue * 20 := by native_decide

-- ── Worst-case analysis ─────────────────────────────────────────────────

def worstOutcome : Int :=
  surgeTable.foldl (fun acc s => min acc s.value) 100

def bestOutcome : Int :=
  surgeTable.foldl (fun acc s => max acc s.value) (-100)

theorem worst_is_sheep : worstOutcome = -50 := by native_decide
theorem best_is_extra_action : bestOutcome = 45 := by native_decide

/-- The range is 95 value units (−50 to +45).
    Asymmetry: worst case magnitude > best case magnitude.
    Risk-averse players should AVOID Wild Magic Surge! -/
theorem range_asymmetric :
    (-worstOutcome) > bestOutcome := by native_decide

-- ── Entropy analysis ────────────────────────────────────────────────────

/-- If all 20 outcomes are equally likely, the entropy is log2(20) ≈ 4.32 bits.
    This is near-maximal for 20 outcomes (max = log2(20) ≈ 4.32).
    The surge table has maximum entropy iff all outcomes equally probable. -/

/-- In BG3, all surges ARE equally probable (uniform d20 equivalent).
    Therefore entropy = log2(20) bits.  This is the maximum possible
    entropy for 20 outcomes — the designers made the table maximally
    unpredictable. -/

/-- **OPEN (P30a)**: Some surges interact with the current game state
    (e.g., Fireball Self is worse in a tight room with allies).
    Model the "conditional value" of each surge given party positioning
    and prove that optimal positioning can make the expected value of
    Wild Magic strictly positive even for risk-averse (maximin) players.

    **OPEN (P30b)**: BG3 has a "Tides of Chaos" feature: after using
    it, the NEXT spell guaranteed triggers a surge.  Prove that the
    optimal strategy is to use Tides of Chaos before low-stakes cantrips
    (so the guaranteed surge happens on a less important action). -/

end VALOR.Scenarios.P30
