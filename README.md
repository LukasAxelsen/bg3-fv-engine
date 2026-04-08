# VALOR

**Verified Automated Loop for Oracle-driven Rule-checking**

Lean 4 formal verification of Baldur's Gate 3 combat mechanics. 27 self-contained scenarios, each encoding a real game mechanic as a decidable proposition and proving (or disproving) it.

Inspired by [sts_lean](https://github.com/collinzrj/sts_lean). Where that project proves infinite combos in Slay the Spire, VALOR proves damage bounds, resource invariants, termination guarantees, and optimal strategies in BG3.

## Quick Start

```bash
git clone https://github.com/LukasAxelsen/bg3-fv-engine.git && cd bg3-fv-engine
python3 -m pip install -r requirements.txt   # crawler + tests
python3 -m pytest tests/ -v                  # 23 tests, <1s

# Lean 4 verification (requires elan: https://github.com/leanprover/elan)
cd src/2_fv_core && lake build               # type-checks all 27 scenarios
```

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

The loop (CEGAR-style, Clarke et al. 2000) iterates until the formal model and game engine agree. The Lean scenarios below work standalone — no LLM or game required.

---

## What We Prove

27 scenarios across 7 proof categories. Every theorem marked ✓ is machine-checked by `native_decide`, `simp`, or `omega`. Theorems marked `sorry` are stated as open problems.

### I. Termination & Well-foundedness

*Chains of triggered game effects always halt.*

| # | Scenario | Key Theorem | Method |
|---|----------|-------------|--------|
| P2 | Reaction chain | `reaction_decreases_fuel` — chain length ≤ entity count | well-founded recursion ✓ |
| P6 | Agathys + Hellish Rebuke cascade | `cascade_always_terminates` — for ANY initial damage | `simp` over struct ✓ |
| P9 | Surface element interactions | `rewriting_terminates` — no infinite Fire↔Water loop | term rewriting ✓ |
| P19 | Wet + Lightning | `wet_consumed_after_aoe` — Wet is a linear resource, consumed on use | Lyapunov function ✓ |

### II. Resource Invariants

*Game resources obey conservation / monotonicity laws.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P3 | Concentration | `concentration_uniqueness` — at most one concentration spell per entity | axiom |
| P5 | Status stacking | `ignore_preserves_existing` — Ignore StackType is idempotent | ✓ |
| P7 | Multiclass spell slots | `esl_paladin5_sorc5 = 7` — exact ESL for all build types | `native_decide` ✓ |
| P15 | Sorcery Point economy | `round_trip_always_lossy` — every SP↔slot cycle loses ≥1 SP | `interval_cases` ✓ |
| P29 | Coffeelock exploit | BG3: `two_cycles_capped` — bounded at 4 extra slots. 5e RAW: `ten_cycles_thirty_slots` — **unbounded** | ✓ / ✓ |

### III. Damage Bounds & Exact Computation

*Precise damage numbers under specific builds, verified against bg3.wiki.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P1 | DRS composition | `drs_amplifies_damage` — DRS causes O((k+1)×m) scaling | `native_decide` ✓ |
| P10 | DRS damage ceiling | `full_turn_damage` — max single-turn damage for the throwing build | `native_decide` ✓ |
| P12 | Smite + Critical Hit | `crit_max = 127`, `crit_preserves_flat` — dice doubled, modifiers not | `native_decide` ✓ |
| P16 | Upcast efficiency | `two_base_beats_upcast` — 2× Fireball L3 > 1× Fireball L6 | `native_decide` ✓ |
| P17 | Dual Wield vs Two-Handed | `no_gwm_crossover_at_6` — exact STR mod where DW overtakes TH | `native_decide` + `omega` ✓ |

### IV. Action Economy Bounds

*Maximum actions/attacks a character can take in one turn.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P4 | Action economy | `max_attacks_is_8`, `max_attacks_honour_is_7` | `native_decide` ✓ |
| P22 | Action Surge + Haste + Thief | `global_max_is_11` — exhaustive search over 192 builds | `native_decide` ✓ |

### V. Probability & Stochastic Dominance

*D20 roll distributions, Markov chains, order statistics.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P8 | Concentration saves | `eb_dc_always_10` — Eldritch Blast DC floors at 10 for all d10 rolls | `simp` + `omega` ✓ |
| P14 | Advantage algebra | `combine_comm`, `combine_assoc`, `adv_idempotent` — 3-element monoid laws | `cases` ✓ |
| P18 | Karmic Dice | `karmic_boost_over_standard` — hit rate increases from 50% to ~54.8% | Markov chain ✓ |
| P21 | Death Saving Throws | `survival_less_than_half` — P(survive) ≈ 46.7%, not 50% | absorbing chain ✓ |
| P25 | Bardic Inspiration | `advantage_never_beats_d6_bi` — BI(d6) ≥ advantage for ALL DCs | exhaustive ✓ |
| P28 | Initiative first-strike | `alert_quadruples_first_strike` — Alert: 9% → 36% all-first (2v2) | order statistics ✓ |

### VI. Game Theory & Adversarial Reasoning

*Optimal play in strategic interactions between casters/combatants.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P11 | Counterspell war | `game_tree_finite` — depth ≤ number of casters | `native_decide` ✓ |
| P23 | Twin Haste + concentration break | `break_round_2 = 0` — adversary break-even at round 2 | `native_decide` ✓ |
| P26 | Grapple / Shove lock | `threshold_is_6` — +6 Athletics needed for 50% 3-round lock | `native_decide` ✓ |

### VII. Combinatorial Optimization

*Build selection, party composition, resource scheduling — many NP-hard in general, solved exactly for BG3's small instance sizes.*

| # | Scenario | Key Theorem | Result |
|---|----------|-------------|--------|
| P13 | Sneak Attack eligibility | `eligible_ratio = 832` — 832/2048 states allow SA (40.6%) | 2¹¹ enumeration ✓ |
| P20 | Party composition | `minimum_cover_size_is_3` — 3 classes cover all 8 roles; 2 cannot | C(12,2) + C(12,3) ✓ |
| P24 | Rest scheduling | `smart_beats_greedy6` — greedy short rest placement is suboptimal | counterexample ✓ |
| P27 | Feat selection | `greedy_suboptimal` — synergies make greedy fail; GWM+PAM+Sentinel optimal | C(12,3) QUBO ✓ |
| P30 | Wild Magic Surge | `positive_expected_value`, `high_variance` — net +EV but σ ≫ μ | statistics ✓ |
| P31 | Healing efficiency | `healing_word_theorem` — HW > Cure Wounds for attack DPR ≥ 8 | `omega` ✓ |
| P32 | Multiclass dip | `rogue_dip_improves_fighter` — pure builds are suboptimal | exhaustive IP ✓ |

---

## Repository Layout

```
src/
  1_auto_formalizer/     Python: wiki crawler, parser, SQLite DB, LLM stub
  2_fv_core/
    Core/                Lean 4 game ontology + state machine
    Axioms/              Formalized BG3 rules (P1–P5)
    Proofs/              Termination and exploit proofs
    Scenarios/           Self-contained scenarios P6–P32 (this is the main contribution)
    lakefile.lean        Build manifest
  3_engine_bridge/       Python: Lean output → Lua scripts → log analysis
  4_ingame_oracle/       Lua: BG3 Script Extender mod
eval/                    Feedback loop orchestrator + metric collection
tests/                   23 pytest tests for the Python layer
dataset/                 Raw wiki dumps + manual annotation benchmarks
```

## Usage

### Verify all theorems

```bash
cd src/2_fv_core && lake build
```

Every `theorem` in `Scenarios/P*.lean` is checked by the Lean 4 kernel. Failures appear as errors; `sorry` marks open problems.

### Crawl game data

```bash
python3 -c "
import importlib
crawler = importlib.import_module('src.1_auto_formalizer.crawler')
crawler.crawl_all()
"
```

All data comes from the [bg3.wiki](https://bg3.wiki) MediaWiki API. Nothing is fabricated.

### Run the feedback loop

```bash
python3 -m eval.run_feedback_loop --rounds 5 --skip-lake --output results/
```

Add `--lean-root src/2_fv_core` if you have `elan` installed. Add `--oracle-log` to incorporate in-game combat logs.

### In-game oracle (optional)

Copy `src/4_ingame_oracle/Mods/VALOR_Injector/*.lua` to your BG3 Script Extender Lua directory, add `Ext.Require("main")` to `BootstrapServer.lua`, and create `VALOR_Scripts/` + `VALOR_Logs/` directories. The mod polls for test scripts and emits JSON combat logs.

## Adding a New Scenario

Create `src/2_fv_core/Scenarios/P33_YourProblem.lean`:

```lean
namespace VALOR.Scenarios.P33

-- Define your game mechanic as computable Lean 4 functions
def myMechanic (x : Nat) : Nat := ...

-- State and prove properties
theorem my_property : myMechanic 42 = expected_value := by native_decide

end VALOR.Scenarios.P33
```

Run `lake build` to verify. No other files need to change.

## References

- Clarke et al. (2000). Counterexample-Guided Abstraction Refinement. *CAV*.
- de Moura & Ullrich (2021). The Lean 4 Theorem Prover. *CADE*.
- [sts_lean](https://github.com/collinzrj/sts_lean) — Slay the Spire infinite combo verification in Lean 4.
- [bg3.wiki](https://bg3.wiki) — Community wiki, sole data source.

## License

MIT
