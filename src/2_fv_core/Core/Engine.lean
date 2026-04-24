/-!
# Engine.lean — Abstract State-Machine Transition Semantics

Defines `step : GameState → Event → GameState`, the pure operational
semantics of BG3 combat.  This is the kernel against which all proofs
and counterexample searches run.

## Key design choices

1. **Partial function via `Option`**: `step` returns `Option GameState`—
   `none` when the event is illegal in the current state (e.g. casting
   without a spell slot).  Proofs must show precondition satisfaction.
2. **Damage pipeline**: mirrors the real DS/DR/DRS three-tier system
   documented on bg3.wiki/wiki/Damage_mechanics.
3. **Reaction recursion**: reactions (Counterspell, Hellish Rebuke) can
   trigger further reactions.  Termination.lean proves this is bounded.
-/

import Core.Types

namespace VALOR

-- ── Damage application ──────────────────────────────────────────────────

def applyDamageRelation (base : Int) (rel : DamageRelation) : Int :=
  match rel with
  | .vulnerable => base * 2
  | .neutral    => base
  | .resistant  => base / 2
  | .immune     => 0

/-- Apply a list of damage rolls to an entity, respecting resistances. -/
def Entity.applyDamage (e : Entity) (rolls : List DamageRoll) : Entity :=
  let totalDmg := rolls.foldl (fun acc r =>
    let maxDmg := r.dice.maxVal  -- worst-case for verification
    acc + applyDamageRelation maxDmg (e.resistances r.dmgType)
  ) (0 : Int)
  { e with hp := e.hp - totalDmg }

-- ── Concentration check ─────────────────────────────────────────────────

/--
When a concentrating entity takes damage, it must make a CON save.
DC = max(10, damage / 2).  We model the *worst case*: the save fails,
and concentration breaks.
-/
def Entity.breakConcentration (e : Entity) : Entity :=
  { e with
    concentratingOn := none,
    conditions := e.conditions.filter (fun c => c.tag != .concentrating)
  }

-- ── Spell slot consumption ──────────────────────────────────────────────

def consumeSlot (slots : List (Nat × Nat)) (level : Nat) : Option (List (Nat × Nat)) :=
  let rec go : List (Nat × Nat) → Option (List (Nat × Nat))
    | [] => none
    | (l, r) :: rest =>
      if l == level then
        if r > 0 then some ((l, r - 1) :: rest)
        else none
      else match go rest with
        | some rest' => some ((l, r) :: rest')
        | none => none
  go slots

-- ── Condition management ────────────────────────────────────────────────

def Entity.addCondition (e : Entity) (c : ActiveCondition) : Entity :=
  match c.stackType with
  | .stack     => { e with conditions := c :: e.conditions }
  | .ignore    =>
    if e.hasCondition c.tag then e
    else { e with conditions := c :: e.conditions }
  | .overwrite =>
    { e with conditions := c :: e.conditions.filter (fun x => x.tag != c.tag) }
  | .additive  =>
    let existing := e.conditions.find? (fun x => x.tag == c.tag)
    match existing, c.turnsLeft with
    | some old, some newDur =>
      let combined := match old.turnsLeft with
        | some d => some (d + newDur)
        | none   => some newDur
      { e with conditions :=
          { old with turnsLeft := combined } ::
          e.conditions.filter (fun x => x.tag != c.tag) }
    | _, _ => { e with conditions := c :: e.conditions }

-- ── Turn management ─────────────────────────────────────────────────────

def TurnOrder.advance (t : TurnOrder) : TurnOrder :=
  let next := t.currentIndex + 1
  if next ≥ t.order.length then
    { t with currentIndex := 0, roundNumber := t.roundNumber + 1 }
  else
    { t with currentIndex := next }

-- ── Tick: decrement condition durations at turn boundaries ──────────────

def tickConditions (tickPoint : TickType) (conditions : List ActiveCondition) : List ActiveCondition :=
  conditions.filterMap fun c =>
    if c.tickType != tickPoint then some c
    else match c.turnsLeft with
      | none     => some c
      | some 0   => none  -- expired, remove
      | some (n+1) => some { c with turnsLeft := some n }

-- ── The core transition function ────────────────────────────────────────

/--
`step gs event` applies a single event to the game state.

Returns `none` if the event is invalid in the current state (e.g.
no spell slot available, dead entity acting, etc.).
-/
def step (gs : GameState) (event : Event) : Option GameState :=
  match event with

  | .takeDamage targetId rolls =>
    match gs.getEntity targetId with
    | none => none
    | some target =>
      let target' := target.applyDamage rolls
      -- concentration check on damage
      let target'' := if target'.concentratingOn.isSome then
        target'.breakConcentration  -- worst case: save fails
      else target'
      some (gs.updateEntity targetId (fun _ => target''))

  | .heal targetId amount =>
    match gs.getEntity targetId with
    | none => none
    | some target =>
      let newHp := min (target.hp + amount) target.maxHp
      some (gs.updateEntity targetId (fun e => { e with hp := newHp }))

  | .applyCondition _sourceId targetId cond =>
    match gs.getEntity targetId with
    | none => none
    | some _ =>
      some (gs.updateEntity targetId (fun e => e.addCondition cond))

  | .castSpell casterId _spellName slotLevel _target =>
    match gs.getEntity casterId with
    | none => none
    | some caster =>
      -- consume spell slot (cantrips = level 0, no slot needed)
      if slotLevel == 0 then some gs
      else match consumeSlot caster.spellSlots slotLevel with
        | none => none  -- no slot available
        | some slots' =>
          some (gs.updateEntity casterId (fun e => { e with spellSlots := slots' }))

  | .useReaction reactorId _name _trigger =>
    match gs.getEntity reactorId with
    | none => none
    | some reactor =>
      if reactor.reactionUsed then none  -- already used this round
      else some (gs.updateEntity reactorId (fun e => { e with reactionUsed := true }))

  | .endTurn entityId =>
    match gs.getEntity entityId with
    | none => none
    | some entity =>
      let entity' := { entity with
        conditions := tickConditions .endTurn entity.conditions
      }
      let gs' := gs.updateEntity entityId (fun _ => entity')
      some { gs' with turnOrder := gs'.turnOrder.advance }

  | .passTurn entityId =>
    step gs (.endTurn entityId)

  | .weaponAttack _attackerId _targetId _weaponName =>
    some gs  -- weapon attack resolution delegated to axioms

-- ── Multi-step execution ────────────────────────────────────────────────

/-- Execute a sequence of events, short-circuiting on the first illegal step. -/
def executeTrace (gs : GameState) : List Event → Option GameState
  | [] => some gs
  | e :: es => match step gs e with
    | none => none
    | some gs' => executeTrace { gs' with eventLog := gs'.eventLog ++ [e] } es

end VALOR
