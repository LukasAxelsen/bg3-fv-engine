"""
Parse combat logs from ``execute.lua`` and compare observed trajectories to Lean predictions.

This module closes the bridge loop: divergence reports feed back into axiom correction
when the in-game oracle disagrees with the symbolic witness.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

try:
    from .lean_parser import CounterexamplePath, CounterexampleStep
except ImportError:  # pragma: no cover
    from lean_parser import CounterexamplePath, CounterexampleStep

logger = logging.getLogger(__name__)


class DivergenceType(str, Enum):
    """Classification of oracle vs model disagreement."""

    ALIGNED = "aligned"
    VALUE_MISMATCH = "value_mismatch"
    MISSING_EVENT = "missing_event"
    EXTRA_EVENT = "extra_event"
    STATUS_MISMATCH = "status_mismatch"


@dataclass(frozen=True)
class DivergenceReport:
    """Single step-level diagnosis for the feedback loop (LLM / human review)."""

    step_index: int
    divergence_type: DivergenceType
    expected: str
    observed: str
    axiom_name: str | None


def _event_signature(ev: Mapping[str, Any]) -> str:
    tag = ev.get("tag")
    if isinstance(tag, str):
        return tag
    if len(ev) == 1:
        return str(next(iter(ev.keys())))
    return json.dumps(ev, sort_keys=True, default=str)


def _normalize_log_entries(raw_lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw_lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            logger.warning("Skipping non-JSON log line %d: %s", line_no, e)
    rows.sort(key=lambda r: int(r.get("step_index", -1)))
    return rows


def _slim_entities(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    entities = state.get("entities")
    out: list[dict[str, Any]] = []
    if not isinstance(entities, list):
        return out
    for e in entities:
        if not isinstance(e, Mapping):
            continue
        eid = e.get("id")
        vid: int | None = None
        if isinstance(eid, Mapping) and "val" in eid:
            vid = int(eid["val"])
        elif isinstance(eid, int):
            vid = eid
        conds = e.get("conditions") or []
        tags: list[str] = []
        if isinstance(conds, list):
            for c in conds:
                if isinstance(c, Mapping) and "tag" in c:
                    tags.append(str(c["tag"]))
        tags.sort()
        out.append(
            {
                "id": vid,
                "hp": e.get("hp"),
                "concentratingOn": e.get("concentratingOn"),
                "conditionTags": tags,
            }
        )
    out.sort(key=lambda x: (x["id"] is None, x["id"] or -1))
    return out


def _post_state_from_step(step: CounterexampleStep) -> dict[str, Any]:
    """Treat ``step.state`` as the post-state snapshot asserted after the step's event."""
    return {"entities": _slim_entities(step.state)}


