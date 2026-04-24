"""
Register ``src/1_auto_formalizer`` and ``src/3_engine_bridge`` as importable
packages despite their digit-prefixed directory names.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]

_PACKAGES: dict[str, tuple[Path, list[tuple[str, str]]]] = {
    "auto_formalizer": (
        _ROOT / "src" / "1_auto_formalizer",
        [
            ("models", "models.py"),
            ("wikitext_parser", "wikitext_parser.py"),
            ("database", "database.py"),
            ("drs_lean_export", "drs_lean_export.py"),
            ("llm_providers", "llm_providers.py"),
            ("llm_eval", "llm_eval.py"),
        ],
    ),
    "engine_bridge": (
        _ROOT / "src" / "3_engine_bridge",
        [
            ("lean_parser", "lean_parser.py"),
            ("lua_generator", "lua_generator.py"),
            ("log_analyzer", "log_analyzer.py"),
            ("probability_scenarios", "probability_scenarios.py"),
        ],
    ),
}


def pytest_configure(config: pytest.Config) -> None:
    for pkg_name, (pkg_dir, submodules) in _PACKAGES.items():
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(pkg_dir)]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg

        for sub, fname in submodules:
            full = f"{pkg_name}.{sub}"
            if full in sys.modules and getattr(sys.modules[full], "__file__", None):
                continue
            spec = importlib.util.spec_from_file_location(full, pkg_dir / fname)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_name
            sys.modules[full] = mod
            spec.loader.exec_module(mod)
