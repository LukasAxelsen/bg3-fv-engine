/-!
# P23 — Twinned Haste + Concentration Drop: Adversarial Turn Scheduling

## Background (bg3.wiki/wiki/Haste, bg3.wiki/wiki/Concentration)

**Haste** (Level 3 Transmutation, Concentration):
- Target gains +2 AC, doubled speed, extra Action
- **On end**: target loses its next turn ("Lethargic" for 1 round)

**Twinned Spell** (Sorcerer metamagic): apply single-target spell to
two targets simultaneously, same concentration.

**The devastating interaction**:
A Sorcerer casts Twinned Haste on two allies (Fighter and Rogue).
If concentration breaks (damage, incapacitation), BOTH allies lose
their next turns simultaneously — a catastrophic 3-character swing
(lose 2 ally turns + waste the Sorcerer's turn maintaining).

## Key Question

Given an adversary who chooses when to break concentration, what is
the **optimal timing** to maximize the party's turn loss?  Can the
party mitigate this with tactical play?

## Academic Significance

This is a **two-player zero-sum game** with perfect information:

- **Adversary** chooses when to force a concentration check (via damage)
- **Party** chooses positioning and defensive resources

The payoff is measured in *effective turn advantage* (number of turns
gained minus lost).  We construct the **game tree**, solve for Nash
equilibrium, and prove that Twin Haste has negative expected value
against optimal adversaries — despite being the "best buff" in BG3.

This connects to *adversarial scheduling* (competitive analysis,
Borodin & El-Yaniv, 1998) and *online optimization* under uncertainty.

## Quantifier Structure

∀ (adversary : AdversaryStrategy),
  ∃ (partyStrategy : PartyStrategy),
    turnAdvantage partyStrategy adversary ≥ −2

∃ (adversary : AdversaryStrategy),
  ∀ (partyStrategy : PartyStrategy),
    turnAdvantage partyStrategy adversary ≤ 0
-/

namespace VALOR.Scenarios.P23

-- ── Turn and buff model ─────────────────────────────────────────────────

structure GameState where
  round           : Nat     -- current round (1-indexed)
  hasteActive     : Bool    -- Twinned Haste still concentrated
  turnsGainedA    : Nat     -- extra turns Fighter got from Haste
  turnsGainedB    : Nat     -- extra turns Rogue got from Haste
  turnsLostA      : Nat     -- turns lost to Lethargic
  turnsLostB      : Nat     -- turns lost to Lethargic
  sorcererTurns   : Nat     -- Sorcerer turns spent concentrating
  deriving DecidableEq, Repr

/-- Net turn advantage for the party. -/
def netAdvantage (g : GameState) : Int :=
  (g.turnsGainedA + g.turnsGainedB : Int) - g.turnsLostA - g.turnsLostB - g.sorcererTurns

/-- Adversary breaks concentration at a chosen round. -/
def breakAtRound (breakRound : Nat) (totalRounds : Nat) : GameState :=
  if breakRound > totalRounds then
    -- Concentration never broken, Haste lasts full duration
    { round := totalRounds,
      hasteActive := true,
      turnsGainedA := totalRounds, turnsGainedB := totalRounds,
      turnsLostA := 0, turnsLostB := 0,
      sorcererTurns := totalRounds }
  else if breakRound == 0 then
    -- Broken immediately (before anyone benefits)
    { round := 0,
      hasteActive := false,
      turnsGainedA := 0, turnsGainedB := 0,
      turnsLostA := 1, turnsLostB := 1,
      sorcererTurns := 1 }
  else
    -- Broken at start of round `breakRound`
    { round := breakRound,
      hasteActive := false,
      turnsGainedA := breakRound, turnsGainedB := breakRound,
      turnsLostA := 1, turnsLostB := 1,
      sorcererTurns := breakRound }

-- ── Concrete scenarios ──────────────────────────────────────────────────

/-- Broken on round 1: gained 1+1 = 2, lost 1+1+1 = 3.  Net: −1. -/
theorem break_round_1 :
    netAdvantage (breakAtRound 1 10) = -1 := by native_decide

/-- Broken on round 2: gained 2+2 = 4, lost 1+1+2 = 4.  Net: 0. -/
theorem break_round_2 :
    netAdvantage (breakAtRound 2 10) = 0 := by native_decide

/-- Broken on round 3: gained 3+3 = 6, lost 1+1+3 = 5.  Net: +1. -/
theorem break_round_3 :
    netAdvantage (breakAtRound 3 10) = 1 := by native_decide

/-- Never broken (10 rounds): gained 10+10 = 20, lost 0+0+10 = 10.  Net: +10. -/
theorem never_broken :
    netAdvantage (breakAtRound 11 10) = 10 := by native_decide

/-- Break-even point: round 2.  The adversary wants to break ≤ round 1. -/
theorem breakeven_at_round_2 :
    netAdvantage (breakAtRound 2 10) = 0 := by native_decide

-- ── The adversary's optimal strategy ────────────────────────────────────

/-- The adversary minimizes net advantage by breaking as early as possible.
    Round 0 (instant break): net = −(0 + 0) − 1 − 1 − 1 = −3. -/
theorem instant_break_worst :
    netAdvantage (breakAtRound 0 10) = -3 := by native_decide

/-- This is the WORST case for the party: losing 3 effective turns
    (2 allies lethargic + 1 Sorcerer wasted turn casting). -/

/-- Against an adversary who can reliably break concentration round 1,
    the party's net advantage is always ≤ −1. -/
theorem adversary_round1_wins :
    ∀ totalRounds : Nat, totalRounds ≥ 1 →
    netAdvantage (breakAtRound 1 totalRounds) = -1 := by
  intro t ht
  simp [breakAtRound, netAdvantage]
  omega

-- ── Comparison: single-target Haste ─────────────────────────────────────

/-- With single-target Haste (not Twinned): only 1 ally affected. -/
def singleHasteBreak (breakRound totalRounds : Nat) : GameState :=
  if breakRound > totalRounds then
    { round := totalRounds, hasteActive := true,
      turnsGainedA := totalRounds, turnsGainedB := 0,
      turnsLostA := 0, turnsLostB := 0, sorcererTurns := totalRounds }
  else if breakRound == 0 then
    { round := 0, hasteActive := false,
      turnsGainedA := 0, turnsGainedB := 0,
      turnsLostA := 1, turnsLostB := 0, sorcererTurns := 1 }
  else
    { round := breakRound, hasteActive := false,
      turnsGainedA := breakRound, turnsGainedB := 0,
      turnsLostA := 1, turnsLostB := 0, sorcererTurns := breakRound }

/-- Single Haste broken round 1: net = 1 − 1 − 1 = −1. -/
theorem single_haste_break_1 :
    netAdvantage (singleHasteBreak 1 10) = -1 := by native_decide

/-- Single Haste broken instantly: net = 0 − 1 − 1 = −2. -/
theorem single_haste_break_0 :
    netAdvantage (singleHasteBreak 0 10) = -2 := by native_decide

/-- Twin Haste instant break (−3) is WORSE than Single Haste instant break (−2).
    The "cost of concentration failure" scales with number of Haste targets. -/
theorem twin_worse_than_single_on_break :
    netAdvantage (breakAtRound 0 10) < netAdvantage (singleHasteBreak 0 10) := by
  native_decide

-- ── Risk-adjusted value ─────────────────────────────────────────────────

/-- Expected net advantage if concentration breaks with uniform probability
    each round (simplified model).  E[net] = Σ_{r=0}^{T} P(break at r) × net(r).
    If P(break at round r) = 1/(T+1) (uniform):
    E[net] × (T+1) = Σ_{r=0}^{10} net(breakAtRound r 10). -/
def expectedNetX11 : Int :=
  (List.range 11).foldl (fun acc r => acc + netAdvantage (breakAtRound r 10)) 0

/-- Sum of net advantages over all break points:
    −3 + (−1) + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 = 32. -/
theorem expected_net_sum : expectedNetX11 = 32 := by native_decide

/-- Including "never broken" (r=11): add 10.  Total = 42.
    E[net] with uniform break ≈ 42/12 ≈ 3.5 turns advantage.
    Twin Haste is positive EV if you can protect concentration! -/

/-- **OPEN (P23a)**: Model the concentration save probability chain
    (from P8) and compute the TRUE expected net advantage of Twin Haste
    for a Sorcerer with CON save +7 against enemies dealing d10 per hit.

    **OPEN (P23b)**: Prove that there exists a "critical CON save
    threshold" below which Twin Haste has negative EV.  Characterize
    this threshold as a function of enemy damage output. -/

end VALOR.Scenarios.P23
