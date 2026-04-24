import Lake
open Lake DSL

/-!
# lakefile.lean — Lean 4 Package Manifest for the VALOR FV Core

## Position in the VALOR Closed Loop

Build-system entry-point of the *Symbolic Layer* (Stage 2).
`lake` reads this manifest to resolve dependencies, compile the type
definitions in `Core/`, the auto-generated axioms in `Axioms/`, the
proof-search targets in `Proofs/`, and the self-contained scenario
files in `Scenarios/`.

## Responsibilities

- Declare the Lean 4 package name (`VALOR_FV`).
- Define the library targets `Core`, `Axioms`, `Proofs`, and `Scenarios`,
  enabling incremental compilation when the auto-formalizer rewrites only
  `Axioms/BG3Rules.lean`.

## Academic Context

Using Lean 4 (rather than Lean 3 / Coq / Isabelle) is motivated by its
native metaprogramming facilities and first-class `lake` build system,
which simplify programmatic axiom injection from the neural layer—a key
requirement for closed-loop operation.
-/

package VALOR_FV where
  leanOptions := #[
    ⟨`autoImplicit, false⟩
  ]

/-- Default build target: the v0.1-alpha verified core.

  Includes the foundational ontology (`Core`), the formalised BG3
  axioms (`Axioms.BG3Rules`), the safety/termination meta-properties
  (`Proofs`), and the one fully-formalised showcase scenario
  (`Scenarios.P14_AdvantageAlgebra`).  `lake build` on the default
  target must succeed with zero `error`-level diagnostics.

  Additional draft scenarios (P6-P13, P15-P32) live under
  `Scenarios_wip/` and are excluded from the default build target.
  They are tracked for v0.2 and can be built individually with
  `lake build Scenarios_wip.P<N>_<slug>` once each is upgraded for
  the Lean 4.29 core API. -/
@[default_target]
lean_lib VALOR where
  srcDir := "."
  roots := #[
    `Core.Types, `Core.Engine,
    `Axioms.BG3Rules, `Axioms.DRSItems,
    `Proofs.Exploits, `Proofs.Termination,
    `Scenarios.P14_AdvantageAlgebra,
    `Scenarios.P17_DualWieldCrossover,
    `Scenarios.P22_ActionSurgeExplosion,
    `Scenarios.P29_CoffeelockInfiniteSlots
  ]

/-- Optional library: draft scenarios pending Lean 4.29 upgrade.
    Built only when explicitly requested (`lake build VALOR_WIP`). -/
lean_lib VALOR_WIP where
  srcDir := "."
  globs  := #[.submodules `Scenarios_wip]
