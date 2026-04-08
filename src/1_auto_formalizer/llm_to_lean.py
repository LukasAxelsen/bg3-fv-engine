"""
llm_to_lean.py — LLM-Driven Auto-Formalization Engine
======================================================

Position in the VALOR Closed Loop
---------------------------------
This module is the **core neural component** of Stage 1 (Auto-Formalizer).
It receives structured game-rule records from ``crawler.py`` and produces
syntactically valid Lean 4 declarations that are written into
``src/2_fv_core/Axioms/BG3Rules.lean``:

    ┌──────────────┐   structured JSON   ┌───────────────┐
    │  crawler.py  │  ──────────────►    │ llm_to_lean.py│
    └──────────────┘                     │ (this file)   │
                                         └───────┬───────┘
                                                 │  Lean 4 source
                                                 ▼
                                         ┌───────────────┐
                                         │ 2_fv_core/    │
                                         │ Axioms/       │
                                         │ BG3Rules.lean │
                                         └───────────────┘

Responsibilities
----------------
1. **Prompt Construction**: Assemble few-shot prompts from the templates
   stored in ``prompt_templates/``.  Each prompt demonstrates how a
   natural-language rule maps to a Lean 4 ``theorem`` or ``axiom``
   declaration using the type vocabulary defined in
   ``2_fv_core/Core/Types.lean``.
2. **LLM Invocation**: Call a frontier LLM (Claude / GPT-4 class) via its
   API, requesting a Lean 4 code block as output.
3. **Syntax Pre-Validation**: Run a lightweight regex + AST check on the
   returned Lean fragment *before* writing it to disk.  This catches
   trivial formatting issues (unbalanced parentheses, missing ``:=``)
   and triggers an automatic retry with a corrective prompt.
4. **Feedback-Loop Integration**: When the downstream evaluator
   (``eval/run_feedback_loop.py``) detects a mismatch between the Lean
   model and the in-game oracle, it invokes this module again with
   - the original rule text,
   - the failing Lean axiom, and
   - the concrete counterexample from ``lean_parser.py``
   so the LLM can **self-correct** the axiom.  This is the "Correction"
   arc of the Lean → Lua → Oracle → Correction closed loop.

Design Rationale
----------------
Separating prompt templates from invocation logic allows ablation studies
over prompt engineering strategies (zero-shot, few-shot, chain-of-thought,
decomposed sub-task) without modifying the orchestration code—an important
consideration for reproducible top-venue experiments.

Academic Context
----------------
This module instantiates the *neural auto-formalizer* paradigm, where an
LLM acts as a noisy translator from natural language to a formal target
language.  The closed-loop self-correction mechanism draws on recent work
in LLM self-refinement (Madaan et al., "Self-Refine", NeurIPS 2023) and
interactive theorem-proving agents (First et al., 2023).

References
----------
- Madaan, A., et al. "Self-Refine: Iterative Refinement with
  Self-Feedback." NeurIPS 2023.
- First, E., et al. "Baldur: Whole-Proof Generation and Repair with
  Large Language Models." ESEC/FSE 2023.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """
    CLI stub for the closed feedback loop. Production runs wire an LLM here.

    Exits 0 so orchestration can proceed without API keys in CI.
    """
    p = argparse.ArgumentParser(description="LLM → Lean auto-formalizer (stub or future API).")
    p.add_argument("--round", type=int, default=0, help="Feedback-loop round index")
    p.add_argument(
        "--mode",
        choices=("formalize", "correct"),
        default="formalize",
        help="Initial formalization vs correction pass",
    )
    p.add_argument(
        "--state-json",
        type=Path,
        default=None,
        help="Optional path to read/write loop state hints",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    log = logging.getLogger("llm_to_lean")
    log.info("round=%s mode=%s (stub: no LLM call)", args.round, args.mode)
    if args.state_json and args.state_json.exists():
        log.debug("state keys: %s", list(json.loads(args.state_json.read_text()).keys()))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
