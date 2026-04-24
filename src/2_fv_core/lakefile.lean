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
lean_lib VALOR where
  srcDir := "."
  roots := #[
    `Core.Types, `Core.Engine,
    `Axioms.BG3Rules,
    `Proofs.Exploits, `Proofs.Termination,
    `Scenarios.P6_AgathysRebukeCascade, `Scenarios.P7_MulticlassSpellSlots,
    `Scenarios.P8_ConcentrationSaveChain, `Scenarios.P9_SurfaceInteractions,
    `Scenarios.P10_DRSDamageCeiling, `Scenarios.P11_CounterspellWar,
    `Scenarios.P12_SmiteCritDamage, `Scenarios.P13_SneakAttackSAT,
    `Scenarios.P14_AdvantageAlgebra, `Scenarios.P15_SorceryPointEconomy,
    `Scenarios.P16_UpcastEfficiency, `Scenarios.P17_DualWieldCrossover,
    `Scenarios.P18_KarmicDiceBias, `Scenarios.P19_WetLightningChain,
    `Scenarios.P20_PartyCompositionCover, `Scenarios.P21_DeathSaveMarkov,
    `Scenarios.P22_ActionSurgeExplosion, `Scenarios.P23_TwinHasteAdversarial,
    `Scenarios.P24_RestResourceScheduling, `Scenarios.P25_BardicInspirationDominance,
    `Scenarios.P26_GrappleShoveNim, `Scenarios.P27_FeatKnapsack,
    `Scenarios.P28_InitiativeFirstStrike, `Scenarios.P29_CoffeelockInfiniteSlots,
    `Scenarios.P30_WildMagicFairness, `Scenarios.P31_HealingEfficiency,
    `Scenarios.P32_MulticlassDipOptimization
  ]
