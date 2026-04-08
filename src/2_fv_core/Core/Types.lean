/-!
# Types.lean — Foundational Ontology for BG3 Combat Verification

Every Lean file in the VALOR FV Core imports this module.  It defines the
vocabulary of entities, damage, status effects, actions, and game state
used by the state machine (Engine.lean), axioms (BG3Rules.lean), and
proof search (Exploits.lean, Termination.lean).

## Design: deeply embedded DSL

Game concepts are modelled as inductive types so that pattern matching is
exhaustive and the Lean kernel rejects ill-formed axioms at compile time.
-/

namespace VALOR

-- ── Damage ──────────────────────────────────────────────────────────────

inductive DamageType where
  | acid | bludgeoning | cold | fire | force
  | lightning | necrotic | piercing | poison
  | psychic | radiant | slashing | thunder
  deriving DecidableEq, Repr

def DamageType.isPhysical : DamageType → Bool
  | .bludgeoning | .piercing | .slashing => true
  | _ => false

structure DiceExpr where
  count : Nat
  sides : Nat
  bonus : Int := 0
  deriving DecidableEq, Repr

def DiceExpr.minVal (d : DiceExpr) : Int := d.count + d.bonus
def DiceExpr.maxVal (d : DiceExpr) : Int := d.count * d.sides + d.bonus

structure DamageRoll where
  dice     : DiceExpr
  dmgType  : DamageType
  deriving Repr

-- ── Abilities & Saves ───────────────────────────────────────────────────

inductive Ability where
  | str | dex | con | int | wis | cha
  deriving DecidableEq, Repr

structure AbilityScores where
  str : Nat := 10
  dex : Nat := 10
  con : Nat := 10
  int : Nat := 10
  wis : Nat := 10
  cha : Nat := 10
  deriving Repr

def AbilityScores.modifier (a : AbilityScores) (ab : Ability) : Int :=
  let score := match ab with
    | .str => a.str | .dex => a.dex | .con => a.con
    | .int => a.int | .wis => a.wis | .cha => a.cha
  (score : Int) / 2 - 5

-- ── Damage Interaction ──────────────────────────────────────────────────

inductive DamageRelation where
  | vulnerable  -- ×2
  | neutral     -- ×1
  | resistant   -- ×0.5
  | immune      -- ×0
  deriving DecidableEq, Repr

-- ── Status / Conditions ─────────────────────────────────────────────────

inductive ConditionTag where
  | hastened | lethargic | hexed | burning | wet
  | frozen | prone | stunned | blinded | silenced
  | concentrating | invisible | blessed | cursed
  | sleeping | downed | frightened | charmed
  | custom (name : String)
  deriving DecidableEq, Repr

inductive StackType where
  | stack | ignore | overwrite | additive
  deriving DecidableEq, Repr

inductive TickType where
  | startTurn | endTurn | startRound | endRound
  deriving DecidableEq, Repr

structure ActiveCondition where
  tag          : ConditionTag
  turnsLeft    : Option Nat
  stackType    : StackType := .overwrite
  tickType     : TickType  := .startTurn
  sourceEntity : Option Nat := none    -- entity id of the caster
  deriving Repr

-- ── Spell Metadata ──────────────────────────────────────────────────────

inductive SpellSchool where
  | abjuration | conjuration | divination | enchantment
  | evocation | illusion | necromancy | transmutation
  deriving DecidableEq, Repr

inductive CastResource where
  | action | bonusAction | reaction
  deriving DecidableEq, Repr

structure SpellLevel where
  val : Nat
  h   : val ≤ 9 := by omega
  deriving Repr

-- ── Entity ──────────────────────────────────────────────────────────────

structure EntityId where
  val : Nat
  deriving DecidableEq, Repr

structure Entity where
  id              : EntityId
  name            : String
  hp              : Int
  maxHp           : Nat
  ac              : Nat
  abilities       : AbilityScores
  proficiencyBonus : Nat := 2
  conditions      : List ActiveCondition := []
  resistances     : DamageType → DamageRelation := fun _ => .neutral
  spellSlots      : List (Nat × Nat)  := []  -- (level, remaining)
  reactionUsed    : Bool := false
  concentratingOn : Option String := none
  deriving Repr

def Entity.isAlive (e : Entity) : Prop := e.hp > 0
def Entity.isDowned (e : Entity) : Prop := e.hp ≤ 0

def Entity.hasCondition (e : Entity) (tag : ConditionTag) : Bool :=
  e.conditions.any (fun c => c.tag == tag)

-- ── Events / Actions ────────────────────────────────────────────────────

inductive SpellTarget where
  | single (target : EntityId)
  | area   (centre : EntityId) (radiusM : Float) (targets : List EntityId)
  | self
  deriving Repr

inductive Event where
  | castSpell      (caster : EntityId) (spellName : String) (slotLevel : Nat)
                   (target : SpellTarget)
  | weaponAttack   (attacker : EntityId) (target : EntityId)
                   (weaponName : String)
  | useReaction    (reactor : EntityId) (reactionName : String)
                   (trigger : Event)
  | applyCondition (source : EntityId) (target : EntityId)
                   (condition : ActiveCondition)
  | takeDamage     (target : EntityId) (rolls : List DamageRoll)
  | heal           (target : EntityId) (amount : Nat)
  | endTurn        (entity : EntityId)
  | passTurn       (entity : EntityId)
  deriving Repr

-- ── Game State ──────────────────────────────────────────────────────────

structure TurnOrder where
  order         : List EntityId
  currentIndex  : Nat := 0
  roundNumber   : Nat := 1
  deriving Repr

def TurnOrder.currentEntity (t : TurnOrder) : Option EntityId :=
  t.order.get? t.currentIndex

structure GameState where
  entities    : List Entity
  turnOrder   : TurnOrder
  eventLog    : List Event := []
  deriving Repr

def GameState.getEntity (gs : GameState) (id : EntityId) : Option Entity :=
  gs.entities.find? (fun e => e.id == id)

def GameState.updateEntity (gs : GameState) (id : EntityId) (f : Entity → Entity) : GameState :=
  { gs with entities := gs.entities.map fun e => if e.id == id then f e else e }

-- ── Invariant Predicates (used by Exploits.lean) ────────────────────────

def GameState.hpNonneg (gs : GameState) : Prop :=
  ∀ e ∈ gs.entities, e.hp ≥ -e.maxHp  -- can go negative up to −maxHp (instant death)

def GameState.atMostOneConcentration (gs : GameState) : Prop :=
  ∀ e ∈ gs.entities, (e.concentratingOn.isSome →
    ¬ ∃ c ∈ e.conditions, c.tag == .concentrating ∧ c.sourceEntity ≠ some e.id.val)

def GameState.reactionsBounded (gs : GameState) : Prop :=
  ∀ e ∈ gs.entities, e.reactionUsed = true ∨
    (gs.eventLog.filter (fun ev => match ev with
      | .useReaction r _ _ => r == e.id
      | _ => false)).length ≤ 1

end VALOR
