/-!
# P17 — Dual Wield vs Two-Handed vs Sword-and-Board: DPR Crossover Analysis

## Background (bg3.wiki)

Three melee weapon styles compete for damage per round (DPR):

1. **Two-Handed** (Greatsword 2d6 + STR + GWM):
   - One attack per action; Extra Attack → 2 attacks
   - Great Weapon Master: −5 to hit, +10 damage

2. **Dual Wield** (Shortsword 1d6 + STR each):
   - Main hand: 2 attacks (with Extra Attack)
   - Off-hand: 1 bonus action attack (adds STR mod in BG3!)
   - 3 total attacks per round

3. **Sword and Board** (Longsword 1d8 + STR + Dueling +2):
   - 2 attacks, lower damage but +2 AC from shield

## Key Question

At what STR modifier does Two-Handed overtake Dual Wield in max DPR?
What about expected DPR given a target AC?

## Academic Significance

This is a **parametric optimization** problem with integer constraints.
The crossover point depends on the ability modifier, which creates a
piecewise-linear DPR function.  We find exact crossover thresholds.

## Quantifier Structure

∃ (threshold : Nat), ∀ (strMod : Nat),
  strMod ≥ threshold →
  twoHandedDPR strMod > dualWieldDPR strMod
-/

namespace VALOR.Scenarios.P17

-- ── Damage formulas ─────────────────────────────────────────────────────

/-- Two-Handed: 2 attacks × (2d6 + STR + GWM_bonus).
    Max per hit = 12 + STR + bonus. -/
def twoHandedMaxDPR (strMod : Nat) (gwmBonus : Nat := 10) : Nat :=
  2 * (12 + strMod + gwmBonus)

/-- Two-Handed without GWM. -/
def twoHandedBaseMaxDPR (strMod : Nat) : Nat :=
  2 * (12 + strMod)

/-- Dual Wield: 3 attacks × (1d6 + STR).
    BG3-specific: offhand DOES add ability modifier (unlike 5e RAW). -/
def dualWieldMaxDPR (strMod : Nat) : Nat :=
  3 * (6 + strMod)

/-- Sword and Board: 2 attacks × (1d8 + STR + 2 Dueling). -/
def swordBoardMaxDPR (strMod : Nat) : Nat :=
  2 * (8 + strMod + 2)

-- ── Min DPR (all dice roll 1) ───────────────────────────────────────────

def twoHandedMinDPR (strMod : Nat) (gwmBonus : Nat := 10) : Nat :=
  2 * (2 + strMod + gwmBonus)

def dualWieldMinDPR (strMod : Nat) : Nat :=
  3 * (1 + strMod)

def swordBoardMinDPR (strMod : Nat) : Nat :=
  2 * (1 + strMod + 2)

-- ── Average DPR ×2 (to stay in Nat) ────────────────────────────────────

/-- Greatsword avg per die: 3.5, so 2d6 avg = 7.  ×2 → 14. -/
def twoHandedAvgX2 (strMod : Nat) (gwmBonus : Nat := 10) : Nat :=
  2 * (14 + strMod * 2 + gwmBonus * 2)

/-- Shortsword avg: 3.5.  ×2 → 7. -/
def dualWieldAvgX2 (strMod : Nat) : Nat :=
  3 * (7 + strMod * 2)

/-- Longsword avg: 4.5.  ×2 → 9. -/
def swordBoardAvgX2 (strMod : Nat) : Nat :=
  2 * (9 + strMod * 2 + 4)

-- ── Concrete comparisons ────────────────────────────────────────────────

/-- STR 16 (+3): Dual Wield = 3 × 9 = 27 max, TH = 2 × 25 = 50 max (with GWM). -/
theorem str3_max : dualWieldMaxDPR 3 = 27 ∧ twoHandedMaxDPR 3 = 50 := by native_decide

/-- STR 20 (+5): Dual Wield = 3 × 11 = 33 max, TH = 2 × 27 = 54 max. -/
theorem str5_max : dualWieldMaxDPR 5 = 33 ∧ twoHandedMaxDPR 5 = 54 := by native_decide

/-- Without GWM at STR 10 (+0): TH = 2 × 12 = 24, DW = 3 × 6 = 18. -/
theorem str0_no_gwm : twoHandedBaseMaxDPR 0 = 24 ∧ dualWieldMaxDPR 0 = 18 := by native_decide

/-- Two-Handed (with GWM) always beats Dual Wield in max DPR for STR ≤ 10.
    TH = 2(12 + s + 10) = 44 + 2s.  DW = 3(6 + s) = 18 + 3s.
    TH > DW iff 44 + 2s > 18 + 3s iff 26 > s.  So for s < 26 (always in BG3). -/
theorem two_handed_gwm_always_wins (strMod : Nat) (h : strMod ≤ 10) :
    twoHandedMaxDPR strMod > dualWieldMaxDPR strMod := by
  unfold twoHandedMaxDPR dualWieldMaxDPR; omega

/-- Without GWM: TH = 24 + 2s, DW = 18 + 3s.  TH > DW iff s < 6.
    At STR 22 (+6), Dual Wield ties! -/
theorem no_gwm_crossover_at_6 :
    twoHandedBaseMaxDPR 6 = dualWieldMaxDPR 6 := by native_decide

theorem no_gwm_th_wins_below_6 (s : Nat) (h : s < 6) :
    twoHandedBaseMaxDPR s > dualWieldMaxDPR s := by
  unfold twoHandedBaseMaxDPR dualWieldMaxDPR; omega

theorem no_gwm_dw_wins_above_6 (s : Nat) (h : s > 6) :
    dualWieldMaxDPR s > twoHandedBaseMaxDPR s := by
  unfold twoHandedBaseMaxDPR dualWieldMaxDPR; omega

-- ── Expected hit probability and true DPR ───────────────────────────────

/-- Hit probability out of 20 (ignoring nat 1/20 for simplicity).
    Need d20 + toHit ≥ targetAC. -/
def hitProb20 (toHitBonus targetAC : Nat) : Nat :=
  let needed := if targetAC > toHitBonus then targetAC - toHitBonus else 1
  if needed > 20 then 0
  else if needed < 1 then 20
  else 21 - needed

/-- GWM penalty: −5 to hit.  Against AC 16, +8 to hit:
    Normal: need 8, P = 13/20 = 65%.
    GWM:    need 13, P = 8/20 = 40%. -/
theorem gwm_hit_penalty :
    hitProb20 8 16 = 13 ∧ hitProb20 3 16 = 8 := by native_decide

/-! ## Open problems

**P17a.** Compute the full expected DPR as a function of `(STR, targetAC,
weaponEnchantment)` and find the exact surface where TH-GWM = DW in
expected damage.  Requires modelling hit probability × expected damage per
hit for each attack.

**P17b.** With Berserker Barbarian's Frenzy (extra bonus-action attack),
Dual Wield loses its 3rd-attack advantage.  Prove that Frenzy + Two-Handed
strictly dominates Dual Wield for all STR ≥ 3.
-/

end VALOR.Scenarios.P17
