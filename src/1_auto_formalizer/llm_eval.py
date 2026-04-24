"""
Accuracy evaluator for the LLM auto-formalisation stage.

Loads ``dataset/manual_annotations/_gold_index.json``, runs the
configured :class:`LLMProvider` on each entry, compares the model's
``parsed_facts`` to the gold facts, and reports per-fact / per-entry /
overall accuracy.

Used by both the standalone ``llm_to_lean`` CLI (``--eval``) and by
``eval/run_feedback_loop.py`` to fold accuracy into per-round metrics.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    from .llm_providers import (
        DryRunProvider,
        FormalisationRequest,
        LLMProvider,
        auto_select_provider,
    )
except ImportError:
    from llm_providers import (  # type: ignore[no-redef]
        DryRunProvider,
        FormalisationRequest,
        LLMProvider,
        auto_select_provider,
    )

logger = logging.getLogger(__name__)


@dataclass
class FactScore:
    """How well one entry's gold facts were reproduced by the model."""

    entry_id: str
    spell_name: str
    total_facts: int
    correct_facts: int
    fact_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def per_entry_accuracy(self) -> float:
        if self.total_facts == 0:
            return 1.0
        return self.correct_facts / self.total_facts


@dataclass
class AccuracyReport:
    provider: str
    model: str
    entries: list[FactScore] = field(default_factory=list)

    @property
    def total_facts(self) -> int:
        return sum(e.total_facts for e in self.entries)

    @property
    def correct_facts(self) -> int:
        return sum(e.correct_facts for e in self.entries)

    @property
    def micro_accuracy(self) -> float:
        if self.total_facts == 0:
            return 1.0
        return self.correct_facts / self.total_facts

    @property
    def macro_accuracy(self) -> float:
        if not self.entries:
            return 1.0
        return sum(e.per_entry_accuracy for e in self.entries) / len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "n_entries": len(self.entries),
            "total_facts": self.total_facts,
            "correct_facts": self.correct_facts,
            "micro_accuracy": round(self.micro_accuracy, 4),
            "macro_accuracy": round(self.macro_accuracy, 4),
            "entries": [asdict(e) for e in self.entries],
        }

    def summary(self) -> str:
        return (
            f"LLM eval [{self.provider} / {self.model}]: "
            f"micro={self.micro_accuracy:.3f} ({self.correct_facts}/{self.total_facts}) "
            f"macro={self.macro_accuracy:.3f} over {len(self.entries)} entries"
        )


def _facts_equal(gold: Any, predicted: Any) -> bool:
    """Permissive equality: numbers compare by value, strings case-insensitive."""
    if gold is None and predicted is None:
        return True
    if isinstance(gold, bool) or isinstance(predicted, bool):
        return bool(gold) == bool(predicted)
    if isinstance(gold, (int, float)) and isinstance(predicted, (int, float)):
        return float(gold) == float(predicted)
    if isinstance(gold, str) and isinstance(predicted, str):
        return gold.strip().lower() == predicted.strip().lower()
    return gold == predicted


def score_entry(entry: Mapping[str, Any], predicted: Mapping[str, Any]) -> FactScore:
    gold_facts = entry.get("gold_facts", {})
    fact_results: dict[str, dict[str, Any]] = {}
    correct = 0
    for key, gold_value in gold_facts.items():
        pred_value = predicted.get(key) if isinstance(predicted, Mapping) else None
        ok = _facts_equal(gold_value, pred_value)
        fact_results[key] = {"gold": gold_value, "predicted": pred_value, "correct": ok}
        if ok:
            correct += 1
    return FactScore(
        entry_id=entry["id"],
        spell_name=entry["spell_name"],
        total_facts=len(gold_facts),
        correct_facts=correct,
        fact_results=fact_results,
    )


def load_gold_index(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("entries", []))


def evaluate_provider(
    provider: LLMProvider,
    gold_entries: list[dict[str, Any]],
    *,
    wikitext_lookup: Mapping[str, str] | None = None,
) -> AccuracyReport:
    """Run ``provider`` against every gold entry and aggregate results."""
    report = AccuracyReport(provider=provider.name, model=provider.model)
    for entry in gold_entries:
        request = FormalisationRequest(
            spell_name=entry["spell_name"],
            wiki_url=entry.get("wiki_url", ""),
            wikitext=(wikitext_lookup or {}).get(entry["id"], ""),
        )
        try:
            response = provider.formalise(request)
        except Exception as e:
            logger.exception("Provider %s crashed on %s", provider.name, entry["id"])
            response_facts: Mapping[str, Any] = {}
            score = score_entry(entry, response_facts)
            score.fact_results["__error__"] = {"gold": None, "predicted": str(e), "correct": False}
            report.entries.append(score)
            continue
        report.entries.append(score_entry(entry, response.parsed_facts))
    return report


# ── CLI ───────────────────────────────────────────────────────────────────


def _build_argparser() -> "argparse.ArgumentParser":  # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(
        prog="llm_eval",
        description="Score auto-formalisation accuracy against the gold index.",
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
        "--provider",
        choices=["auto", "openai", "anthropic", "dry-run"],
        default="auto",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        help="Optional path to write the full report as JSON.",
    )
    return p


def _select_provider(name: str) -> LLMProvider:  # pragma: no cover
    if name == "openai":
        from .llm_providers import OpenAIProvider

        return OpenAIProvider()
    if name == "anthropic":
        from .llm_providers import AnthropicProvider

        return AnthropicProvider()
    if name == "dry-run":
        return DryRunProvider()
    return auto_select_provider()


def _cli_main(argv: list[str] | None = None) -> int:  # pragma: no cover
    args = _build_argparser().parse_args(argv)
    entries = load_gold_index(args.gold_index)
    provider = _select_provider(args.provider)
    report = evaluate_provider(provider, entries)
    print(report.summary())
    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli_main())
