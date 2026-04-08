"""
Load ``src/1_auto_formalizer`` as importable package ``auto_formalizer``
(digit-prefixed directory name is not a valid Python module identifier).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_FORM = _ROOT / "src" / "1_auto_formalizer"


def pytest_configure(config: pytest.Config) -> None:
    pkg = types.ModuleType("auto_formalizer")
    pkg.__path__ = [str(_FORM)]  # type: ignore[attr-defined]
    sys.modules["auto_formalizer"] = pkg

    for sub, fname in (
        ("models", "models.py"),
        ("wikitext_parser", "wikitext_parser.py"),
        ("database", "database.py"),
    ):
        full = f"auto_formalizer.{sub}"
        if full in sys.modules and getattr(sys.modules[full], "__file__", None):
            continue
        spec = importlib.util.spec_from_file_location(full, _FORM / fname)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "auto_formalizer"
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
