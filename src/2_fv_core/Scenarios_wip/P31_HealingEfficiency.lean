/-!
# P31 — Healing Efficiency Frontier: HP per Action Economy Unit

## Background (bg3.wiki)

BG3 has multiple healing options with different action costs:

| Spell | Level | Action | HP (max) | HP (avg) |
|-------|-------|--------|----------|----------|
| Healing Word | 1 | Bonus | 1d4+WIS = 8 | 5.5 |
| Cure Wounds | 1 | Action | 1d8+WIS = 12 | 8.5 |
| Heal (potion) | — | Bonus* | 2d4+2 = 10 | 7 |
| Greater Heal Potion | — | Bonus* | 4d4+4 = 20 | 14 |
| Mass Healing Word | 3 | Bonus | 1d4+WIS × 6 = 48 | 33 |
| Mass Cure Wounds | 5 | Action | 3d8+WIS × 6 = 180 | 114 |
| Heal (spell L6) | 6 | Action | 70 flat | 70 |

(*BG3 allows potion as bonus action)

## Key Question

What is the **Pareto frontier** of healing efficiency when considering
both (1) HP healed and (2) action economy cost?  Is Healing Word
strictly dominated by any alternative?

## Academic Significance

This is a **multi-objective optimization** problem with two objectives:
maximize HP healed and minimize action economy cost.  The Pareto
frontier identifies the set of "non-dominated" healing options.

This connects to *Pareto efficiency* (Pareto, 1906), *multi-criteria
decision analysis*, and *resource allocation in distributed systems*.

## Quantifier Structure

∀ (option : HealOption), onPareto option ↔
  ¬∃ (other : HealOption),
    other.efficiency ≥ option.efficiency ∧
    other.cost ≤ option.cost ∧
    (other.efficiency > option.efficiency ∨ other.cost < option.cost)
-/

namespace VALOR.Scenarios.P31

-- ── Healing model ───────────────────────────────────────────────────────

/-- Action economy cost units:
    Standard Action = 2, Bonus Action = 1, Reaction = 1.
    This reflects that a Standard Action is worth ~2 Bonus Actions
    because Bonus Actions can't be used for most attacks. -/
inductive ActionCost where
  | bonusAction    -- 1 unit
  | standardAction -- 2 units
  deriving DecidableEq, Repr

def ActionCost.units : ActionCost → Nat
  | .bonusAction => 1
  | .standardAction => 2

structure HealOption where
  name       : String
  spellLevel : Nat       -- 0 = potion/cantrip
  cost       : ActionCost
  hpMax      : Nat       -- maximum HP healed (single target)
  hpAvgX2    : Nat       -- average HP × 2 (to stay in Nat)
  targets    : Nat       -- number of targets (1 for single)
  slotCost   : Nat       -- spell slot level (0 for potions)
  deriving Repr

def HealOption.totalMaxHP (h : HealOption) : Nat := h.hpMax * h.targets
def HealOption.efficiencyMax (h : HealOption) : Nat := h.totalMaxHP / h.cost.units
def HealOption.totalAvgX2 (h : HealOption) : Nat := h.hpAvgX2 * h.targets

-- ── Healing options (WIS mod = 4 assumed) ───────────────────────────────

def healingWord : HealOption :=
  ⟨"Healing Word", 1, .bonusAction, 8, 11, 1, 1⟩

def cureWounds : HealOption :=
  ⟨"Cure Wounds", 1, .standardAction, 12, 17, 1, 1⟩

def healPotion : HealOption :=
  ⟨"Potion of Healing", 0, .bonusAction, 10, 14, 1, 0⟩

def greaterHealPotion : HealOption :=
  ⟨"Potion of Greater Healing", 0, .bonusAction, 20, 28, 1, 0⟩

def massHealingWord : HealOption :=
  ⟨"Mass Healing Word", 3, .bonusAction, 8, 11, 6, 3⟩

def massCureWounds : HealOption :=
  ⟨"Mass Cure Wounds", 5, .standardAction, 27, 38, 6, 5⟩

def healSpell : HealOption :=
  ⟨"Heal", 6, .standardAction, 70, 140, 1, 6⟩

def allOptions : List HealOption :=
  [healingWord, cureWounds, healPotion, greaterHealPotion,
   massHealingWord, massCureWounds, healSpell]

-- ── Efficiency metrics ──────────────────────────────────────────────────

/-- HP per action unit (max). -/
theorem hw_efficiency : healingWord.efficiencyMax = 8 := by native_decide
theorem cw_efficiency : cureWounds.efficiencyMax = 6 := by native_decide
theorem pot_efficiency : healPotion.efficiencyMax = 10 := by native_decide
theorem gpot_efficiency : greaterHealPotion.efficiencyMax = 20 := by native_decide
theorem mhw_efficiency : massHealingWord.efficiencyMax = 48 := by native_decide
theorem mcw_efficiency : massCureWounds.efficiencyMax = 81 := by native_decide
theorem heal_efficiency : healSpell.efficiencyMax = 35 := by native_decide

