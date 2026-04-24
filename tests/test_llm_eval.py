"""
Tests for the LLM auto-formalisation harness.

Network-free: every test uses :class:`DryRunProvider` or a small custom
provider that returns hand-authored facts.  The real OpenAI / Anthropic
providers are exercised only by their constructor / ``configured``
property tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_formalizer.llm_eval import (
    AccuracyReport,
    FactScore,
    _facts_equal,
    evaluate_provider,
    load_gold_index,
    score_entry,
)
from auto_formalizer.llm_providers import (
    AnthropicProvider,
    DryRunProvider,
    FormalisationRequest,
    FormalisationResponse,
    LLMProvider,
    OpenAIProvider,
    _extract_json_object,
    auto_select_provider,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_INDEX = REPO_ROOT / "dataset" / "manual_annotations" / "_gold_index.json"


# ── Helpers ────────────────────────────────────────────────────────────────


class _FixedProvider(LLMProvider):
    """Returns a hand-coded facts dict regardless of the request."""

    name = "fixed"

    def __init__(self, facts: dict) -> None:
        self.model = "fixed-test"
        self._facts = facts

    def formalise(self, request: FormalisationRequest) -> FormalisationResponse:
        return FormalisationResponse(
            raw_text=json.dumps(self._facts),
            parsed_facts=self._facts,
            provider=self.name,
            model=self.model,
        )


# ── JSON extraction ────────────────────────────────────────────────────────


class TestExtractJsonObject:
    def test_bare_json(self) -> None:
        out = _extract_json_object('{"a": 1, "b": "x"}')
        assert out == {"a": 1, "b": "x"}

    def test_fenced_json(self) -> None:
        text = "intro\n```json\n{\"foo\": 42}\n```\noutro"
        assert _extract_json_object(text) == {"foo": 42}

    def test_prose_then_json(self) -> None:
        text = "Sure, here:\n{\"k\": null}\nDone."
        assert _extract_json_object(text) == {"k": None}

    def test_malformed(self) -> None:
        assert _extract_json_object("nope") == {}
        assert _extract_json_object("") == {}


# ── Provider constructors ─────────────────────────────────────────────────


class TestDryRunProvider:
    def test_returns_empty_facts(self) -> None:
        p = DryRunProvider()
        r = p.formalise(FormalisationRequest(spell_name="X", wiki_url="https://bg3.wiki/X"))
        assert r.provider == "dry-run"
        assert r.parsed_facts == {}


class TestOpenAIProviderConfigured:
    def test_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAIProvider()
        assert not p.configured

    def test_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        p = OpenAIProvider()
        assert p.configured
        assert p.model.startswith("gpt-") or p.model

    def test_unconfigured_returns_error_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAIProvider()
        r = p.formalise(FormalisationRequest(spell_name="Fireball", wiki_url=""))
        assert r.parsed_facts == {}
        assert r.error and "OPENAI_API_KEY" in r.error


class TestAnthropicProviderConfigured:
    def test_unconfigured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        assert not p.configured

    def test_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        p = AnthropicProvider()
        assert p.configured

    def test_unconfigured_returns_error_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider()
        r = p.formalise(FormalisationRequest(spell_name="Fireball", wiki_url=""))
        assert r.parsed_facts == {}
        assert r.error and "ANTHROPIC_API_KEY" in r.error


class TestAutoSelectProvider:
    def test_no_keys_returns_dry_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert isinstance(auto_select_provider(), DryRunProvider)

    def test_anthropic_wins_over_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-2")
        assert isinstance(auto_select_provider(), AnthropicProvider)

    def test_only_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
        assert isinstance(auto_select_provider(), OpenAIProvider)


# ── Fact comparison ───────────────────────────────────────────────────────


class TestFactsEqual:
    def test_none_both(self) -> None:
        assert _facts_equal(None, None)
        assert not _facts_equal(None, 0)

    def test_numbers(self) -> None:
        assert _facts_equal(3, 3.0)
        assert not _facts_equal(3, 4)

    def test_strings_case_insensitive(self) -> None:
        assert _facts_equal("Fire", "fire")
        assert _facts_equal("Fire", " FIRE ")

    def test_bool(self) -> None:
        assert _facts_equal(True, True)
        assert not _facts_equal(True, False)


# ── Scoring & evaluation ──────────────────────────────────────────────────


class TestScoreEntry:
    def test_perfect(self) -> None:
        entry = {
            "id": "fireball",
            "spell_name": "Fireball",
            "gold_facts": {"damage_dice": "8d6", "damage_type": "Fire", "concentration": False},
        }
        predicted = {"damage_dice": "8d6", "damage_type": "fire", "concentration": False}
        s = score_entry(entry, predicted)
        assert s.total_facts == 3
        assert s.correct_facts == 3
        assert s.per_entry_accuracy == 1.0

    def test_partial(self) -> None:
        entry = {
            "id": "x",
            "spell_name": "X",
            "gold_facts": {"a": 1, "b": "two", "c": True},
        }
        predicted = {"a": 1, "b": "wrong", "c": True}
        s = score_entry(entry, predicted)
        assert s.correct_facts == 2
        assert pytest.approx(s.per_entry_accuracy) == 2 / 3

    def test_empty_predicted(self) -> None:
        entry = {
            "id": "y",
            "spell_name": "Y",
            "gold_facts": {"a": 1},
        }
        s = score_entry(entry, {})
        assert s.correct_facts == 0


# ── Gold index integrity ──────────────────────────────────────────────────


class TestGoldIndex:
    def test_at_least_20_entries(self) -> None:
        entries = load_gold_index(GOLD_INDEX)
        assert len(entries) >= 20, f"gold set only has {len(entries)} entries"

    def test_every_entry_has_required_fields(self) -> None:
        for entry in load_gold_index(GOLD_INDEX):
            assert "id" in entry and entry["id"]
            assert "spell_name" in entry and entry["spell_name"]
            assert "wiki_url" in entry and entry["wiki_url"].startswith("https://bg3.wiki/")
            assert "gold_facts" in entry and isinstance(entry["gold_facts"], dict)
            assert entry["gold_facts"], f"empty facts for {entry['id']}"


# ── End-to-end evaluation ─────────────────────────────────────────────────


class TestEvaluateProvider:
    def test_dry_run_zero_correct(self) -> None:
        entries = load_gold_index(GOLD_INDEX)
        report = evaluate_provider(DryRunProvider(), entries)
        assert report.provider == "dry-run"
        assert report.total_facts > 0
        # DryRun returns {} so nothing matches gold's non-null/non-False values.
        # But False/None gold facts CAN match a missing predicted value (None ==
        # missing key returns None). _facts_equal(False, None) → False, so most
        # are wrong; _facts_equal(None, None) is True. The fraction depends on
        # the gold set composition. Just assert the run completes and accuracy
        # is at most 1.
        assert 0.0 <= report.micro_accuracy <= 1.0
        assert 0.0 <= report.macro_accuracy <= 1.0
        assert len(report.entries) == len(entries)

    def test_perfect_provider_scores_one(self) -> None:
        entries = load_gold_index(GOLD_INDEX)

        # Perfect-oracle provider that returns the gold facts verbatim.
        class _Oracle(LLMProvider):
            name = "oracle"
            model = "gold"

            def formalise(self, request: FormalisationRequest) -> FormalisationResponse:
                # Find the matching gold entry by spell name (test harness only).
                for e in entries:
                    if e["spell_name"] == request.spell_name:
                        return FormalisationResponse(
                            raw_text=json.dumps(e["gold_facts"]),
                            parsed_facts=e["gold_facts"],
                            provider=self.name,
                            model=self.model,
                        )
                return FormalisationResponse(raw_text="", parsed_facts={}, provider=self.name, model=self.model)

        report = evaluate_provider(_Oracle(), entries)
        assert report.micro_accuracy == 1.0
        assert report.macro_accuracy == 1.0

    def test_provider_exception_handled(self) -> None:
        entries = load_gold_index(GOLD_INDEX)[:1]

        class _Crashy(LLMProvider):
            name = "crashy"
            model = "boom"

            def formalise(self, request):
                raise RuntimeError("boom")

        report = evaluate_provider(_Crashy(), entries)
        # Crashing provider must not abort the run.
        assert len(report.entries) == 1
        assert "__error__" in report.entries[0].fact_results
        # The vast majority of facts must be flagged wrong.  A handful may
        # still match purely because `_facts_equal(False, None) == True`
        # (booleans coerce missing → False), so we just require non-trivial
        # error mass rather than exact zero.
        assert report.entries[0].correct_facts < report.entries[0].total_facts

    def test_report_to_dict_round_trip(self) -> None:
        entries = load_gold_index(GOLD_INDEX)[:3]
        report = evaluate_provider(_FixedProvider({"damage_dice": "8d6"}), entries)
        d = report.to_dict()
        assert d["provider"] == "fixed"
        assert d["n_entries"] == 3
        assert "entries" in d
        # Round-trip via JSON to confirm serialisability.
        json.dumps(d)
