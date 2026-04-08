"""
Parse Lean 4 `lake build` output for the FV core and extract counterexample witnesses.

This module is the symbolic → bridge entrypoint: it classifies verification outcomes
and materializes witness traces for `lua_generator.py` and downstream oracle replay.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Union

logger = logging.getLogger(__name__)

# Lean-side tooling can embed a witness between these markers on stdout/stderr.
WITNESS_BEGIN = "VALOR_COUNTEREXAMPLE_JSON_BEGIN"
WITNESS_END = "VALOR_COUNTEREXAMPLE_JSON_END"

DEFAULT_LEAN_BUILD_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class CounterexampleStep:
    """One step of a witness: Lean ``GameState`` snapshot and the ``Event`` applied."""

    state: Mapping[str, Any]
    event: Mapping[str, Any]


@dataclass(frozen=True)
class CounterexamplePath:
    """Ordered witness trace from Lean (state, event) pairs plus optional provenance."""

    steps: list[CounterexampleStep]
    axiom_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProofSucceeded:
    """``lake build`` completed without a structured counterexample witness."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class CounterexampleFound:
    """A structured witness was present in the build output."""

    path: CounterexamplePath
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class LeanTypeError:
    """Lean type-check / elaboration failure (bridge classification: **TypeError**)."""

    message: str
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class Timeout:
    """Subprocess exceeded the configured wall-clock limit."""

    seconds: float
    partial_stdout: str = ""
    partial_stderr: str = ""


LeanResult = Union[ProofSucceeded, CounterexampleFound, LeanTypeError, Timeout]


def _extract_witness_json(text: str) -> dict[str, Any] | None:
    if WITNESS_BEGIN not in text or WITNESS_END not in text:
        return None
    try:
        start = text.index(WITNESS_BEGIN) + len(WITNESS_BEGIN)
        end = text.index(WITNESS_END, start)
    except ValueError:
        return None
    blob = text[start:end].strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        logger.warning("Witness JSON present but invalid: %s", e)
        return None


def _steps_from_payload(payload: Mapping[str, Any]) -> list[CounterexampleStep]:
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list):
        return []
    out: list[CounterexampleStep] = []
    for item in raw_steps:
        if not isinstance(item, Mapping):
            continue
        st = item.get("state")
        ev = item.get("event")
        if not isinstance(st, Mapping) or not isinstance(ev, Mapping):
            continue
        out.append(CounterexampleStep(state=dict(st), event=dict(ev)))
    return out


def _path_from_payload(payload: dict[str, Any]) -> CounterexamplePath | None:
    steps = _steps_from_payload(payload)
    if not steps:
        return None
    axiom = payload.get("axiom_name") or payload.get("axiom")
    axiom_str = axiom if isinstance(axiom, str) else None
    meta = {k: v for k, v in payload.items() if k not in ("steps", "axiom_name", "axiom")}
    return CounterexamplePath(steps=steps, axiom_name=axiom_str, metadata=meta)


def _looks_like_lean_type_error(combined: str, returncode: int) -> bool:
    if returncode == 0:
        return False
    lowered = combined.lower()
    needles = (
        "type mismatch",
        "typeclass instance problem",
        "unknown identifier",
        "failed to synthesize",
        "application type mismatch",
        "invalid field",
        "unexpected token",
    )
    return "error:" in lowered or any(n in lowered for n in needles)


def _lean_error_message(combined: str, max_chars: int = 8000) -> str:
    # Prefer last error block (often most specific).
    matches = list(re.finditer(r"(?:^|\n)(error:\s*.+?)(?=\n\n|\Z)", combined, re.DOTALL | re.MULTILINE))
    if matches:
        body = matches[-1].group(1).strip()
    else:
        body = combined.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "\n… (truncated)"
    return body


def run_lean_check(lean_root: Path, *, timeout_s: float = DEFAULT_LEAN_BUILD_TIMEOUT_S) -> LeanResult:
    """
    Run ``lake build`` in the Lean project root (directory containing ``lakefile.lean``).

    Classifies output into proof success, counterexample witness, type error, or timeout.
    Counterexample traces use ``CounterexampleStep`` rows of JSON ``state`` / ``event`` objects.
    """
    root = lean_root.resolve()
    if not root.is_dir():
        msg = f"lean_root is not a directory: {root}"
        logger.error(msg)
        return LeanTypeError(message=msg, stdout="", stderr="")

    lakefile = root / "lakefile.lean"
    if not lakefile.is_file():
        logger.warning("No lakefile.lean at %s — build will likely fail.", root)

    cmd = ["lake", "build"]
    logger.info("Running %s in %s (timeout=%ss)", " ".join(cmd), root, timeout_s)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        err = e.stderr or ""
        logger.error("lean build timed out after %ss", timeout_s)
        return Timeout(seconds=timeout_s, partial_stdout=out, partial_stderr=err)
    except OSError as e:
        msg = f"Failed to spawn lake build: {e}"
        logger.error("%s", msg)
        return LeanTypeError(message=msg, stdout="", stderr=str(e))

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined = f"{stdout}\n{stderr}"

    witness = _extract_witness_json(combined)
    if witness is not None:
        path = _path_from_payload(witness)
        if path is not None:
            logger.info("Counterexample witness: %d steps (axiom=%s)", len(path.steps), path.axiom_name)
            return CounterexampleFound(path=path, stdout=stdout, stderr=stderr)
        logger.warning("Witness JSON found but no valid steps; treating as ordinary build outcome.")

    if proc.returncode == 0:
        logger.info("lake build succeeded with no counterexample witness.")
        return ProofSucceeded(exit_code=proc.returncode, stdout=stdout, stderr=stderr)

    if _looks_like_lean_type_error(combined, proc.returncode):
        msg = _lean_error_message(combined)
        logger.error("Lean build failed (type/elab error). exit=%s", proc.returncode)
        return LeanTypeError(message=msg, stdout=stdout, stderr=stderr)

    msg = _lean_error_message(combined) or f"lake build failed with exit code {proc.returncode}"
    logger.error("Lean build failed: %s", msg[:200])
    return LeanTypeError(message=msg, stdout=stdout, stderr=stderr)