-- ── Pareto dominance ────────────────────────────────────────────────────

/-- Option A dominates B if A has ≥ efficiency and ≤ cost, with strict
    inequality in at least one dimension. -/
def dominates (a b : HealOption) : Bool :=
  a.efficiencyMax ≥ b.efficiencyMax &&
  a.cost.units ≤ b.cost.units &&
  (a.efficiencyMax > b.efficiencyMax || a.cost.units < b.cost.units)

/-- Healing Word (8 HP/unit, bonus) vs Cure Wounds (6 HP/unit, action):
    HW dominates CW!  HW has better efficiency AND lower cost. -/
theorem hw_dominates_cw :
    dominates healingWord cureWounds = true := by native_decide

/-- Greater Heal Potion (20 HP/unit, bonus) dominates both HW and CW. -/
theorem gpot_dominates_hw :
    dominates greaterHealPotion healingWord = true := by native_decide

/-- Mass Healing Word (48 HP/unit, bonus) dominates single-target options. -/
theorem mhw_dominates_gpot :
    dominates massHealingWord greaterHealPotion = true := by native_decide

-- ── Slot efficiency (HP per slot level) ─────────────────────────────────

/-- HP per slot level: which spell gives the most healing per slot? -/
def hpPerSlot (h : HealOption) : Nat :=
  if h.slotCost == 0 then 0  -- potions have infinite slot efficiency
  else h.totalMaxHP / h.slotCost

theorem hw_per_slot : hpPerSlot healingWord = 8 := by native_decide
theorem cw_per_slot : hpPerSlot cureWounds = 12 := by native_decide
theorem mhw_per_slot : hpPerSlot massHealingWord = 16 := by native_decide
theorem mcw_per_slot : hpPerSlot massCureWounds = 32 := by native_decide
theorem heal_per_slot : hpPerSlot healSpell = 11 := by native_decide

/-- Heal (L6, 70 HP/slot=11.7) is LESS slot-efficient than
    Mass Cure Wounds (L5, 32 HP/slot)!  The AoE multiplier
    dominates the flat healing of Heal. -/
theorem mcw_more_slot_efficient_than_heal :
    hpPerSlot massCureWounds > hpPerSlot healSpell := by native_decide

-- ── The "in-combat" question ────────────────────────────────────────────

/-- In combat, the key trade-off is: spend your action healing
    vs. spending it attacking.  If your attack does 20 damage/action
    and healing does 12 HP/action, attacking is better (enemy dies
    faster, reducing incoming damage).

    Healing Word uses a BONUS action → no opportunity cost on attacking.
    This makes HW uniquely valuable despite low throughput.

    Metric: "effective HP value" = HP healed + opportunity cost saved.
    HW: 8 HP + 20 (kept standard action for attack) = 28 effective.
    CW: 12 HP + 0 (lost attack action) = 12 effective.
    HW effective value is 2.3× Cure Wounds! -/

def effectiveValue (h : HealOption) (attackDPR : Nat) : Nat :=
  let savedAttack := if h.cost == .bonusAction then attackDPR else 0
  h.hpMax + savedAttack

theorem hw_effective_at_20dpr :
    effectiveValue healingWord 20 = 28 := by native_decide

theorem cw_effective_at_20dpr :
    effectiveValue cureWounds 20 = 12 := by native_decide

theorem hw_effective_dominates_cw :
    effectiveValue healingWord 20 > 2 * effectiveValue cureWounds 20 := by native_decide

/-- **The Healing Word Theorem**: For any attack DPR ≥ 8,
    Healing Word's effective value strictly exceeds Cure Wounds'.
    Formally: ∀ dpr ≥ 8, 8 + dpr > 12. -/
theorem healing_word_theorem (dpr : Nat) (h : dpr ≥ 8) :
    effectiveValue healingWord dpr > effectiveValue cureWounds dpr := by
  simp [effectiveValue]
  omega

/-- **OPEN (P31a)**: Extend to a full encounter simulation.  Given
    N rounds of combat, compare "heal reactively" (heal when ally
    drops to 0) vs "heal proactively" (keep HP above a threshold).
    Prove that reactive healing with Healing Word (the "yo-yo"
    strategy) outperforms proactive healing with Cure Wounds for
    expected party survival.

    **OPEN (P31b)**: Compute the Pareto frontier for ALL healing
    options considering three objectives: HP/action, HP/slot,
    and gold cost.  Potions have high gold cost but zero slot cost. -/

end VALOR.Scenarios.P31
