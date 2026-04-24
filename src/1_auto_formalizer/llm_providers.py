"""
LLM provider abstractions for the auto-formalisation stage.

The neural half of "neuro-symbolic" historically lived as a stub
(``llm_to_lean.py`` returned 0).  This module replaces the stub with a
small, dependency-light provider interface plus three implementations:

* :class:`DryRunProvider` — purely deterministic; emits the input
  serialised back as JSON.  Used by the test suite, local development
  without an API key, and as the default in CI.
* :class:`OpenAIProvider` — POSTs to the OpenAI Chat Completions API
  (model configurable via ``OPENAI_MODEL``).  Activates when
  ``OPENAI_API_KEY`` is in the environment.
* :class:`AnthropicProvider` — POSTs to the Anthropic Messages API
  (model configurable via ``ANTHROPIC_MODEL``).  Activates when
  ``ANTHROPIC_API_KEY`` is in the environment.

The provider returns a :class:`FormalisationResponse` with the raw
model text plus a ``parsed_facts`` dict.  Callers (the evaluator,
:func:`run_feedback_loop`) treat the dict as the unit of truth — what
matters for accuracy is the extracted facts, not the surrounding prose.
"""

from __future__ import annotations

import abc
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormalisationRequest:
    """The unit of work submitted to a provider."""

    spell_name: str
    wiki_url: str
    wikitext: str = ""
    extra_context: str = ""

    def to_user_prompt(self) -> str:
        return (
            f"Spell name: {self.spell_name}\n"
            f"Wiki URL: {self.wiki_url}\n"
            f"Wiki text excerpt:\n{self.wikitext[:4000]}\n"
            + (f"\nExtra context:\n{self.extra_context}\n" if self.extra_context else "")
        )


@dataclass(frozen=True)
class FormalisationResponse:
    """Provider output.  ``parsed_facts`` is the canonical evaluation surface."""

    raw_text: str
    parsed_facts: Mapping[str, Any] = field(default_factory=dict)
    provider: str = "unknown"
    model: str = ""
    cost_usd: float = 0.0
    error: str | None = None


SYSTEM_PROMPT = """\
You are an auto-formaliser for the VALOR project.  Given a single BG3
spell description, output a single JSON object whose keys are the
mechanical facts about the spell.  Allowed keys (use the same
spelling exactly):

  spell_slot_level     int|null      Slot level 1..9, or null for cantrips/non-spells.
  school               string|null   Abjuration, Conjuration, Divination, Enchantment,
                                     Evocation, Illusion, Necromancy, Transmutation.
  damage_dice          string|null   "NdM" style, e.g. "8d6". null if the spell is non-damaging.
  damage_type          string|null   Acid, Bludgeoning, Cold, Fire, Force, Lightning,
                                     Necrotic, Piercing, Poison, Psychic, Radiant,
                                     Slashing, Thunder. null when irrelevant.
  save_ability         string|null   Strength, Dexterity, Constitution, Intelligence,
                                     Wisdom, Charisma. null if no save.
  on_save              string|null   "half", "negate", or null.
  requires_attack_roll bool          true if the spell hits via attack roll.
  casting_resource     string|null   "Action", "Bonus Action", "Reaction", or null.
  range_m              number|null   Range in metres.
  aoe_m                number|null   AoE radius / cone length / cube edge in metres.
  concentration        bool          Concentration spell?
  ritual               bool          Ritual?

Output ONLY the JSON object — no Markdown fence, no commentary.
"""


def _extract_json_object(text: str) -> Mapping[str, Any]:
    """Pull a top-level ``{...}`` JSON object out of ``text`` (tolerant of
    leading prose / ``\`\`\`json`` fences)."""
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return {}
        candidate = text[first : last + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, Mapping) else {}


# ── Provider interface ─────────────────────────────────────────────────────


class LLMProvider(abc.ABC):
    """Subclasses must implement :meth:`formalise`."""

    name: str = "abstract"
    model: str = ""

    @abc.abstractmethod
    def formalise(self, request: FormalisationRequest) -> FormalisationResponse:
        """Return a parsed formalisation response for ``request``."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(model={self.model!r})"


# ── DryRun provider (deterministic, no network) ───────────────────────────


class DryRunProvider(LLMProvider):
    """Echoes back a stub formalisation deterministically.

    Useful when no API key is available: lets the rest of the pipeline
    (evaluator, feedback-loop, metrics) run end-to-end so contributors
    can iterate on the harness without burning credits.
    """

    name = "dry-run"
    model = "echo"

    def formalise(self, request: FormalisationRequest) -> FormalisationResponse:
        # Minimal "look at the name" heuristics so the response isn't
        # *completely* useless: empty dict, but the provider is honest.
        facts: dict[str, Any] = {}
        return FormalisationResponse(
            raw_text=json.dumps(facts),
            parsed_facts=facts,
            provider=self.name,
            model=self.model,
        )


# ── OpenAI provider ───────────────────────────────────────────────────────


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._base_url = base_url
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def formalise(self, request: FormalisationRequest) -> FormalisationResponse:  # pragma: no cover - network
        if not self.configured:
            return FormalisationResponse(
                raw_text="",
                parsed_facts={},
                provider=self.name,
                model=self.model,
                error="OPENAI_API_KEY not set",
            )
        import httpx

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request.to_user_prompt()},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        try:
            r = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return FormalisationResponse(
                raw_text="",
                parsed_facts={},
                provider=self.name,
                model=self.model,
                error=f"http error: {e}",
            )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except Exception:
            text = ""
        return FormalisationResponse(
            raw_text=text,
            parsed_facts=_extract_json_object(text),
            provider=self.name,
            model=self.model,
        )


# ── Anthropic provider ────────────────────────────────────────────────────


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
        self._base_url = base_url
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def formalise(self, request: FormalisationRequest) -> FormalisationResponse:  # pragma: no cover - network
        if not self.configured:
            return FormalisationResponse(
                raw_text="",
                parsed_facts={},
                provider=self.name,
                model=self.model,
                error="ANTHROPIC_API_KEY not set",
            )
        import httpx

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": request.to_user_prompt()},
            ],
            "temperature": 0.0,
        }
        try:
            r = httpx.post(
                f"{self._base_url}/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return FormalisationResponse(
                raw_text="",
                parsed_facts={},
                provider=self.name,
                model=self.model,
                error=f"http error: {e}",
            )
        try:
            blocks = data.get("content", [])
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except Exception:
            text = ""
        return FormalisationResponse(
            raw_text=text,
            parsed_facts=_extract_json_object(text),
            provider=self.name,
            model=self.model,
        )


# ── Provider selection helper ─────────────────────────────────────────────


def auto_select_provider() -> LLMProvider:
    """Pick the best provider based on available env vars; defaults to dry-run."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider()
    return DryRunProvider()
