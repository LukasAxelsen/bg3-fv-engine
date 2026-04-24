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

try:
    from .llm_eval import evaluate_provider, load_gold_index
    from .llm_providers import (
        DryRunProvider,
        FormalisationRequest,
        LLMProvider,
        auto_select_provider,
    )
except ImportError:  # pragma: no cover - flat layout invocation
    from llm_eval import evaluate_provider, load_gold_index  # type: ignore[no-redef]
    from llm_providers import (  # type: ignore[no-redef]
        DryRunProvider,
        FormalisationRequest,
        LLMProvider,
        auto_select_provider,
    )


def _select_provider(name: str) -> LLMProvider:
    if name == "openai":
        from .llm_providers import OpenAIProvider  # local import keeps deps lazy

        return OpenAIProvider()
    if name == "anthropic":
        from .llm_providers import AnthropicProvider

        return AnthropicProvider()
    if name == "dry-run":
        return DryRunProvider()
    return auto_select_provider()


def main(argv: list[str] | None = None) -> int:
    """
    CLI for the LLM auto-formalisation stage.

    Three modes:

    * ``formalize`` — call the configured LLM provider on a single spell.
    * ``correct``   — re-call the LLM with a counter-example correction
      hint (currently passes the hint as ``extra_context``).
    * ``eval``      — run the provider against the entire gold index and
      print a one-line accuracy summary; optionally write the full report
      as JSON for ``eval/collect_metrics.py`` to pick up.

    No mode raises if the provider has no API key; instead the active
    provider falls back to :class:`DryRunProvider` and the call still
    returns ``0`` so orchestration can continue.
    """
    p = argparse.ArgumentParser(description="LLM → Lean auto-formaliser.")
    p.add_argument("--round", type=int, default=0, help="Feedback-loop round index")
    p.add_argument(
        "--mode",
        choices=("formalize", "correct", "eval"),
        default="eval",
        help="What to do this invocation",
    )
    p.add_argument(
        "--provider",
        choices=("auto", "openai", "anthropic", "dry-run"),
        default="auto",
        help="Which LLM backend to use; 'auto' picks based on env vars.",
    )
    p.add_argument(
        "--spell",
        type=str,
        default=None,
        help="Spell name (formalize/correct mode).",
    )
    p.add_argument(
        "--wiki-url",
        type=str,
        default="",
        help="Wiki URL for the spell (formalize/correct mode).",
    )
    p.add_argument(
        "--state-json",
        type=Path,
        default=None,
        help="Optional path to read/write loop state hints",
    )
    p.add_argument(
        "--gold-index",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "dataset"
        / "manual_annotations"
        / "_gold_index.json",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="Where to write the eval report (eval mode only).",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    log = logging.getLogger("llm_to_lean")

    provider = _select_provider(args.provider)
    log.info("provider=%s model=%s mode=%s round=%s", provider.name, provider.model, args.mode, args.round)

    if args.mode == "eval":
        entries = load_gold_index(args.gold_index)
        report = evaluate_provider(provider, entries)
        print(report.summary())
        if args.out_json:
            args.out_json.parent.mkdir(parents=True, exist_ok=True)
            args.out_json.write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("wrote %s", args.out_json)
        return 0

    if args.mode in {"formalize", "correct"}:
        if not args.spell:
            print("error: --spell is required for formalize/correct mode", file=sys.stderr)
            return 2
        extra = ""
        if args.state_json and args.state_json.exists():
            extra = args.state_json.read_text(encoding="utf-8")
        request = FormalisationRequest(
            spell_name=args.spell,
            wiki_url=args.wiki_url,
            extra_context=extra,
        )
        response = provider.formalise(request)
        if response.error:
            log.warning("provider error: %s", response.error)
        print(json.dumps({
            "provider": response.provider,
            "model": response.model,
            "spell": args.spell,
            "raw_text": response.raw_text,
            "parsed_facts": dict(response.parsed_facts),
            "error": response.error,
        }, indent=2, ensure_ascii=False))
        return 0

    return 0  # unreachable


if __name__ == "__main__":  # pragma: no cover - module-as-script
    raise SystemExit(main())
