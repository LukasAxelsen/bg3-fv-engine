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

@[default_target]
lean_lib Core where
  srcDir := "Core"

lean_lib Axioms where
  srcDir := "Axioms"

lean_lib Proofs where
  srcDir := "Proofs"

lean_lib Scenarios where
  srcDir := "Scenarios"
