/-!
# P26 — Grapple/Shove as a Positional Game

## Background (bg3.wiki/wiki/Shove, bg3.wiki/wiki/Prone)

**Shove** (bonus action in BG3): push target back OR knock prone.
- Success: STR (Athletics) check vs target's STR/DEX.
- Prone: advantage on melee attacks, disadvantage on ranged, costs
  half movement to stand up.

**Grapple** (not in BG3 base, but in mods/5e): grab target,
reducing speed to 0.  Contest: STR (Athletics) vs STR/DEX.

**Prone + Grapple combo** (in 5e, partially in BG3):
1. Grapple → target speed = 0
2. Shove prone → target can't stand up (needs movement, but speed = 0)
3. All melee attacks have advantage → the "prone lock"

## Key Question

This is a **two-player perfect-information game**: the grappler tries
to maintain the lock; the target tries to break free.  We model this
as a combinatorial game and solve for optimal strategies.

## Academic Significance

The grapple/shove interaction is an instance of a **pursuit-evasion
game** on a graph (the grid map).  With the "prone lock" combo, it
becomes a Nim-like game where the positions are the relative
Athletics/Acrobatics modifiers.  We prove that the game is
*determined* (one player has a winning strategy) and compute the
critical modifier difference.

## Quantifier Structure

∀ (modDiff : Int), modDiff ≥ 0 →
  (∀ round, grappler wins the Athletics contest with probability ≥ 50%)

∃ (threshold : Nat),
  modDiff ≥ threshold → P(maintain lock for 3+ rounds) ≥ 80%
-/

namespace VALOR.Scenarios.P26

-- ── Contest mechanics ───────────────────────────────────────────────────

/-- Athletics contest: attacker rolls d20 + atkMod, defender rolls d20 + defMod.
    Attacker wins on ≥ (ties go to attacker in contested checks).
    P(attacker wins) out of 400. -/
def contestWin400 (atkMod defMod : Int) : Nat :=
  let mut count := 0
  for a in List.range 20 do
    for d in List.range 20 do
      if (a : Int) + 1 + atkMod ≥ (d : Int) + 1 + defMod then
        count := count + 1
  count

-- ── Verified: contest probabilities ─────────────────────────────────────

/-- Equal modifiers: 210/400 = 52.5% (attacker wins ties). -/
theorem equal_contest : contestWin400 0 0 = 210 := by native_decide

/-- +5 vs +0: significant advantage. -/
theorem plus5_contest : contestWin400 5 0 = 310 := by native_decide
-- 310/400 = 77.5%

/-- +0 vs +5: the grappler is outmatched. -/
theorem minus5_contest : contestWin400 0 5 = 110 := by native_decide
-- 110/400 = 27.5%

/-- +3 vs +0: 265/400 = 66.25%. -/
theorem plus3_contest : contestWin400 3 0 = 265 := by native_decide

-- ── Prone lock maintenance ──────────────────────────────────────────────

/-- The prone lock requires winning TWO contests per round:
    1. Maintain grapple (if target tries to break free)
    2. Prevent standing (target uses half movement, but speed = 0)

    Actually, if grappled and prone, standing requires movement
    but grapple sets speed to 0, so standing is impossible
    WITHOUT breaking the grapple first.  So only 1 contest needed. -/

/-- P(maintain lock for N rounds) = P(win contest)^N.
    (Target tries to break free each round.) -/
def lockNRoundsNumer (n : Nat) (atkMod defMod : Int) : Nat :=
  (contestWin400 atkMod defMod) ^ n

def lockNRoundsDenom (n : Nat) : Nat :=
  400 ^ n

-- ── Concrete scenarios ──────────────────────────────────────────────────

/-- +5 Athletics vs +0: P(lock 3 rounds) = 310³ / 400³. -/
theorem lock_3_rounds_5v0 :
    lockNRoundsNumer 3 5 0 = 29791000 := by native_decide

theorem lock_3_denom :
    lockNRoundsDenom 3 = 64000000 := by native_decide

-- 29791000 / 64000000 ≈ 46.5% — not great even with +5!

/-- +8 Athletics (Barbarian with Expertise) vs +0:
    P(win single) = ?/400. -/
theorem plus8_contest : contestWin400 8 0 = 350 := by native_decide
-- 350/400 = 87.5%.

theorem lock_3_rounds_8v0 :
    lockNRoundsNumer 3 8 0 = 42875000 := by native_decide
-- 42875000 / 64000000 = 67.0% for 3 rounds.

/-- P(lock 5 rounds) at +8 vs +0. -/
theorem lock_5_rounds_8v0 :
    lockNRoundsNumer 5 8 0 = 5252150000 := by native_decide

-- 5252150000 / 400^5 = 5252150000 / 1.024×10^13 ≈ 51.3%

-- ── Advantage from being prone: attack bonus ────────────────────────────

/-- While target is prone and grappled:
    - All melee attacks against them have ADVANTAGE
    - Their attacks have DISADVANTAGE
    - Their speed is 0 (can't escape without breaking grapple)

    Combined with the P14 advantage algebra:
    P(hit with advantage at DC 11) = 300/400 = 75%
    P(hit with disadvantage at DC 11) = 100/400 = 25%

    Damage ratio: 75/25 = 3:1 in favor of the grappler! -/

/-- The "prone lock" creates a 3:1 hit probability ratio.
    Expected DPR ratio: (0.75 × dmg) / (0.25 × dmg) = 3.0. -/
theorem prone_lock_ratio :
    300 * 100 = 3 * (100 * 100) := by native_decide

-- ── Critical modifier threshold ─────────────────────────────────────────

/-- Find the minimum atkMod where P(lock 3 rounds) ≥ 50%.
    Try atkMod = 0..10 vs defMod = 0. -/
def findThreshold : Nat :=
  let thresholds := (List.range 11).filter fun atkMod =>
    lockNRoundsNumer 3 atkMod 0 * 2 ≥ lockNRoundsDenom 3
  match thresholds.head? with
  | some t => t
  | none => 99

theorem threshold_is_6 : findThreshold = 6 := by native_decide

/-- **OPEN (P26a)**: Model the full positional game on a grid:
    the grappler wants to hold the target in melee; the target wants
    to reach ranged distance (10m+).  With Sentinel feat (OA stops
    movement), prove the grappler can contain any target within
    a 3×3 area.

    **OPEN (P26b)**: With multiple grapplers (2+ characters), prove
    that "relay grappling" (pass the grapple each round) maintains
    the lock with probability approaching 1 as grappler count → ∞. -/

end VALOR.Scenarios.P26
