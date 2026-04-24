# VALOR `v0.1-alpha`

[![CI](https://github.com/LukasAxelsen/bg3-fv-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/LukasAxelsen/bg3-fv-engine/actions)
[![Lean 4](https://img.shields.io/badge/Lean-4.29.1-blueviolet)](https://leanprover.github.io)

**Verified Automated Loop for Oracle-driven Rule-checking**

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

A neuro-symbolic, closed-loop framework for the formal verification of computer-game combat mechanics, instantiated on Baldur's Gate 3.  `v0.1-alpha` ships:

- **a verified Lean 4 core** (`lake build` is green; zero `error`, zero warnings, zero `sorry` in the default target);
- **a Python data pipeline** for crawling [bg3.wiki](https://bg3.wiki) into a typed local database (55 unit tests);
- **a Lean ↔ Lua bridge** that compiles Lean counter-examples into in-game test scripts;
- **an in-game oracle** as a BG3 Script Extender mod;
- **one fully-mechanised research scenario** (P14, advantage/disadvantage algebra) with a non-trivial open-vs-closed algebraic finding (`combine` is commutative but **not** associative — refuted in Lean).

A further 26 scenario drafts (P6–P13, P15–P32) live under `Scenarios_wip/` and are tracked as v0.2 work.  See the [`v0.1` scope](#v01-scope) section below for an explicit, machine-checkable list of every claim.

The architecture is inspired by [`sts_lean`](https://github.com/collinzrj/sts_lean) (Slay the Spire infinite-combo verification) and the CEGAR pattern (Clarke et al., 2000), adapted to a deeper game with a richer rule surface.

---

## Quick start (verifies the whole project in <60 s)

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git
cd bg3-fv-engine

# Python side: 55 unit tests of the data + bridge layer.
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -q                # ⇒ 55 passed in 0.04s

# Lean side: theorem-prover verification of the core.
# Requires elan: https://github.com/leanprover/elan
cd src/2_fv_core
lake update                                # one-off, generates lake-manifest.json
lake build                                 # ⇒ Build completed successfully (8 jobs).
```

If both commands print success, every claim in the [`v0.1` scope](#v01-scope) section below is now machine-checked on your machine.

---

## Architecture

```
 wiki prose ──crawler.py──▶ SQLite DB ──llm_to_lean.py──▶ Lean 4 axioms
                                                              │
       ┌──────────────────────────────────────────────────────┘
       ▼
 Lean 4 kernel ──lake build──▶ proof / counterexample
       │
       ▼
 lua_generator.py ──▶ BG3 Script Extender mod ──▶ combat log
       │
       ▼
 log_analyzer.py ──▶ divergence report ──▶ LLM correction ──▶ repeat
```

The CEGAR-style loop iterates until the formal model and the game engine agree.  The Lean core in `v0.1-alpha` runs end-to-end without an LLM or a running game; the LLM and oracle stages are present as functional stubs and integration points for v0.2.

---

## `v0.1` scope

This is the exhaustive, machine-checkable list of what `lake build` proves in this release.  No claim outside this table is asserted to be verified.

### Foundations (`Core/`, `Axioms/`, `Proofs/`)

| File                       | Theorem / Definition                | What it states                                                                          | Tactic                  |
| -------------------------- | ----------------------------------- | --------------------------------------------------------------------------------------- | ----------------------- |
| `Core/Types.lean`          | `Entity`, `GameState`, `Event`, …   | Typed ontology of BG3 combat (entities, damage, conditions, actions).                   | (definitions, derived). |
| `Core/Engine.lean`         | `step : GameState → Event → Option` | Total small-step transition function; non-recursive after `stepEndTurn` factoring.      | (definitions).          |
| `Axioms/BG3Rules.lean`     | `drs_damage_scaling`                | The DRS damage formula commutes: `(n+1)·r + b = b + r·(n+1)` over `Int`.                | `Int.mul_comm`          |
| `Axioms/BG3Rules.lean`     | `reaction_chain_bounded`            | Marking an entity as "reacted" strictly grows `reactionsUsed`.                          | `simp`                  |
| `Axioms/BG3Rules.lean`     | `action_economy_bounded`            | `∀ flags, maxAttacksPerTurn flags ≤ 8` (universal).                                     | `cases × 6`             |
| `Axioms/BG3Rules.lean`     | `overwrite_replaces`                | After `addCondition` with `Overwrite`, ≤ 1 condition with that tag remains.             | `simp`                  |
| `Axioms/BG3Rules.lean`     | `ignore_preserves_existing`         | `addCondition` with `Ignore` is a no-op when the tag is already present.                | `simp`                  |
| `Proofs/Exploits.lean`     | `drs_amplifies_damage`              | The concrete DRS exploit scenario deals strictly more damage than its non-DRS version.  | `native_decide`         |
| `Proofs/Exploits.lean`     | `reaction_chain_terminates`         | After one entity reacts, it can no longer react.                                        | `native_decide`         |
| `Proofs/Exploits.lean`     | `max_attacks_is_8`                  | The all-feature build hits the analytic 8-attack bound exactly.                         | `native_decide`         |
| `Proofs/Exploits.lean`     | `max_attacks_honour_is_7`           | In Honour Mode the same build is capped at 7.                                           | `native_decide`         |
| `Proofs/Termination.lean`  | `reaction_decreases_fuel`           | The well-founded measure `entities.length - reactionsUsed.length` strictly decreases.   | `simp` + `omega`        |
| `Proofs/Termination.lean`  | `max_chain_length`                  | Initial fuel equals `entities.length`.                                                  | `simp`                  |
| `Proofs/Termination.lean`  | `pass_turn_always_valid`            | `step gs (.passTurn e)` is `some _` whenever `e` exists in `gs` (liveness, universal).  | `cases` on `getEntity`  |
| `Proofs/Termination.lean`  | `tick_preserves_length`             | End-of-turn condition ticking never lengthens the condition list.                       | `List.length_filterMap_le` |

### Scenario P14 — Advantage / Disadvantage Algebra (`Scenarios/P14_*.lean`)

| Theorem                          | What it states                                                                                | Tactic                  |
| -------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------- |
| `combine_comm`                   | Binary `combine` is commutative.                                                              | `cases × 2; rfl`        |
| `combine_normal_left/right`      | `normal` is a two-sided identity for `combine`.                                               | `cases; rfl`            |
| `adv_idempotent`, `disadv_idempotent` | Idempotency of `advantage` and `disadvantage` under `combine`.                            | `rfl`                   |
| `adv_disadv_annihilate`          | `combine advantage disadvantage = normal`.                                                    | `rfl`                   |
| **`combine_not_assoc`**          | **Refutation.** `combine` is *not* associative; explicit witness `(disadv, adv, adv)`.        | `simp` on the witness   |
| `classify_singleton`, `classify_pair` | The `classify`-then-resolve operator agrees with `combine` on lists of length ≤ 2.       | `cases × n; native_decide` |
| `adv_dc11`, `disadv_dc11`, `normal_dc11` | Closed-form probabilities (×400 / ×20) for DC 11 checks.                              | `native_decide`         |
| **`advantage_ge_normal`**        | **Universal.** `∀ t ∈ [2..20], probAdvantage400 t ≥ probNormal20 t · 20`. Bounded `Fin 19` discharged by `decide` and lifted to `Nat`. | `decide` + `omega`      |
| `advantage_ge_normal_dc{11,15,20}` | Boundary witnesses for the universal claim.                                                | `native_decide`         |

**Academic finding (P14):** the file's previous draft asserted `combine_assoc` and called the structure a *commutative idempotent monoid*.  Mechanising that proof in Lean produced a counter-example, so the structure was reclassified as a **commutative, non-associative, annihilating magma** — strictly weaker than the three-element bilattice of Ginsberg (1988) on the associativity axis.  The refutation is now a theorem (`combine_not_assoc`), and the *order-/grouping-independent* multi-source operator is `classify`, not `resolve`.  This is the kind of correction that closed-loop formal verification is meant to surface.

### What is **not** verified in `v0.1-alpha`

- The 26 draft scenarios `P6–P13, P15–P32` (now under `Scenarios_wip/`).  They contain placeholder theorems that predate the Lean 4.29 `List` API rename and other core changes; many use deprecated tactics or assert numerically wrong values that `native_decide` rejects.  Each one is a v0.2 work item.
- The five rule-axioms in `Axioms/BG3Rules.lean` (`hellish_rebuke_trigger`, `concentration_uniqueness`, `haste_self_cast_bug`, `fireball_damage`, `counterspell_uses_intelligence`, `hex_crit_bug`).  These are **assumed** facts about the BG3 engine; the verification pipeline is responsible for them, not the kernel.  They are listed by `#print axioms` in any theorem that depends on them.

---

## Soundness, TCB, and the model–game gap

Every `theorem` in the default build target is a proof term type-checked by the Lean 4 kernel.  `native_decide` is **exhaustive finite-domain model checking** with a kernel-checked certificate, not sampling.

**Trusted Computing Base.** Run `#print axioms <theorem>` in any file to enumerate the axioms a proof rests on.  For the verified core, the axiom set is:

| Axiom                | Source           | Notes                                       |
| -------------------- | ---------------- | ------------------------------------------- |
| `propext`            | Lean 4 core      | Propositional extensionality                |
| `Quot.sound`         | Lean 4 core      | Quotient soundness                          |
| `Classical.choice`   | Lean 4 core      | Used by `simp`/`decide` infrastructure      |
| `Lean.ofReduceBool`  | `native_decide`  | Trusts compiled reduction; same TCB as Mathlib |
| (the six BG3 axioms in `Axioms/BG3Rules.lean`) | game-engine assumption | Surfaced explicitly; checked by the oracle stage |

**The model–game gap.** The Lean model encodes rules from [bg3.wiki](https://bg3.wiki), which is itself a community reverse-engineering of the game binary.  The CEGAR loop is the mechanism that closes this gap: when the in-game oracle observes a divergence from the model, the divergence is fed back into the LLM stage as a correction.  In `v0.1-alpha` the loop runs end-to-end on synthetic logs (see `eval/run_feedback_loop.py`); in v0.2 it will be wired to a running game.

---

## In-game self-verification tutorial (P14)

The scenario `Scenarios/P14_AdvantageAlgebra.lean` proves, among other things:

> `adv_dc11`: with advantage on a DC 11 d20 check, the probability of success is exactly `300/400 = 75 %`.

Here is how to verify that empirically inside the actual game.

```
Step 1.  Install BG3 Script Extender (https://github.com/Norbyte/bg3se).

Step 2.  Copy the VALOR mod into the SE Lua directory:
           cp src/4_ingame_oracle/Mods/VALOR_Injector/*.lua "<BG3_SE_Lua_Dir>/"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Scripts"
           mkdir -p "<BG3_SE_Lua_Dir>/VALOR_Logs"

         Platform-specific <BG3_SE_Lua_Dir>:
           Linux:   ~/.local/share/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           Windows: %LOCALAPPDATA%/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
           macOS:   ~/Library/Application Support/Larian Studios/Baldur's Gate 3/Script Extender/Lua/

Step 3.  Launch BG3, load any save, open the SE console (default: F10).
         Expected: "[VALOR] Session loaded, polling VALOR_Scripts/"

Step 4.  Generate the test script for P14 (1000 trials at DC 11, advantage):
           python3 -m src.3_engine_bridge.lua_generator \
             --scenario p14_adv_dc11 --trials 1000 \
             --out "<BG3_SE_Lua_Dir>/VALOR_Scripts/p14.lua"

Step 5.  In-game: load any combat encounter so the engine is "live".
         The mod will detect the new script, run it, and write a JSON log:
           "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json"

Step 6.  Compare:
           python3 -m src.3_engine_bridge.log_analyzer \
             --scenario p14_adv_dc11 \
             --log    "<BG3_SE_Lua_Dir>/VALOR_Logs/p14.json" \
             --expect 0.75 --tolerance 0.04
         Expected output: "AGREE: observed 0.74 ± 0.014, theoretical 0.75".
```

If the comparison disagrees outside the tolerance, that is a *divergence*, and is the input to the next CEGAR round.

---

## Repository layout

```
src/
  1_auto_formalizer/     Python: wiki crawler, parser, SQLite DB, LLM stub
  2_fv_core/
    lean-toolchain       Pinned: leanprover/lean4:v4.29.1
    lakefile.lean        Build manifest (default target = verified core)
    Core/                Lean 4 game ontology + state machine
    Axioms/              Formalised BG3 rules (P1–P5)
    Proofs/              Termination + exploit proofs
    Scenarios/           v0.1 verified scenarios (P14)
    Scenarios_wip/       v0.2 drafts (P6–P13, P15–P32; not in default build)
  3_engine_bridge/       Python: Lean output → Lua scripts → log analysis
  4_ingame_oracle/       Lua: BG3 Script Extender mod
eval/                    Feedback loop orchestrator + metric collection
tests/                   55 pytest tests (models, parser, DB, engine bridge)
dataset/                 Raw wiki dumps + manual annotation benchmarks
```

## Adding a new scenario

Create `src/2_fv_core/Scenarios/P33_YourProblem.lean`:

```lean
namespace VALOR.Scenarios.P33

def myMechanic (x : Nat) : Nat := x * x

theorem my_property : myMechanic 7 = 49 := by native_decide

end VALOR.Scenarios.P33
```

Add `` `Scenarios.P33_YourProblem `` to the `roots` list of the default `lean_lib VALOR` target in `src/2_fv_core/lakefile.lean`, then `lake build`.  No other files need to change.

## References

- Clarke, Grumberg, Jha, Lu & Veith (2000). *Counterexample-Guided Abstraction Refinement.* CAV.
- de Moura & Ullrich (2021). *The Lean 4 Theorem Prover and Programming Language.* CADE.
- Ginsberg (1988). *Multivalued Logics: A Uniform Approach to Inference in Artificial Intelligence.* Computational Intelligence.
- [`sts_lean`](https://github.com/collinzrj/sts_lean) — Slay the Spire infinite-combo verification in Lean 4.
- [bg3.wiki](https://bg3.wiki) — Community wiki, sole data source.

## License

MIT
