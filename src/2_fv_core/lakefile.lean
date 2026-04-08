/-!
# lakefile.lean — Lean 4 Package Manifest for the VALOR FV Core

## Position in the VALOR Closed Loop

This file is the **build-system entry-point** of the *Symbolic Layer*
(Stage 2).  `lake` (the Lean 4 package manager) reads this manifest to
resolve dependencies, compile the type definitions in `Core/`, the
auto-generated axioms in `Axioms/`, and the proof-search targets in
`Proofs/`.

```
  Auto-Formalizer (Stage 1)
        │  writes Lean 4 source
        ▼
  ┌─────────────────────────────────────┐
  │  2_fv_core/                         │
  │  lakefile.lean  ◄── you are here    │
  │  Core/  Axioms/  Proofs/            │
  └─────────────────┬───────────────────┘
                    │  counterexample / proof certificate
                    ▼
            Engine Bridge (Stage 3)
```

## Responsibilities

- Declare the Lean 4 package name (`VALOR_FV`).
- Pin the `mathlib4` dependency (needed for tactic libraries such as
  `omega`, `decide`, and the SMT bridge `Std.Tactic.Omega`).
- Define the library target that includes `Core`, `Axioms`, and `Proofs`
  as sub-modules, enabling incremental compilation when the
  auto-formalizer rewrites only `Axioms/BG3Rules.lean`.

## Academic Context

Using Lean 4 (rather than Lean 3 / Coq / Isabelle) is motivated by its
native metaprogramming facilities and first-class `lake` build system,
which simplify programmatic axiom injection from the neural layer—a key
requirement for closed-loop operation.
-/

import Lake
open Lake DSL

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
