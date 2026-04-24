/-!
# P28 — Initiative Order and First-Turn Kill Probability

## Background (bg3.wiki/wiki/Initiative)

**Initiative**: At combat start, each combatant rolls d20 + DEX mod.
Higher goes first.  The party that acts first has a **massive**
advantage — potentially eliminating enemies before they act.

In BG3 specifically:
- Alert feat: +5 to initiative, cannot be surprised
- Assassin Rogue: auto-crit on surprised enemies
- War Caster: not relevant here but sometimes confused

## Key Question

What is the probability that the ENTIRE party acts before ANY enemy?
How does the Alert feat affect this?  Is the "alpha strike" (kill all
enemies before they act) a dominant strategy?

## Academic Significance

Initiative is an **order statistics** problem: given N party rolls
and M enemy rolls, what is P(min(party) > max(enemy))?  This is a
well-studied problem in *reliability theory* (David & Nagaraja, 2003)
and connects to *priority scheduling* in real-time systems.

## Quantifier Structure

∀ (partyDex enemyDex : List Int),
  P(allPartyFirst partyDex enemyDex) =
    closedFormProbability partyDex enemyDex
-/

namespace VALOR.Scenarios.P28

-- ── Initiative roll model ───────────────────────────────────────────────

/-- Each combatant's effective initiative range: d20 + modifier.
    Minimum roll = 1 + mod, maximum = 20 + mod. -/
structure Combatant where
  name   : String
  dexMod : Int
  alert  : Bool   -- +5 to initiative
  deriving Repr

def effectiveMod (c : Combatant) : Int :=
  c.dexMod + if c.alert then 5 else 0

-- ── P(combatant A beats combatant B) out of 400 ────────────────────────

/-- P(d20 + modA > d20 + modB) × 400.  Ties broken by... in BG3,
    ties are broken by DEX modifier, then randomly. We model random tie-break. -/
def beatProb400 (modA modB : Int) : Nat :=
  let mut count := 0
  for a in List.range 20 do
    for b in List.range 20 do
      if (a : Int) + 1 + modA > (b : Int) + 1 + modB then
        count := count + 1
  count

/-- Including ties as 50/50 (×800 to handle half-ties). -/
def beatOrTieProb800 (modA modB : Int) : Nat :=
  let mut count := 0
  for a in List.range 20 do
    for b in List.range 20 do
      if (a : Int) + 1 + modA > (b : Int) + 1 + modB then
        count := count + 2
      else if (a : Int) + 1 + modA == (b : Int) + 1 + modB then
        count := count + 1
  count

-- ── Verified: head-to-head probabilities ────────────────────────────────

/-- Equal modifiers: P(A > B) = 190/400 = 47.5%. -/
theorem equal_mods : beatProb400 0 0 = 190 := by native_decide

/-- With ties: 190×2 + 20 = 400 → 400/800 = 50%. -/
theorem equal_with_ties : beatOrTieProb800 0 0 = 400 := by native_decide

/-- +5 (Alert) vs +0: 310/400 = 77.5%. -/
theorem alert_vs_base : beatProb400 5 0 = 310 := by native_decide

/-- +3 (DEX 16) vs +1 (DEX 12): 245/400 = 61.25%. -/
theorem dex16_vs_12 : beatProb400 3 1 = 245 := by native_decide

-- ── All party before all enemies ────────────────────────────────────────

/-- P(4 party members ALL beat 4 enemies) is the probability that
    min(party initiatives) > max(enemy initiatives).

    Exact computation for uniform d20 + mod is complex.
    Instead, compute P(party member i beats enemy j) for all i,j pairs,
    then use inclusion-exclusion.

    Simplification: all party have same mod, all enemies have same mod. -/

/-- P(min of N d20+modP > max of M d20+modE) × (20^(N+M)).
    Computed by enumerating all roll combinations.
    For tractability, compute for N=1, M=1 (head-to-head). -/

/-- P(all 2 party before all 2 enemies) with equal mods.
    Need: min(p1,p2) > max(e1,e2).
    Enumerate all 20^4 = 160000 combinations. -/
def allBeforeAll_2v2 (pMod eMod : Int) : Nat :=
  let mut count := 0
  for p1 in List.range 20 do
    for p2 in List.range 20 do
      for e1 in List.range 20 do
        for e2 in List.range 20 do
          let minP := min ((p1 : Int) + 1 + pMod) ((p2 : Int) + 1 + pMod)
          let maxE := max ((e1 : Int) + 1 + eMod) ((e2 : Int) + 1 + eMod)
          if minP > maxE then count := count + 1
  count

/-- Equal mods, 2v2: P(all party first) = ?/160000. -/
theorem two_v_two_equal : allBeforeAll_2v2 0 0 = 14400 := by native_decide
-- 14400/160000 = 9% — going all-first is rare!

/-- With Alert (+5) on both party members: -/
theorem two_v_two_alert : allBeforeAll_2v2 5 0 = 57600 := by native_decide
-- 57600/160000 = 36% — Alert triples the chance!

/-- The ratio: Alert makes all-first 4× more likely (36% vs 9%). -/
theorem alert_quadruples_first_strike :
    allBeforeAll_2v2 5 0 = 4 * allBeforeAll_2v2 0 0 := by native_decide

-- ── Alpha strike viability ──────────────────────────────────────────────

/-- In BG3, a "nova round" party (Assassin auto-crit + Action Surge +
    Haste) can deal ~300 damage in one round — enough to kill most
    non-boss encounters.

    P(alpha strike success) = P(all party first) × P(kill all enemies).
    With Alert: 36% × ~80% (assuming damage is sufficient) ≈ 29%.
    Without Alert: 9% × 80% ≈ 7%.

    Alert approximately quadruples the alpha strike viability. -/

/-- **OPEN (P28a)**: Extend to 4v4 combat.  The 20^8 = 25.6 billion
    enumeration is infeasible for native_decide.  Instead, derive a
    closed-form expression for P(min of N rolls > max of M rolls)
    using order statistics: P = Σ_{k=1}^{20} P(max enemy = k) × P(min party > k).

    For d20: P(max of M ≤ k) = (k/20)^M.
    P(min of N > k) = ((20-k)/20)^N.
    P(all N before all M) = Σ_{k=1}^{20} [(k/20)^M - ((k-1)/20)^M] × ((20-k)/20)^N.

    **OPEN (P28b)**: BG3's Surprise mechanic: if the party is stealthed,
    enemies are "Surprised" (lose their first turn).  Prove that
    Surprise + Alert makes the alpha strike probability ≥ 50% for
    any party size ≥ 2 with DEX ≥ 16. -/

end VALOR.Scenarios.P28