def analyze_log(log_path: Path, expected_path: CounterexamplePath) -> DivergenceReport:
    """
    Align JSONL combat log entries with ``expected_path`` and return the first divergence.

    Log lines are expected to be objects with ``step_index``, ``event``, and ``post_state``
    (as produced by ``execute.lua``). When the log fully matches the predicted trajectory,
    returns ``DivergenceType.ALIGNED`` with ``step_index`` -1.
    """
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.error("Cannot read combat log %s: %s", log_path, e)
        raise

    entries = _normalize_log_entries(text.splitlines())
    axiom = expected_path.axiom_name

    if not expected_path.steps:
        if entries:
            extra = entries[0]
            return DivergenceReport(
                step_index=int(extra.get("step_index", 0)),
                divergence_type=DivergenceType.EXTRA_EVENT,
                expected="<empty predicted path>",
                observed=json.dumps(extra.get("event"), default=str),
                axiom_name=axiom,
            )
        return DivergenceReport(
            step_index=-1,
            divergence_type=DivergenceType.ALIGNED,
            expected="",
            observed="",
            axiom_name=axiom,
        )

    if len(entries) > len(expected_path.steps):
        extra = entries[len(expected_path.steps)]
        return DivergenceReport(
            step_index=int(extra.get("step_index", len(expected_path.steps))),
            divergence_type=DivergenceType.EXTRA_EVENT,
            expected="<end of predicted path>",
            observed=json.dumps(extra.get("event"), default=str),
            axiom_name=axiom,
        )

    if len(entries) < len(expected_path.steps):
        missing_idx = len(entries)
        exp_ev = expected_path.steps[missing_idx].event
        return DivergenceReport(
            step_index=missing_idx,
            divergence_type=DivergenceType.MISSING_EVENT,
            expected=json.dumps(exp_ev, default=str),
            observed="<log ended before this step>",
            axiom_name=axiom,
        )

    for i, (log_row, pred_step) in enumerate(zip(entries, expected_path.steps)):
        obs_ev = log_row.get("event")
        if not isinstance(obs_ev, Mapping):
            return DivergenceReport(
                step_index=i,
                divergence_type=DivergenceType.MISSING_EVENT,
                expected=_event_signature(pred_step.event),
                observed=str(obs_ev),
                axiom_name=axiom,
            )
        if _event_signature(obs_ev) != _event_signature(pred_step.event):
            return DivergenceReport(
                step_index=i,
                divergence_type=DivergenceType.EXTRA_EVENT,
                expected=json.dumps(pred_step.event, default=str),
                observed=json.dumps(obs_ev, default=str),
                axiom_name=axiom,
            )

        obs_post = log_row.get("post_state")
        if not isinstance(obs_post, Mapping):
            return DivergenceReport(
                step_index=i,
                divergence_type=DivergenceType.VALUE_MISMATCH,
                expected=json.dumps(_post_state_from_step(pred_step), default=str),
                observed=str(obs_post),
                axiom_name=axiom,
            )

        exp_snap = _post_state_from_step(pred_step)
        obs_snap = {"entities": _slim_entities(obs_post)}
        exp_list = exp_snap["entities"]
        obs_by_id: dict[int, dict[str, Any]] = {}
        for oe in obs_snap["entities"]:
            oid = oe.get("id")
            if isinstance(oid, int):
                obs_by_id[oid] = oe

        if len(exp_list) != len(obs_snap["entities"]):
            return DivergenceReport(
                step_index=i,
                divergence_type=DivergenceType.VALUE_MISMATCH,
                expected=json.dumps(exp_snap, default=str),
                observed=json.dumps(obs_snap, default=str),
                axiom_name=axiom,
            )

        for exp_ent in exp_list:
            eid = exp_ent.get("id")
            if not isinstance(eid, int):
                continue
            obs_ent = obs_by_id.get(eid)
            if obs_ent is None:
                return DivergenceReport(
                    step_index=i,
                    divergence_type=DivergenceType.VALUE_MISMATCH,
                    expected=json.dumps(exp_ent, default=str),
                    observed="<entity missing in observed post_state>",
                    axiom_name=axiom,
                )
            if exp_ent.get("hp") != obs_ent.get("hp"):
                return DivergenceReport(
                    step_index=i,
                    divergence_type=DivergenceType.VALUE_MISMATCH,
                    expected=json.dumps(exp_ent, default=str),
                    observed=json.dumps(obs_ent, default=str),
                    axiom_name=axiom,
                )
            if exp_ent.get("conditionTags") != obs_ent.get("conditionTags"):
                return DivergenceReport(
                    step_index=i,
                    divergence_type=DivergenceType.STATUS_MISMATCH,
                    expected=json.dumps(exp_ent.get("conditionTags"), default=str),
                    observed=json.dumps(obs_ent.get("conditionTags"), default=str),
                    axiom_name=axiom,
                )

    logger.info("Log aligned with predicted path (%d steps).", len(expected_path.steps))
    return DivergenceReport(
        step_index=-1,
        divergence_type=DivergenceType.ALIGNED,
        expected="",
        observed="",
        axiom_name=axiom,
    )
