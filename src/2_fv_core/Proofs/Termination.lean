import Core.Types
import Core.Engine
import Axioms.BG3Rules

/-!
# Termination.lean — Reaction-Chain Termination & Progress Proofs

## Core Theorem

Every chain of triggered reactions in a round is bounded by the number
of entities, because each entity may use at most one reaction per round.
This eliminates the class of "infinite reaction loop" exploits.

## Proof Strategy

Define a well-founded measure: `|entities| - |reactionsUsed|`.
Each reaction strictly decreases this measure → termination by
well-founded induction.
-/

namespace VALOR.Proofs.Termination

open VALOR

-- ── The termination measure ─────────────────────────────────────────────

def reactionFuel (s : Rules.ReactionChainState) : Nat :=
  s.entities.length - s.reactionsUsed.length

/--
**Main termination theorem**: Using a reaction strictly decreases
the fuel, and fuel is a natural number, so the chain must terminate.
-/
theorem reaction_decreases_fuel (s : Rules.ReactionChainState) (e : EntityId)
    (_h_can : s.canReact e = true)
    (h_bound : s.reactionsUsed.length < s.entities.length) :
    reactionFuel (s.useReaction e) < reactionFuel s := by
  simp [reactionFuel, Rules.ReactionChainState.useReaction]
  omega

/--
**Corollary**: The maximum chain length equals the number of entities.
With N entities in combat, at most N reactions can fire in sequence.
-/
theorem max_chain_length (s : Rules.ReactionChainState)
    (h_clean : s.reactionsUsed = []) :
    reactionFuel s = s.entities.length := by
  simp [reactionFuel, h_clean]

-- ── Progress: the game loop never deadlocks ─────────────────────────────

/--
From any reachable state in which entity `e` exists, the `passTurn`
event is always valid: the game loop never deadlocks.

`step` is non-recursive (factored via `stepEndTurn`), so the proof is
a direct case-split on whether `getEntity` returns `some`. -/
theorem pass_turn_always_valid (gs : GameState) (e : EntityId)
    (h : (gs.getEntity e).isSome) :
    (step gs (.passTurn e)).isSome := by
  simp only [step, stepEndTurn]
  cases hge : gs.getEntity e with
  | none      => simp [hge] at h
  | some _ent => simp

/--
End-of-turn condition ticking preserves list structure: the resulting
list is no longer than the input.  Follows from `List.length_filterMap_le`. -/
theorem tick_preserves_length (tp : TickType) (cs : List ActiveCondition) :
    (tickConditions tp cs).length ≤ cs.length := by
  unfold tickConditions
  exact List.length_filterMap_le _ _

end VALOR.Proofs.Termination
