# VALOR — Verified Automated Loop for Oracle-driven Rule-checking

> **A Neuro-Symbolic Closed-Loop Formal Verification Framework for Game Mechanics**

## Overview

VALOR couples large-language-model-driven auto-formalization with Lean 4 theorem
proving to discover, verify, and patch balance-breaking exploits in the combat
system of *Baldur's Gate 3*.  The framework implements a four-stage closed loop:

```
 ┌──────────────────────────────────────────────────────────┐
 │  1. Auto-Formalizer (Neural)                             │
 │     LLM translates wiki prose → Lean 4 axioms           │
 └────────────────┬─────────────────────────────────────────┘
                  │  Lean 4 source
                  ▼
 ┌──────────────────────────────────────────────────────────┐
 │  2. FV Core (Symbolic)                                   │
 │     Lean 4 type-checks axioms, searches counter-examples │
 └────────────────┬─────────────────────────────────────────┘
                  │  Counterexample path
                  ▼
 ┌──────────────────────────────────────────────────────────┐
 │  3. Engine Bridge (Communication)                        │
 │     Compiles counter-example → executable Lua script     │
 └────────────────┬─────────────────────────────────────────┘
                  │  Lua injection script
                  ▼
 ┌──────────────────────────────────────────────────────────┐
 │  4. In-Game Oracle (Execution)                           │
 │     BG3 mod executes script, returns combat log          │
 └────────────────┬─────────────────────────────────────────┘
                  │  Execution log
                  ▼
            ┌───────────┐
            │ Evaluator  │──→  LLM corrects axioms  ──→  back to step 1
            └───────────┘
```

## Repository Layout


| Path                     | Layer         | Description                                      |
| ------------------------ | ------------- | ------------------------------------------------ |
| `dataset/`               | Ground Truth  | Raw wiki dumps & hand-annotated spell benchmarks |
| `src/1_auto_formalizer/` | Neural        | LLM-driven wiki → Lean 4 translation             |
| `src/2_fv_core/`         | Symbolic      | Lean 4 type system, axioms & proof search        |
| `src/3_engine_bridge/`   | Communication | Lean ↔ Lua bidirectional compiler                |
| `src/4_ingame_oracle/`   | Execution     | BG3 mod for in-vivo test execution               |
| `eval/`                  | Evaluation    | Accuracy, convergence & metric scripts           |
| `docs/`                  | Documentation | LaTeX figures, architecture diagrams             |


## Quick Start

```bash
# 1. Crawl wiki and auto-formalize
python src/1_auto_formalizer/crawler.py
python src/1_auto_formalizer/llm_to_lean.py

# 2. Type-check and prove in Lean 4
cd src/2_fv_core && lake build

# 3. Compile counterexamples to Lua
python src/3_engine_bridge/lean_parser.py
python src/3_engine_bridge/lua_generator.py

# 4. Run the full feedback loop
python eval/run_feedback_loop.py --rounds 10
```

## Citation

```bibtex
@inproceedings{valor2026,
  title   = {VALOR: Verified Automated Loop for Oracle-driven Rule-checking
             in Game Combat Systems},
  author  = {TBD},
  year    = {2026},
}
```

## License

MIT