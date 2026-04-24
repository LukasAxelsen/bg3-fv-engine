"""
Generate ``src/2_fv_core/Axioms/DRSItems.lean`` from
``dataset/drs_items_seed.json``.

The Lean file is committed to the repo so ``lake build`` works without
running this script — but a CI-side test (``tests/test_drs_ingest.py``)
asserts that the committed Lean file is byte-identical to what this script
would produce, preventing silent drift between the two ends.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = REPO_ROOT / "dataset" / "drs_items_seed.json"
DEFAULT_LEAN = REPO_ROOT / "src" / "2_fv_core" / "Axioms" / "DRSItems.lean"


def _lean_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _lean_dice(dice: dict[str, Any] | None) -> str:
    if dice is None:
        return "none"
    count = int(dice.get("count", 0))
    sides = int(dice.get("sides", 0))
    bonus = int(dice.get("bonus", 0))
    return f"some ⟨{count}, {sides}, {bonus}⟩"


def _lean_dmg_type(dmg: str | None) -> str:
    """Match the constructor names of ``VALOR.DamageType`` (lower-case)."""
    if not dmg:
        return "none"
    table = {
        "Acid": ".acid",
        "Bludgeoning": ".bludgeoning",
        "Cold": ".cold",
        "Fire": ".fire",
        "Force": ".force",
        "Lightning": ".lightning",
        "Necrotic": ".necrotic",
        "Piercing": ".piercing",
        "Poison": ".poison",
        "Psychic": ".psychic",
        "Radiant": ".radiant",
        "Slashing": ".slashing",
        "Thunder": ".thunder",
    }
    if dmg not in table:
        raise ValueError(f"Unknown damage type {dmg!r}")
    return f"some {table[dmg]}"


def _lean_layer(kind: str) -> str:
    table = {"DS": ".ds", "DR": ".dr", "DRS": ".drs"}
    if kind not in table:
        raise ValueError(f"Unknown layer kind {kind!r}")
    return table[kind]


def render_lean(seed: dict[str, Any]) -> str:
    """Render the entire ``Axioms/DRSItems.lean`` file as a string."""
    items = seed.get("items", [])
    provenance = seed.get("_provenance", {})

    header_lines = [
        "import Core.Types",
        "",
        "/-!",
        "# DRSItems.lean — DS / DR / DRS catalogue ingested from bg3.wiki",
        "",
        "**Auto-generated** by `src/1_auto_formalizer/drs_lean_export.py`",
        "from `dataset/drs_items_seed.json`.  Do not edit by hand; run the",
        "exporter and commit the regenerated file.  CI fails if this file",
        "drifts from the JSON seed.",
        "",
        f"Source URL: `{provenance.get('source_url', '')}`",
        f"Source section: `{provenance.get('source_section', '')}`",
        f"Extraction date: `{provenance.get('extraction_date', '')}`",
        "",
        "## Why this file exists",
        "",
        "The bridge needs a *machine-checkable* enumeration of every Damage",
        "Source / Damage Rider / DRS effect documented on bg3.wiki so that",
        "exploit-search theorems (`Proofs/Exploits.lean`) can be parameterised",
        "over the *real* item set rather than a hand-picked example.  The",
        "Honour-mode demotion flag captures the documented Patch 5 behaviour",
        "where most DRS effects are downgraded to plain DRs.",
        "-/",
        "",
        "namespace VALOR.DRSItems",
        "",
        "open VALOR",
        "",
        "/-- Three-tier classification used by bg3.wiki/wiki/Damage_Mechanics. -/",
        "inductive LayerKind where",
        "  | ds   -- Damage Source (acts on its own)",
        "  | dr   -- Damage Rider (only fires alongside a Source)",
        "  | drs  -- Damage Rider treated as a Source (re-attracts every Rider)",
        "  deriving DecidableEq, Repr",
        "",
        "/-- One catalogued layer entry. `riderDice` and `damageType` are",
        "    optional because a few items only document a flat damage value or",
        "    a non-numeric mechanic. -/",
        "structure Item where",
        "  name                : String",
        "  layerKind           : LayerKind",
        "  riderDice           : Option DiceExpr",
        "  damageType          : Option DamageType",
        "  honourDemotesToDR   : Bool",
        "  sourceCategory      : String",
        "  deriving Repr",
        "",
    ]
    item_lines: list[str] = []
    item_lines.append("/-- Curated list ingested from `dataset/drs_items_seed.json`. -/")
    item_lines.append("def all : List Item := [")
    last_idx = len(items) - 1
    for idx, item in enumerate(items):
        suffix = "" if idx == last_idx else ","
        item_lines.append(
            "  { name              := "
            + _lean_string(item["name"])
        )
        item_lines.append(
            "    layerKind         := " + _lean_layer(item["layer_kind"])
        )
        item_lines.append(
            "    riderDice         := " + _lean_dice(item.get("rider_dice"))
        )
        item_lines.append(
            "    damageType        := " + _lean_dmg_type(item.get("damage_type"))
        )
        item_lines.append(
            "    honourDemotesToDR := "
            + ("true" if item.get("honour_demotes_to_dr") else "false")
        )
        item_lines.append(
            "    sourceCategory    := "
            + _lean_string(item.get("source_category", ""))
            + " }"
            + suffix
        )
    item_lines.append("]")
    item_lines.append("")

    derived_lines = [
        "/-- Subset by classification. -/",
        "def byKind (k : LayerKind) : List Item :=",
        "  all.filter (fun i => decide (i.layerKind = k))",
        "",
        "def damageSources    : List Item := byKind .ds",
        "def damageRiders     : List Item := byKind .dr",
        "def damageRiderSrcs  : List Item := byKind .drs",
        "",
        "/-- Sum of worst-case rider damage across a list of items. -/",
        "def totalWorstCase (items : List Item) : Nat :=",
        "  items.foldl (fun acc i =>",
        "    match i.riderDice with",
        "    | some d => acc + d.count * d.sides + d.bonus.toNat",
        "    | none   => acc) 0",
        "",
        "/-- The full catalogue contains at least one DRS entry. -/",
        "theorem catalogue_has_drs : 0 < damageRiderSrcs.length := by",
        "  unfold damageRiderSrcs byKind all",
        "  decide",
        "",
        "/-- Honour mode demotes every catalogued DRS item to a plain DR — a",
        "    machine-checkable restatement of the wiki's documented Patch 5",
        "    behaviour. -/",
        "theorem all_drs_demoted_in_honour :",
        "    ∀ i ∈ damageRiderSrcs, i.honourDemotesToDR = true := by",
        "  unfold damageRiderSrcs byKind all",
        "  decide",
        "",
        "end VALOR.DRSItems",
        "",
    ]
    return "\n".join(header_lines + item_lines + derived_lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate Axioms/DRSItems.lean from the JSON seed.")
    p.add_argument("--seed", type=Path, default=DEFAULT_JSON)
    p.add_argument("--out", type=Path, default=DEFAULT_LEAN)
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if --out would change (CI / pre-commit hook).",
    )
    args = p.parse_args(argv)
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    new_text = render_lean(seed)
    if args.check:
        if not args.out.exists():
            print(f"DRIFT: {args.out} does not exist")
            return 1
        existing = args.out.read_text(encoding="utf-8")
        if existing != new_text:
            print(f"DRIFT: {args.out} is out of sync with {args.seed}")
            return 1
        print(f"OK: {args.out} matches {args.seed}")
        return 0
    args.out.write_text(new_text, encoding="utf-8")
    print(f"Wrote {args.out} ({len(seed.get('items', []))} items)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
