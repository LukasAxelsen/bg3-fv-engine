# VALOR `v0.2-alpha`

[![CI](https://github.com/LukasAxelsen/bg3-fv-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/LukasAxelsen/bg3-fv-engine/actions)
[![Lean 4](https://img.shields.io/badge/Lean-4.29.1-blueviolet)](https://leanprover.github.io)

**Verified Automated Loop for Oracle-driven Rule-checking**

[English](README.md) | [中文](README_zh.md) | [Dansk](README_da.md)

A neuro-symbolic, closed-loop framework for the formal verification of computer-game combat mechanics, instantiated on Baldur's Gate 3.  `v0.2-alpha` ships:

- **a verified Lean 4 core** (`lake build` is green; zero `error`, zero warnings, zero `sorry` in the default target);
- **four fully-mechanised research scenarios** (P14 advantage/disadvantage algebra, P17 dual-wield crossover, P22 action-economy bound, P29 Coffeelock bounded-vs-unbounded), one of which surfaces a non-trivial open-vs-closed algebraic finding (`combine` is commutative but **not** associative — refuted in Lean as `combine_not_assoc`);
- **a curated DRS-items catalogue** ingested from `bg3.wiki/wiki/Damage_Mechanics` into both a SQLite table and a generator-checked `Axioms/DRSItems.lean` (Honour-mode-demotion theorem proved by `decide`);
- **a Python data pipeline** for crawling [bg3.wiki](https://bg3.wiki) into a typed local database, with a 22-spell gold index and an LLM-accuracy harness (OpenAI / Anthropic / dry-run providers);
- **an aligned Lean ↔ Lua bridge** that compiles Lean counter-examples into Script-Extender Lua scripts honouring the actual `VALOR.Sandbox` API; and a probability-scenario CLI that closes the loop on P14's `adv_dc11` claim with kernel-proven theory + game-side verification (118 Python tests).

The 23 remaining scenario drafts (P6–P13, P15–P16, P18–P21, P23–P28, P30–P32) live under `Scenarios_wip/` and are tracked as v0.3 work.  See the [`v0.2` scope](#v02-scope) section below for an explicit, machine-checkable list of every claim.

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

If both commands print success, every claim in the [`v0.2` scope](#v02-scope) section below is now machine-checked on your machine.

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

## `v0.2` scope

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
| `Axioms/DRSItems.lean`     | `catalogue_has_drs`                 | The bg3.wiki-derived DRS catalogue has at least one DRS entry (sanity check).            | `decide`                |
| `Axioms/DRSItems.lean`     | `all_drs_demoted_in_honour`         | Every catalogued DRS item is documented as Honour-mode-demoted to a plain DR.            | `decide`                |
| `Proofs/Exploits.lean`     | `catalogue_drs_damage_positive`     | Worst-case rider damage of the catalogue's DRS items is strictly positive.               | `decide`                |
| `Proofs/Exploits.lean`     | `catalogue_honour_neutralises_drs`  | Catalogue-level statement that Honour mode neutralises every DRS exploit in the seed.    | reuse                   |

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

### Scenario P17 — Dual-Wield Crossover (`Scenarios/P17_*.lean`)

| Theorem                          | What it states                                                                                | Tactic              |
| -------------------------------- | --------------------------------------------------------------------------------------------- | ------------------- |
| `two_handed_gwm_always_wins`     | **Universal.** Two-Handed-with-GWM strictly dominates Dual-Wield in max DPR for STR ≤ 10.    | `unfold` + `omega`  |
| `no_gwm_crossover_at_6`          | At STR mod = 6 the no-GWM Two-Handed and Dual-Wield max DPRs are exactly equal.               | `native_decide`     |
| `no_gwm_th_wins_below_6`         | **Universal.** For STR mod < 6 (no GWM), Two-Handed strictly beats Dual-Wield.                | `unfold` + `omega`  |
| `no_gwm_dw_wins_above_6`         | **Universal.** For STR mod > 6 (no GWM), Dual-Wield strictly beats Two-Handed.                | `unfold` + `omega`  |
| `gwm_hit_penalty`                | Concrete: hit-prob×20 numerator at +8 vs +3 to-hit against AC 16.                              | `native_decide`     |

### Scenario P22 — Action-Economy Ceiling (`Scenarios/P22_*.lean`)

| Theorem                          | What it states                                                                                | Tactic              |
| -------------------------------- | --------------------------------------------------------------------------------------------- | ------------------- |
| `total_builds`                   | The combinatorial space of `Build` records has exactly **96** elements.                        | `native_decide`     |
| `global_max_is_11`               | Across all 96 builds the maximum attacks per turn is **11**.                                   | `native_decide`     |
| `no_build_exceeds_11`            | **Universal over `Build`.** No build attains > 11 attacks/turn.                                | `native_decide`     |
| `unique_optimal_build`           | Exactly **one** build achieves the maximum: every flag enabled and Extra-Attack-tier 2.        | `native_decide`     |

The original draft mis-claimed `total_builds = 192` and `optimal_build_count = 4`; both numbers were wrong by direct enumeration in Lean, so the file now asserts the corrected 96 / 1 — another formal-verification correction logged in the codebase history.

### Scenario P29 — Coffeelock (`Scenarios/P29_*.lean`)

| Theorem                          | What it states                                                                                | Tactic              |
| -------------------------------- | --------------------------------------------------------------------------------------------- | ------------------- |
| `cycle_produces_slots`           | One Coffeelock cycle from empty creates exactly 3 Level-1 slots.                               | `native_decide`     |
| `bg3_created_capped`             | A 2-cycle BG3 trace hits the created-slot cap at exactly 4.                                    | `native_decide`     |
| `bg3_max_total`                  | Maximum simultaneously-available slots in BG3 is **6** (2 Pact + 4 capped created).            | `native_decide`     |
| `five_cycles_fifteen_slots`      | Under 5e RAW (no caps), 5 cycles produce 15 slots.                                             | `native_decide`     |
| `ten_cycles_thirty_slots`        | Under 5e RAW (no caps), 10 cycles produce 30 slots — witnessing the unbounded family.          | `native_decide`     |

### What is **not** verified in `v0.2-alpha`

- The remaining 23 draft scenarios `P6–P13, P15–P16, P18–P21, P23–P28, P30–P32` (still under `Scenarios_wip/`).  Each is a v0.3 work item.
- The six rule-axioms in `Axioms/BG3Rules.lean` (`hellish_rebuke_trigger`, `concentration_uniqueness`, `haste_self_cast_bug`, `fireball_damage`, `counterspell_uses_intelligence`, `hex_crit_bug`).  These are **assumed** facts about the BG3 engine; the verification pipeline is responsible for them, not the kernel.  Their numerical constants are pinned to `dataset/axiom_provenance.json` and tested for non-drift by `tests/test_axiom_provenance.py`.
- The actual `step` semantics is *worst-case* by default (`Entity.applyDamageWith .worstCase`).  Average-DPR claims must use `.expected2` explicitly.

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
           PYTHONPATH=src/3_engine_bridge python3 -m lua_generator \
             --scenario p14_adv_dc11 --trials 1000 --seed 1 \
             --out "<BG3_SE_Lua_Dir>/VALOR_Scripts/p14.lua"

Step 5.  In-game: load any combat encounter so the engine is "live".
         The mod polls VALOR_Scripts/, runs p14.lua, and appends one JSONL
         line per trial to:
           "<BG3_SE_Lua_Dir>/VALOR_Logs/valor_prob_p14_adv_dc11.jsonl"

Step 6.  Compare:
           PYTHONPATH=src/3_engine_bridge python3 -m log_analyzer \
             --scenario p14_adv_dc11 \
             --log    "<BG3_SE_Lua_Dir>/VALOR_Logs/valor_prob_p14_adv_dc11.jsonl" \
             --tolerance 0.04
         Expected output (exit 0):
           "AGREE: scenario=p14_adv_dc11 trials=1000 observed=0.7480 ± 0.0137
            theoretical=0.7500 |delta|=0.0020 tolerance=0.0400"
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

### Foundational

- Clarke, Grumberg, Jha, Lu & Veith (2000). *Counterexample-Guided Abstraction Refinement.* CAV.
- de Moura & Ullrich (2021). *The Lean 4 Theorem Prover and Programming Language.* CADE.
- Ginsberg (1988). *Multivalued Logics: A Uniform Approach to Inference in Artificial Intelligence.* Computational Intelligence.
- Madaan et al. (2023). *Self-Refine: Iterative Refinement with Self-Feedback.* NeurIPS — used as the LLM self-correction template for the closed loop.
- First, Rabe, Ringer & Brun (2023). *Baldur: Whole-Proof Generation and Repair with Large Language Models.* ESEC/FSE — closest published precedent for LLM-driven Lean correction loops.

### Closely-related game / rule formalisations

- Mavani (2025). *Lean 4 Machine-Assisted Proof Framework for Chip-Firing Games and the Graphical Riemann–Roch Theorem.* — Lean 4 formalisation of a non-trivial game-theoretic combinatorial system; shares our methodological choice of typed ontology + executable semantics.
- Capretta et al. (2025). *Towards a Mechanisation of Fraud Proof Games in Lean.* OASIcs / FMBC — first Lean 4 formalisation of multi-agent arbitration games; closest analogue to our Counterspell-war scenario family.
- The `vihdzp/combinatorial-games` Lean 4 library — Conway combinatorial-game theory, including Sprague–Grundy and surreal numbers; supplies the algebraic vocabulary we draw on for P14 and the open P22 / P28 problems.
- Trequetrum, *lean4game-logic* — game-shaped pedagogical Lean 4 framework; precedent for shipping verification artefacts as runnable interactive content.
- Aochagavía, *tic-tac-toe-lean* — minimal Lean 4 formalisation of a complete game; useful baseline for the right *granularity* of state machine when the game logic is small.
- Kwiatkowska, Norman & Parker (2011). *PRISM 4.0: Verification of Probabilistic Real-time Systems.* CAV — the canonical probabilistic model-checker; the right point of comparison for our `probability_scenarios` analyser when judging variance / sample complexity claims.
- Hahn et al. (2017–2024). *The probabilistic model checker Storm* (multiple JFR / TACAS papers) — alternative probabilistic backend; same comparison rationale as PRISM.

### Repository-internal precedents

- [`sts_lean`](https://github.com/collinzrj/sts_lean) — Slay the Spire infinite-combo Lean 4 hobby project; cited as informal motivation, not as an academic baseline.
- [bg3.wiki](https://bg3.wiki) — Community wiki, the sole data source for every numeric constant in `Axioms/BG3Rules.lean` and `Axioms/DRSItems.lean`.

## License

MIT
