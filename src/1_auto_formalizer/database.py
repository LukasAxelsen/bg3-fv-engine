"""
database.py — SQLite Persistence Layer for Crawled Game Data
=============================================================

All crawled wiki data is stored in a local SQLite database.  SQLite was
chosen over a heavier RDBMS because:
 1. Zero deployment friction—critical for reproducibility.
 2. The dataset fits comfortably in a single file (<100 MB).
 3. Full-text search (FTS5) covers our query needs.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import CrawlRecord, DRSItem, Spell


_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "dataset" / "valor.db"


class SpellDB:
    """Thin wrapper around SQLite for VALOR crawl records."""

    def __init__(self, db_path: Path | str = _DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    # ── Schema ────────────────────────────────────────────────────────

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS spells (
                uid          TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                wiki_url     TEXT NOT NULL,
                level        INTEGER NOT NULL,
                school       TEXT,
                summary      TEXT,
                description  TEXT,
                damage_dice  TEXT,
                damage_type  TEXT,
                casting_resource TEXT,
                spell_slot_level INTEGER,
                requires_attack_roll INTEGER DEFAULT 0,
                save_ability TEXT,
                on_save      TEXT,
                range_m      REAL,
                aoe_m        REAL,
                aoe_shape    TEXT,
                concentration INTEGER DEFAULT 0,
                ritual       INTEGER DEFAULT 0,
                upcast_json  TEXT,
                conditions_json TEXT,
                spell_flags_json TEXT,
                classes_json TEXT,
                notes_json   TEXT,
                bugs_json    TEXT,
                raw_wikitext TEXT,
                crawled_at   TEXT NOT NULL,
                UNIQUE(name)
            );

            CREATE TABLE IF NOT EXISTS crawl_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                page_title   TEXT NOT NULL,
                page_id      INTEGER,
                entity_type  TEXT NOT NULL,
                success      INTEGER NOT NULL,
                errors_json  TEXT,
                crawled_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drs_items (
                name                  TEXT PRIMARY KEY,
                wiki_url              TEXT NOT NULL,
                layer_kind            TEXT NOT NULL,
                rider_dice            TEXT,
                damage_type           TEXT,
                honour_demotes_to_dr  INTEGER NOT NULL DEFAULT 0,
                source_category       TEXT,
                notes                 TEXT,
                crawled_at            TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────

    def upsert_spell(self, spell: Spell) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO spells (
                uid, name, wiki_url, level, school, summary, description,
                damage_dice, damage_type, casting_resource, spell_slot_level,
                requires_attack_roll, save_ability, on_save,
                range_m, aoe_m, aoe_shape, concentration, ritual,
                upcast_json, conditions_json, spell_flags_json,
                classes_json, notes_json, bugs_json,
                raw_wikitext, crawled_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?
            )
            ON CONFLICT(uid) DO UPDATE SET
                name=excluded.name, wiki_url=excluded.wiki_url,
                level=excluded.level, school=excluded.school,
                summary=excluded.summary, description=excluded.description,
                damage_dice=excluded.damage_dice, damage_type=excluded.damage_type,
                casting_resource=excluded.casting_resource,
                spell_slot_level=excluded.spell_slot_level,
                requires_attack_roll=excluded.requires_attack_roll,
                save_ability=excluded.save_ability, on_save=excluded.on_save,
                range_m=excluded.range_m, aoe_m=excluded.aoe_m,
                aoe_shape=excluded.aoe_shape,
                concentration=excluded.concentration, ritual=excluded.ritual,
                upcast_json=excluded.upcast_json,
                conditions_json=excluded.conditions_json,
                spell_flags_json=excluded.spell_flags_json,
                classes_json=excluded.classes_json,
                notes_json=excluded.notes_json, bugs_json=excluded.bugs_json,
                raw_wikitext=excluded.raw_wikitext,
                crawled_at=excluded.crawled_at
            """,
            (
                spell.uid,
                spell.name,
                spell.wiki_url,
                spell.level,
                spell.school.value if spell.school else None,
                spell.summary,
                spell.description,
                spell.damage_dice.raw if spell.damage_dice else None,
                spell.damage_type.value if spell.damage_type else None,
                spell.casting_resource.value if spell.casting_resource else None,
                spell.spell_slot_level,
                int(spell.requires_attack_roll),
                spell.save_ability.value if spell.save_ability else None,
                spell.on_save,
                spell.range_m,
                spell.aoe_m,
                spell.aoe_shape,
                int(spell.concentration),
                int(spell.ritual),
                json.dumps(spell.upcast.model_dump() if spell.upcast else None),
                json.dumps([c.model_dump() for c in spell.conditions]),
                json.dumps(spell.spell_flags),
                json.dumps(spell.classes),
                json.dumps(spell.notes),
                json.dumps(spell.bugs),
                spell.raw_wikitext,
                now,
            ),
        )
        self._conn.commit()

    def log_crawl(self, record: CrawlRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO crawl_log (page_title, page_id, entity_type, success, errors_json, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.page_title,
                record.page_id,
                record.entity_type,
                1 if record.parsed is not None else 0,
                json.dumps(record.parse_errors),
                now,
            ),
        )
        self._conn.commit()

    # ── Read ──────────────────────────────────────────────────────────

    def get_spell(self, uid: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM spells WHERE uid = ?", (uid,)
        ).fetchone()
        return dict(row) if row else None

    def get_spell_by_name(self, name: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM spells WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_spells(self, level: Optional[int] = None) -> list[dict]:
        if level is not None:
            rows = self._conn.execute(
                "SELECT * FROM spells WHERE level = ? ORDER BY name", (level,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM spells ORDER BY level, name"
            ).fetchall()
        return [dict(r) for r in rows]

    def count_spells(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM spells").fetchone()[0]

    def spells_with_bugs(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM spells WHERE bugs_json != '[]' ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def spells_with_concentration(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM spells WHERE concentration = 1 ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def reaction_spells(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM spells WHERE casting_resource = 'Reaction' ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── DRS items ─────────────────────────────────────────────────────

    def upsert_drs_item(self, item: DRSItem) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO drs_items (
                name, wiki_url, layer_kind, rider_dice, damage_type,
                honour_demotes_to_dr, source_category, notes, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                wiki_url=excluded.wiki_url,
                layer_kind=excluded.layer_kind,
                rider_dice=excluded.rider_dice,
                damage_type=excluded.damage_type,
                honour_demotes_to_dr=excluded.honour_demotes_to_dr,
                source_category=excluded.source_category,
                notes=excluded.notes,
                crawled_at=excluded.crawled_at
            """,
            (
                item.name,
                item.wiki_url,
                item.layer_kind.value,
                item.rider_dice.raw if item.rider_dice else None,
                item.damage_type.value if item.damage_type else None,
                int(item.honour_demotes_to_dr),
                item.source_category,
                item.notes,
                now,
            ),
        )
        self._conn.commit()

    def list_drs_items(self, layer_kind: Optional[str] = None) -> list[dict]:
        if layer_kind is not None:
            rows = self._conn.execute(
                "SELECT * FROM drs_items WHERE layer_kind = ? ORDER BY name",
                (layer_kind,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM drs_items ORDER BY layer_kind, name"
            ).fetchall()
        return [dict(r) for r in rows]

    def count_drs_items(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM drs_items").fetchone()[0]

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SpellDB:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
