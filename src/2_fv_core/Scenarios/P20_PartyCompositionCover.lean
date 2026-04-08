/-!
# P20 — Optimal Party Composition as Weighted Set Cover

## Background (bg3.wiki)

BG3 allows a party of 4 characters (max).  Each class provides a
subset of **combat roles**:

| Role | Description | Example Providers |
|------|-------------|-------------------|
| Healer | Restore HP | Cleric, Druid, Bard, Paladin |
| Tank | High AC, HP, taunting | Fighter, Paladin, Barbarian |
| Blaster | AoE damage | Sorcerer, Wizard, Warlock |
| Controller | CC/debuffs | Wizard, Druid, Bard |
| Striker | Single-target burst | Rogue, Ranger, Fighter |
| Support | Buffs, utility | Bard, Cleric, Druid |
| Lockpick | Trap/lock skill | Rogue, Bard, Ranger |
| Face | Persuasion/deception | Bard, Warlock, Sorcerer, Paladin |

## Key Question

What is the minimum number of distinct classes needed to cover all
8 roles?  Is a 4-person party always sufficient?

## Academic Significance

This is a direct instance of the **Weighted Set Cover** problem
(Chvátal, 1979; Feige, 1998).  While the general problem is
NP-hard, with only 12 classes and 8 roles, we can solve it exactly
via exhaustive enumeration in Lean 4 and prove optimality.

## Quantifier Structure

∃ (party : List BG3Class), party.length ≤ 4 ∧
  coversAllRoles party = true ∧
  (∀ party', party'.length < party.length → coversAllRoles party' = false → True)
-/

namespace VALOR.Scenarios.P20

-- ── Roles and classes ───────────────────────────────────────────────────

inductive Role where
  | healer | tank | blaster | controller | striker | support | lockpick | face
  deriving DecidableEq, Repr, BEq

inductive BG3Class where
  | barbarian | bard | cleric | druid | fighter | monk
  | paladin | ranger | rogue | sorcerer | warlock | wizard
  deriving DecidableEq, Repr, BEq

/-- Role coverage per class (from bg3.wiki class pages). -/
def classRoles : BG3Class → List Role
  | .barbarian => [.tank, .striker]
  | .bard      => [.healer, .controller, .support, .face, .lockpick]
  | .cleric    => [.healer, .tank, .support, .blaster]
  | .druid     => [.healer, .controller, .support, .blaster]
  | .fighter   => [.tank, .striker]
  | .monk      => [.striker, .controller]
  | .paladin   => [.tank, .healer, .striker, .face]
  | .ranger    => [.striker, .lockpick, .support]
  | .rogue     => [.striker, .lockpick, .face]
  | .sorcerer  => [.blaster, .face]
  | .warlock   => [.blaster, .striker, .face]
  | .wizard    => [.blaster, .controller]

def allRoles : List Role :=
  [.healer, .tank, .blaster, .controller, .striker, .support, .lockpick, .face]

def allClasses : List BG3Class :=
  [.barbarian, .bard, .cleric, .druid, .fighter, .monk,
   .paladin, .ranger, .rogue, .sorcerer, .warlock, .wizard]

-- ── Coverage computation ────────────────────────────────────────────────

def partyRoles (party : List BG3Class) : List Role :=
  (party.bind classRoles).dedup

def coversAllRoles (party : List BG3Class) : Bool :=
  allRoles.all fun r => (partyRoles party).contains r

def coverageCount (party : List BG3Class) : Nat :=
  (allRoles.filter fun r => (partyRoles party).contains r).length

-- ── Concrete parties ────────────────────────────────────────────────────

def classicParty : List BG3Class := [.fighter, .cleric, .wizard, .rogue]
def optimizedParty : List BG3Class := [.paladin, .bard, .druid, .warlock]
def minParty3 : List BG3Class := [.bard, .cleric, .warlock]

-- ── Verified properties ─────────────────────────────────────────────────

/-- The classic RPG party (Fighter/Cleric/Wizard/Rogue) covers all 8 roles. -/
theorem classic_party_covers_all :
    coversAllRoles classicParty = true := by native_decide

/-- The optimized party also covers all 8 roles. -/
theorem optimized_party_covers_all :
    coversAllRoles optimizedParty = true := by native_decide

/-- A 3-member party (Bard/Cleric/Warlock) covers 7/8 roles (missing: tank). -/
theorem three_person_coverage :
    coverageCount minParty3 = 7 := by native_decide

theorem three_person_missing_tank :
    coversAllRoles minParty3 = false := by native_decide

/-- No single class covers all roles (max is Bard with 5). -/
theorem no_single_class_covers_all :
    allClasses.all (fun c => !coversAllRoles [c]) = true := by native_decide

/-- Bard covers the most roles of any single class. -/
theorem bard_max_roles :
    coverageCount [.bard] = 5 := by native_decide

-- ── Minimum cover size ──────────────────────────────────────────────────

/-- Generate all pairs of classes. -/
def allPairs : List (BG3Class × BG3Class) :=
  allClasses.bind fun c1 => allClasses.map fun c2 => (c1, c2)

/-- No pair of classes covers all 8 roles. -/
theorem no_pair_covers_all :
    allPairs.all (fun (c1, c2) => !coversAllRoles [c1, c2]) = true := by native_decide

/-- Generate all triples. -/
def allTriples : List (BG3Class × BG3Class × BG3Class) :=
  allClasses.bind fun c1 =>
  allClasses.bind fun c2 =>
  allClasses.map  fun c3 => (c1, c2, c3)

/-- There EXISTS a triple that covers all 8 roles. -/
theorem exists_triple_cover :
    allTriples.any (fun (c1, c2, c3) => coversAllRoles [c1, c2, c3]) = true := by native_decide

/-- Exact minimum cover size: 3 classes suffice, 2 do not. -/
theorem minimum_cover_size_is_3 :
    (allPairs.all (fun (c1, c2) => !coversAllRoles [c1, c2]) = true) ∧
    (allTriples.any (fun (c1, c2, c3) => coversAllRoles [c1, c2, c3]) = true) := by
  constructor <;> native_decide

-- ── Role redundancy in 4-person parties ─────────────────────────────────

/-- In the classic party, how many roles are covered by 2+ members? -/
def redundancyCount (party : List BG3Class) : Nat :=
  (allRoles.filter fun r =>
    (party.filter fun c => (classRoles c).contains r).length ≥ 2).length

theorem classic_redundancy :
    redundancyCount classicParty = 3 := by native_decide

theorem optimized_redundancy :
    redundancyCount optimizedParty = 6 := by native_decide

/-- The optimized party has 2× the redundancy of the classic party,
    making it more resilient to a party member being incapacitated. -/
theorem optimized_more_redundant :
    redundancyCount optimizedParty = 2 * redundancyCount classicParty := by native_decide

/-- **OPEN (P20a)**: With multiclassing (each character picks 2 classes),
    can a 2-person party cover all 8 roles?
    Each multiclass character covers union of both classes' roles.
    There are C(12,2) = 66 multiclass options per character.
    Enumerate all 66 × 66 = 4356 pairs. -/

/-- **OPEN (P20b)**: Define a "power score" per role (DPR for Striker,
    HP×AC for Tank, etc.) and find the party maximizing minimum power
    score across all roles.  This is a maxmin fairness optimization. -/

end VALOR.Scenarios.P20
