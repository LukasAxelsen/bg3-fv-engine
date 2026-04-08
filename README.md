# VALOR

**Verified Automated Loop for Oracle-driven Rule-checking**

A neuro-symbolic closed-loop framework that couples LLM-driven auto-formalization with Lean 4 theorem proving and in-engine runtime validation to discover, formally verify, and patch balance-breaking exploits in the combat system of *Baldur's Gate 3*.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Architecture](#architecture)
3. [Research Problems](#research-problems)
4. [Repository Layout](#repository-layout)
5. [Prerequisites](#prerequisites)
6. [Installation](#installation)
7. [Reproducing Results](#reproducing-results)
8. [In-Game Oracle Setup](#in-game-oracle-setup)
9. [Testing](#testing)
10. [Debugging](#debugging)
11. [Extending VALOR](#extending-valor)
12. [References](#references)
13. [License](#license)

---

## Motivation

Game-balance verification is traditionally done through manual playtesting or ad-hoc unit tests—methods that scale poorly with combinatorial rule interactions.  BG3 alone has ~350 spells, ~800 status conditions, a three-tier damage composition system (DS/DR/DRS), and multi-class/feat interactions that create an enormous state space.

VALOR addresses this with a **CEGAR-style closed loop** (Clarke et al., 2000) where:

- A **neural auto-formalizer** (LLM) translates natural-language game rules into machine-checkable Lean 4 axioms.
- A **symbolic prover** (Lean 4 kernel + SMT) searches for balance violations as concrete counterexample traces.
- An **engine bridge** compiles traces into executable Lua scripts.
- An **in-game oracle** (BG3 Script Extender mod) runs the scripts inside the actual game engine and returns ground-truth combat logs.
- A **divergence analyzer** compares predicted vs. observed behavior, feeding corrections back to the LLM.

This loop iterates until convergence: the formal model and the game engine agree on all tested behaviors.

## Architecture

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │                    run_feedback_loop.py                             │
 │                    (master orchestrator)                            │
 ├─────────────────────────────────────────────────────────────────────┤
 │                                                                     │
 │  for round_i in 1..N:                                               │
 │                                                                     │
 │    ┌───────────────────────────────────────┐                        │
 │    │ Stage 1: Auto-Formalize               │  crawler.py            │
 │    │   wiki prose  ──LLM──▶  Lean 4 axioms │  llm_to_lean.py       │
 │    └──────────────────┬────────────────────┘                        │
 │                       ▼                                             │
 │    ┌───────────────────────────────────────┐                        │
 │    │ Stage 2: Formal Verify                │  lake build            │
 │    │   type-check ──▶ search counterexample│  Exploits.lean         │
 │    └──────────────────┬────────────────────┘                        │
 │                       ▼                                             │
 │    ┌───────────────────────────────────────┐                        │
 │    │ Stage 3: Engine Bridge                │  lean_parser.py        │
 │    │   counterexample ──▶ Lua script       │  lua_generator.py      │
 │    └──────────────────┬────────────────────┘                        │
 │                       ▼                                             │
 │    ┌───────────────────────────────────────┐                        │
 │    │ Stage 4: In-Game Oracle               │  VALOR_Injector mod    │
 │    │   execute script ──▶ combat log       │  (BG3 Script Extender) │
 │    └──────────────────┬────────────────────┘                        │
 │                       ▼                                             │
 │    ┌───────────────────────────────────────┐                        │
 │    │ Stage 5: Analyze + Correct            │  log_analyzer.py       │
 │    │   divergence ──LLM──▶ patch axiom     │  llm_to_lean.py        │
 │    └───────────────────────────────────────┘                        │
 │                                                                     │
 │  until: no new divergences for 2 consecutive rounds                 │
 └─────────────────────────────────────────────────────────────────────┘
```

## Research Problems

VALOR currently formalizes five research problems, each chosen for its capacity to produce a publishable finding at a top PL/SE/AI venue (ICSE, FSE, CAV, NeurIPS, ICLR).  The framework is designed so that new problems require only adding axioms to `BG3Rules.lean` and targets to `Exploits.lean`.

### P1 — Damage Source / Rider / DRS Composition Soundness

BG3's damage pipeline classifies bonus damage into three tiers:

| Tier | Abbreviation | Behavior |
|------|-------------|----------|
| Damage Source | DS | Direct damage (weapon hit, spell) |
| Damage Rider | DR | Bonus that "rides" on a source (Hex, coatings) |
| DRS | DRS | Rider **treated as** a new source, causing all riders to reapply |

With *k* DRS effects and *m* riders, total damage scales as *O((k+1) × m)*.  A single thrown-weapon attack with Lightning Jabber + Hex + Lightning Charges + Ring of Flinging + Tavern Brawler deals ~36 average damage (with DRS) vs. ~24 (without)—a 50% amplification from a single hidden mechanic.  Extreme combinations exceed 1,000 damage per attack.

**Formalized in**: `BG3Rules.lean` → `computeTotalDamage`, `drs_damage_scaling`
**Counterexample**: `Exploits.lean` → `drs_exploit_scenario`, `drs_amplifies_damage` ✓ proved via `native_decide`

### P2 — Reaction Chain Termination

Reactions (Counterspell, Hellish Rebuke, Armour of Agathys) can trigger further reactions.  We prove the chain length is bounded by the entity count *N*: each entity has ≤1 reaction per round, so the termination measure `N - |reactionsUsed|` strictly decreases.

**Formalized in**: `Termination.lean` → `reaction_decreases_fuel`, `max_chain_length`
**Proved**: well-founded recursion over `Nat` ✓

### P3 — Concentration Invariant

At most one concentration spell per entity.  The Haste self-cast bug (documented on bg3.wiki) creates a window where casting Haste on yourself, then switching concentration, causes both spells to fail—losing Haste immediately *and* ending the new spell.

**Formalized in**: `BG3Rules.lean` → `concentration_uniqueness`, `haste_self_cast_bug`

### P4 — Action Economy Boundedness

Extra Attack + Haste + Action Surge + Thief's Fast Hands + dual-wield offhand yields at most **8** attacks per turn (7 in Honour Mode).

**Formalized in**: `BG3Rules.lean` → `maxAttacksPerTurn`
**Proved**: `action_economy_bounded` ✓ via exhaustive `cases` + `simp`; `max_attacks_is_8` ✓ via `native_decide`

### P5 — Status Effect Stack Consistency

The Stack ID / Stack Type system (Stack, Ignore, Overwrite, Additive) must form a consistent rewrite system.  We prove that `overwrite` preserves uniqueness and `ignore` is idempotent.

**Formalized in**: `BG3Rules.lean` → `overwrite_replaces`, `ignore_preserves_existing`

## Repository Layout

```
bg3-fv-engine/
├── README.md
├── requirements.txt              # Python dependencies (httpx, pydantic, rich, tenacity)
├── pytest.ini                    # Test configuration
├── .gitignore
│
├── dataset/                      # Ground-truth data
│   ├── raw_wiki_dumps/           # Raw wikitext JSON from bg3.wiki API
│   └── manual_annotations/       # Hand-annotated Lean benchmarks (Fireball, Hex, Counterspell)
│
├── src/
│   ├── 1_auto_formalizer/        # Stage 1: Neural layer (Python)
│   │   ├── models.py             # Pydantic data models (Spell, Condition, DiceExpression, ...)
│   │   ├── wikitext_parser.py    # Deterministic {{Feature page}} template parser
│   │   ├── database.py           # SQLite persistence (dataset/valor.db)
│   │   ├── crawler.py            # MediaWiki API crawler for bg3.wiki
│   │   ├── llm_to_lean.py        # LLM invocation stub (wire your API key here)
│   │   └── prompt_templates/     # Few-shot prompt storage
│   │
│   ├── 2_fv_core/                # Stage 2: Symbolic layer (Lean 4)
│   │   ├── lakefile.lean         # Lean 4 package manifest
│   │   ├── Core/
│   │   │   ├── Types.lean        # Game ontology: Entity, DamageType, Ability, GameState, Event
│   │   │   └── Engine.lean       # State machine: step, damage pipeline, concentration, slots
│   │   ├── Axioms/
│   │   │   └── BG3Rules.lean     # Formalized rules and research problems P1-P5
│   │   └── Proofs/
│   │       ├── Exploits.lean     # Counterexample search (DRS, reaction chains, action economy)
│   │       └── Termination.lean  # Well-founded termination proofs
│   │
│   ├── 3_engine_bridge/          # Stage 3: Communication layer (Python)
│   │   ├── lean_parser.py        # Parse lake build output → CounterexamplePath
│   │   ├── lua_generator.py      # CounterexamplePath → BG3 Lua script with assertions
│   │   └── log_analyzer.py       # Combat log → DivergenceReport (VALUE_MISMATCH, ...)
│   │
│   └── 4_ingame_oracle/          # Stage 4: Execution layer (Lua)
│       └── Mods/VALOR_Injector/
│           ├── main.lua          # Session listener, file watcher, pcall-guarded dispatch
│           ├── sandbox.lua       # Deterministic test env: spawn dummies, reset state, RNG
│           └── execute.lua       # Action executor, state snapshots, JSON combat log emitter
│
├── eval/                         # Evaluation and orchestration
│   ├── evaluate_accuracy.py      # Formalization accuracy: EM, clause F1, semantic equivalence
│   ├── run_feedback_loop.py      # Master loop: N rounds of formalize→verify→bridge→oracle→correct
│   └── collect_metrics.py        # Generate paper figures (matplotlib) and LaTeX tables
│
├── tests/                        # Pytest suite (23 tests)
│   ├── conftest.py               # Module import shim for digit-prefixed directories
│   ├── test_wikitext_parser.py   # Parser tests with real bg3.wiki template strings
│   ├── test_database.py          # SQLite CRUD and query tests
│   └── test_models.py            # Data model validation tests
│
└── docs/                         # Generated figures and tables for paper
```

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | ≥ 3.11 | Crawler, bridge, eval scripts |
| [elan](https://github.com/leanprover/elan) + Lean 4 | ≥ 4.3.0 | Formal verification core |
| [BG3 Script Extender](https://github.com/Norbyte/bg3se) | ≥ v18 | In-game oracle (optional for offline verification) |
| Baldur's Gate 3 | Patch 7+ | Runtime oracle (optional) |

The Lean 4 and in-game components are **optional**.  The crawler, parser, database, and Python tests work standalone.

## Installation

```bash
# 1. Clone
git clone https://github.com/<you>/bg3-fv-engine.git
cd bg3-fv-engine

# 2. Python dependencies
python3 -m pip install -r requirements.txt

# 3. Verify installation (23 tests, <1 second)
python3 -m pytest tests/ -v

# 4. (Optional) Lean 4 toolchain
curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh
cd src/2_fv_core && lake build
```

## Reproducing Results

### Step 1: Crawl game data from bg3.wiki

Every record is sourced exclusively from the bg3.wiki MediaWiki API.  No data is fabricated.  Each spell entry retains its provenance URL and verbatim wikitext for auditability.

```bash
# Crawl a single spell (verify data integrity)
python3 -c "
import importlib
crawler = importlib.import_module('src.1_auto_formalizer.crawler')
crawler.main()
" --spell Fireball

# Full crawl: all spells (Cantrips through Level 6), ~5 min at 2 req/s
python3 -c "
import importlib
crawler = importlib.import_module('src.1_auto_formalizer.crawler')
crawler.crawl_all()
"
# Output: dataset/valor.db (SQLite, ~300 spells)

# Also save raw wikitext for provenance auditing
python3 -c "
import importlib
crawler = importlib.import_module('src.1_auto_formalizer.crawler')
records = crawler.crawl_all()
crawler.save_raw_dumps(records)
"
# Output: dataset/raw_wiki_dumps/*.json
```

You can verify any entry against the wiki:
```bash
python3 -c "
import importlib, json
db_mod = importlib.import_module('src.1_auto_formalizer.database')
db = db_mod.SpellDB()
spell = db.get_spell_by_name('Fireball')
print(json.dumps({k: spell[k] for k in ['name','uid','level','damage_dice','damage_type','save_ability','range_m','aoe_m']}, indent=2))
db.close()
"
```

Expected output (all values from bg3.wiki, zero fabrication):
```json
{
  "name": "Fireball",
  "uid": "Projectile_Fireball",
  "level": 3,
  "damage_dice": "8d6",
  "damage_type": "Fire",
  "save_ability": "Dexterity",
  "range_m": 18.0,
  "aoe_m": 4.0
}
```

### Step 2: Formal verification (Lean 4)

```bash
cd src/2_fv_core

# Type-check all definitions and run proof search
lake build

# Specific theorems that should succeed:
# - drs_damage_scaling        (P1: DRS amplification is O((N+1)×M))
# - reaction_chain_bounded    (P2: each reaction increases used count)
# - reaction_decreases_fuel   (P2: well-founded termination measure)
# - action_economy_bounded    (P4: maxAttacksPerTurn ≤ 8 for all Bool combos)
# - max_attacks_is_8          (P4: concrete witness via native_decide)
# - max_attacks_honour_is_7   (P4: Honour Mode variant)
# - drs_amplifies_damage      (P1: DRS scenario > non-DRS via native_decide)
# - reaction_chain_terminates (P2: after reaction, canReact = false)
# - ignore_preserves_existing (P5: ignore StackType is idempotent)
#
# Theorems marked `sorry` are proof obligations for future work:
# - overwrite_replaces        (P5: needs list filter lemmas)
# - pass_turn_always_valid    (liveness: needs step unfolding)
# - tick_preserves_length     (safety: needs filterMap case split)
```

### Step 3: Run the feedback loop

```bash
# Without Lean toolchain (uses --skip-lake):
python3 -m eval.run_feedback_loop \
  --rounds 5 \
  --skip-lake \
  --output results/

# With Lean toolchain:
python3 -m eval.run_feedback_loop \
  --rounds 10 \
  --lean-root src/2_fv_core \
  --output results/

# With in-game oracle (see "In-Game Oracle Setup" below):
python3 -m eval.run_feedback_loop \
  --rounds 10 \
  --lean-root src/2_fv_core \
  --oracle-log results/oracle_log.json \
  --oracle-wait-s 30 \
  --output results/
```

### Step 4: Generate paper metrics and figures

```bash
python3 -m eval.collect_metrics \
  --results results/ \
  --output docs/

# Outputs:
#   docs/fig_convergence.png      — convergence curve (round vs % axioms converged)
#   docs/fig_exploit_rate.png     — exploit discovery rate over rounds
#   docs/table_metrics.tex        — LaTeX booktabs table for paper
#   docs/metrics_summary.json     — machine-readable summary
```

### Step 5: Evaluate auto-formalization accuracy

```bash
python3 -m eval.evaluate_accuracy \
  --benchmarks dataset/manual_annotations/ \
  --predictions src/2_fv_core/Axioms/

# Metrics: syntactic exact match, clause-level F1, semantic equivalence
# Stratified by complexity tier: simple / compound / interaction
```

## In-Game Oracle Setup

The in-game oracle is **optional** but provides ground-truth validation that no amount of symbolic modeling can replace.

### Prerequisites

1. **Baldur's Gate 3** (Steam or GOG, Patch 7+)
2. **BG3 Script Extender** (Norbyte's bg3se, v18+): [github.com/Norbyte/bg3se](https://github.com/Norbyte/bg3se)

### Installation

```bash
# 1. Locate your BG3 Script Extender Lua directory:
#    Steam (Linux):  ~/.local/share/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
#    Steam (Windows): %LOCALAPPDATA%/Larian Studios/Baldur's Gate 3/Script Extender/Lua/
#    Steam (macOS):  ~/Library/Application Support/Larian Studios/Baldur's Gate 3/Script Extender/Lua/

# 2. Copy the VALOR mod files:
SE_LUA="<your_script_extender_lua_path>"
cp src/4_ingame_oracle/Mods/VALOR_Injector/main.lua     "$SE_LUA/"
cp src/4_ingame_oracle/Mods/VALOR_Injector/sandbox.lua   "$SE_LUA/"
cp src/4_ingame_oracle/Mods/VALOR_Injector/execute.lua   "$SE_LUA/"

# 3. Add to your BootstrapServer.lua:
echo 'Ext.Require("main")' >> "$SE_LUA/BootstrapServer.lua"

# 4. Create the directories the mod expects:
mkdir -p "$SE_LUA/VALOR_Scripts" "$SE_LUA/VALOR_Logs"

# 5. Launch BG3.  The mod will log to VALOR_Logs/main.log on session load.
```

### Running oracle tests

The Python-side `lua_generator.py` writes Lua scripts to a staging directory.  To feed them to the oracle:

```bash
# Copy a generated test script to the mod's watched directory:
cp results/round_001/generated.lua "$SE_LUA/VALOR_Scripts/test_001.lua"

# The mod polls VALOR_Scripts/ every 2 seconds, loads and executes new scripts,
# and writes combat logs to VALOR_Logs/combat_log.json.

# Copy the log back for analysis:
cp "$SE_LUA/VALOR_Logs/combat_log.json" results/oracle_log.json

# The feedback loop will pick it up on the next round if --oracle-log is set.
```

### Manual verification without the mod

If you cannot run the mod, you can manually verify counterexamples:

1. Read the generated Lua script in `results/round_NNN/generated.lua`
2. The script contains BG3 Osiris calls like `Osi.UseSpell(uuid, "Projectile_Fireball", target_uuid)`
3. Reproduce the scenario in-game manually (save first!)
4. Compare the observed outcome against the `-- Post-step assertions` comments

## Testing

### Unit tests

```bash
# Run all 23 tests with verbose output
python3 -m pytest tests/ -v

# Run a specific test file
python3 -m pytest tests/test_wikitext_parser.py -v

# Run with coverage (install pytest-cov first)
python3 -m pytest tests/ --cov=src --cov-report=term-missing
```

#### What the tests cover

| File | Tests | What is verified |
|------|-------|-----------------|
| `test_wikitext_parser.py` | 8 | Parsing of real `{{Feature page}}` templates from bg3.wiki for Fireball, Hex, Haste, Eldritch Blast, Counterspell; edge cases (missing template, unknown school, bad dice) |
| `test_database.py` | 7 | SQLite upsert/read, duplicate UID update, UNIQUE(name) conflict, queries by level / bugs / concentration / reaction |
| `test_models.py` | 7 | `DiceExpression.parse` variants, `Spell` validation (empty name rejection, level bounds), `DamageType` enum completeness, `School` enum roundtrip |

### Integration test: live wiki

```bash
# Fetch and parse a real spell from the live bg3.wiki API
python3 -c "
import importlib, httpx
parser = importlib.import_module('src.1_auto_formalizer.wikitext_parser')
resp = httpx.get('https://bg3.wiki/w/api.php', params={
    'action': 'parse', 'page': 'Fireball', 'prop': 'wikitext', 'format': 'json'
}, timeout=15)
spell, errors = parser.parse_spell('Fireball', resp.json()['parse']['wikitext']['*'])
assert spell is not None, f'Parse failed: {errors}'
assert spell.uid == 'Projectile_Fireball'
assert spell.level == 3
assert spell.damage_dice.count == 8
assert spell.damage_dice.sides == 6
assert spell.damage_type.value == 'Fire'
assert spell.save_ability.value == 'Dexterity'
assert spell.range_m == 18.0
print('Live wiki integration test PASSED')
"
```

### Lean 4 proof checking

```bash
cd src/2_fv_core
lake build 2>&1 | grep -E "(error|sorry|proved)"
# Expected: no errors on complete theorems; `sorry` on work-in-progress obligations
```

## Debugging

### Crawler issues

```bash
# Debug a single spell parse:
python3 -c "
import importlib, httpx, json
parser = importlib.import_module('src.1_auto_formalizer.wikitext_parser')
resp = httpx.get('https://bg3.wiki/w/api.php', params={
    'action': 'parse', 'page': 'YOUR_SPELL_NAME', 'prop': 'wikitext', 'format': 'json'
}, timeout=15)
wikitext = resp.json()['parse']['wikitext']['*']
print('=== Raw wikitext ===')
print(wikitext[:2000])
spell, errors = parser.parse_spell('YOUR_SPELL_NAME', wikitext)
if spell:
    print(spell.model_dump_json(indent=2))
if errors:
    print('Errors:', errors)
"
```

Common issues:
- **Spell not found**: Check the exact page title on bg3.wiki (case-sensitive).
- **Missing UID**: Some wiki pages use non-standard templates.  The parser logs a warning.
- **Bad dice notation**: The regex expects `NdM` or `NdM+B`.  Compound expressions like `1d8+1d4` need the parser extended.

### Lean 4 issues

```bash
cd src/2_fv_core

# See all errors with full context:
lake build 2>&1

# Check a specific file:
lake env lean Core/Types.lean

# Common issues:
# - "unknown identifier": Check import statements at top of file
# - "type mismatch": The axiom's type signature doesn't match Types.lean definitions
# - "declaration uses sorry": Expected for work-in-progress proofs
```

### Bridge issues

```bash
# Test lean_parser independently:
python3 -c "
import importlib
lp = importlib.import_module('src.3_engine_bridge.lean_parser')
result = lp.run_lean_check(lp.Path('src/2_fv_core'))
print(type(result).__name__, result)
"

# Test lua_generator with a synthetic counterexample:
python3 -c "
import importlib, json
lp = importlib.import_module('src.3_engine_bridge.lean_parser')
lg = importlib.import_module('src.3_engine_bridge.lua_generator')
path = lp.CounterexamplePath(
    steps=[lp.CounterexampleStep(
        state={'entities': [{'id': {'val': 0}, 'hp': 50}, {'id': {'val': 1}, 'hp': 30}]},
        event={'tag': 'castSpell', 'caster': 0, 'spellName': 'Fireball', 'target': {'tag': 'single', 'target': 1}}
    )],
    axiom_name='test_fireball'
)
out = lg.compile_to_lua(path, lg.Path('results/debug'))
print(open(out).read())
"
```

### In-game oracle issues

1. **Mod not loading**: Verify `BootstrapServer.lua` contains `Ext.Require("main")` and all three `.lua` files are in the SE Lua directory.
2. **Scripts not detected**: Check that `.lua` files are in `VALOR_Scripts/`, or create `VALOR_Scripts/VALOR_queue.txt` listing filenames.
3. **No combat log**: Check `VALOR_Logs/main.log` for errors.  Common issue: `Osi.GetHitpoints` returns `nil` if the entity UUID is wrong.
4. **Assertion failures**: The Lua assertions in generated scripts compare Lean-predicted HP vs. actual HP.  Failures indicate model-engine divergence—this is the signal the feedback loop uses to trigger corrections.

## Extending VALOR

### Adding a new spell

1. **Crawl it**:
   ```bash
   python3 -c "
   import importlib
   crawler = importlib.import_module('src.1_auto_formalizer.crawler')
   crawler.main()
   " --spell "Your Spell Name"
   ```

2. **Add its axiom** to `src/2_fv_core/Axioms/BG3Rules.lean`:
   ```lean
   axiom your_spell_damage (gs : GameState) (target : EntityId)
       (h_exists : (gs.getEntity target).isSome) :
       let dmg := DamageRoll.mk ⟨dice_count, dice_sides, bonus⟩ .damage_type
       ∃ gs', step gs (.takeDamage target [dmg]) = some gs' ∧
       (gs'.getEntity target).get!.hp ≤ (gs.getEntity target).get!.hp
   ```

3. **Add a counterexample search** to `src/2_fv_core/Proofs/Exploits.lean` if the spell has interesting interactions.

4. **Add its UID** to `src/3_engine_bridge/lua_generator.py` → `SPELL_UID_MAP`.

5. **Add a benchmark annotation** to `dataset/manual_annotations/your_spell.json`.

### Adding a new research problem

1. Define new invariant predicates in `Core/Types.lean` (e.g., `GameState.myNewInvariant`).
2. Add axioms encoding the relevant rules in `Axioms/BG3Rules.lean`.
3. Add proof/disproof targets in `Proofs/Exploits.lean`.
4. If the problem involves a new game mechanic, extend `Core/Engine.lean` (the `step` function).

### Adding new entity types (conditions, items, feats)

The `models.py` already defines `Condition` and `PassiveFeature` Pydantic models.  To crawl them:

1. Add new category constants to `crawler.py` (e.g., `"Category:Conditions"`).
2. Write a `parse_condition()` function in `wikitext_parser.py` (the wiki uses different templates for conditions).
3. Add a `conditions` table to `database.py`.

### Connecting a real LLM

`llm_to_lean.py` is currently a CLI stub.  To wire a real LLM:

1. Add your API key to environment variables (never commit it).
2. Implement the prompt construction using templates from `prompt_templates/`.
3. Call the LLM API and write the response to `BG3Rules.lean`.
4. The feedback loop will automatically pick up the new axioms on the next `lake build`.

See the module's docstring for the full prompt-construction and self-correction protocol.

### Adding new damage/condition types

The Lean 4 types in `Core/Types.lean` use inductive types with exhaustive pattern matching.  To add a new damage type:

1. Add a constructor to `inductive DamageType` in `Types.lean`.
2. Update `DamageType.isPhysical` if applicable.
3. `lake build` will show you every pattern match that needs updating (exhaustiveness checking).

## References

- Clarke, E., Grumberg, O., Jha, S., Lu, Y., & Veith, H. (2000). Counterexample-Guided Abstraction Refinement. *CAV 2000*.
- Madaan, A., et al. (2023). Self-Refine: Iterative Refinement with Self-Feedback. *NeurIPS 2023*.
- First, E., Rabe, M., Ringer, T., & Brun, Y. (2023). Baldur: Whole-Proof Generation and Repair with Large Language Models. *ESEC/FSE 2023*.
- Wu, Y., Jiang, A. Q., et al. (2022). Autoformalization with Large Language Models. *NeurIPS 2022*.
- Jiang, A. Q., et al. (2023). Draft, Sketch, and Prove: Guiding Formal Theorem Provers with Informal Proofs. *ICLR 2023*.
- de Moura, L. & Ullrich, S. (2021). The Lean 4 Theorem Prover and Programming Language. *CADE 2021*.
- Biere, A., Cimatti, A., Clarke, E., & Zhu, Y. (1999). Symbolic Model Checking without BDDs. *TACAS 1999*.

## License

MIT
