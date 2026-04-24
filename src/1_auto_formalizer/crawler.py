"""
crawler.py — BG3 Wiki Spell Crawler via MediaWiki API
=====================================================

Scrapes spell data exclusively from **bg3.wiki** using its public
MediaWiki API.  No screen-scraping, no fabricated data.  Every record
carries its provenance URL and raw wikitext so it can be audited.

Usage
-----
    python -m src.1_auto_formalizer.crawler            # crawl all spells
    python -m src.1_auto_formalizer.crawler --spell Fireball  # single spell
    python -m src.1_auto_formalizer.crawler --dry-run  # parse but don't store

Data flow::

    bg3.wiki MediaWiki API
        │  JSON (wikitext)
        ▼
    wikitext_parser.parse_spell()
        │  Spell model
        ▼
    database.SpellDB.upsert_spell()
        │
        ▼
    dataset/valor.db
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from tenacity import retry, stop_after_attempt, wait_exponential

from .database import SpellDB
from .models import CrawlRecord, Spell
from .wikitext_parser import parse_spell

console = Console()

API_BASE = "https://bg3.wiki/w/api.php"
REQUEST_DELAY = 0.5  # be polite: ≤2 req/s


# ── MediaWiki API helpers ─────────────────────────────────────────────────

def _make_client() -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        headers={"User-Agent": "VALOR-FV-Engine/0.1 (academic research)"},
        timeout=30.0,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
def _api_get(client: httpx.Client, params: dict) -> dict:
    """Issue a GET to the MediaWiki API with automatic retry."""
    params["format"] = "json"
    resp = client.get("", params=params)
    resp.raise_for_status()
    return resp.json()


def list_category_members(
    client: httpx.Client,
    category: str,
    limit: int = 500,
) -> Iterator[dict]:
    """
    Yield all pages in *category* (e.g. ``Category:Spells``).

    Handles continuation tokens automatically.
    """
    params: dict = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmlimit": min(limit, 500),
        "cmtype": "page",
    }
    while True:
        data = _api_get(client, params)
        for member in data.get("query", {}).get("categorymembers", []):
            yield member
        cont = data.get("continue")
        if not cont:
            break
        params["cmcontinue"] = cont["cmcontinue"]
        time.sleep(REQUEST_DELAY)


def fetch_wikitext(client: httpx.Client, page_title: str) -> tuple[int, str]:
    """Return ``(page_id, raw_wikitext)`` for a single page."""
    data = _api_get(client, {
        "action": "parse",
        "page": page_title,
        "prop": "wikitext",
    })
    parsed = data.get("parse", {})
    page_id = parsed.get("pageid", 0)
    wikitext = parsed.get("wikitext", {}).get("*", "")
    return page_id, wikitext


# ── Spell categories on bg3.wiki ──────────────────────────────────────────

SPELL_CATEGORIES = [
    "Category:Cantrips",
    "Category:Level 1 spells",
    "Category:Level 2 spells",
    "Category:Level 3 spells",
    "Category:Level 4 spells",
    "Category:Level 5 spells",
    "Category:Level 6 spells",
]


# ── Core crawl logic ─────────────────────────────────────────────────────

def discover_spell_pages(client: httpx.Client) -> list[dict]:
    """Collect unique spell page titles across all level categories."""
    seen: set[str] = set()
    pages: list[dict] = []

    for cat in SPELL_CATEGORIES:
        console.log(f"[dim]Listing {cat}…[/dim]")
        for member in list_category_members(client, cat):
            title = member["title"]
            if title not in seen:
                seen.add(title)
                pages.append(member)
        time.sleep(REQUEST_DELAY)

    console.log(f"Discovered [bold]{len(pages)}[/bold] unique spell pages")
    return pages


def crawl_spell(
    client: httpx.Client,
    page_title: str,
    db: SpellDB | None = None,
) -> CrawlRecord:
    """Fetch, parse, validate, and optionally store a single spell."""
    page_id, wikitext = fetch_wikitext(client, page_title)

    spell, errors = parse_spell(page_title, wikitext)

    record = CrawlRecord(
        page_title=page_title,
        page_id=page_id,
        wiki_url=f"https://bg3.wiki/wiki/{page_title.replace(' ', '_')}",
        entity_type="spell",
        raw_wikitext=wikitext,
        parsed=spell,
        crawled_at=datetime.now(timezone.utc).isoformat(),
        parse_errors=errors,
    )

    if db is not None:
        db.log_crawl(record)
        if spell is not None:
            db.upsert_spell(spell)

    return record


def crawl_all(db_path: Path | None = None, dry_run: bool = False) -> list[CrawlRecord]:
    """
    Full crawl: discover all spells → fetch → parse → store.

    Returns the list of ``CrawlRecord``s for inspection / testing.
    """
    client = _make_client()
    db: SpellDB | None = None
    if not dry_run:
        db = SpellDB(db_path) if db_path else SpellDB()

    try:
        return _crawl_all_inner(client, db, dry_run)
    finally:
        client.close()
        if db is not None:
            db.close()


def _crawl_all_inner(
    client: httpx.Client, db: SpellDB | None, dry_run: bool
) -> list[CrawlRecord]:
    pages = discover_spell_pages(client)
    records: list[CrawlRecord] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Crawling spells…", total=len(pages))
        for page in pages:
            title = page["title"]
            progress.update(task, description=f"[cyan]{title}")
            try:
                rec = crawl_spell(client, title, db)
                records.append(rec)
                status = "[green]OK" if rec.parsed else "[red]FAIL"
                if rec.parse_errors:
                    console.log(f"  {status} {title}: {rec.parse_errors}")
            except Exception as exc:
                console.log(f"  [red]ERROR[/red] {title}: {exc}")
                records.append(CrawlRecord(
                    page_title=title,
                    page_id=page.get("pageid", 0),
                    wiki_url=f"https://bg3.wiki/wiki/{title.replace(' ', '_')}",
                    entity_type="spell",
                    raw_wikitext="",
                    parse_errors=[str(exc)],
                    crawled_at=datetime.now(timezone.utc).isoformat(),
                ))
            progress.advance(task)
            time.sleep(REQUEST_DELAY)

    succeeded = sum(1 for r in records if r.parsed is not None)
    console.print(
        f"\n[bold]Done.[/bold] {succeeded}/{len(records)} spells parsed successfully."
    )
    if db is not None:
        console.print(f"Database: {db.db_path}  ({db.count_spells()} spells)")

    return records


# ── Save raw wikitext to disk ─────────────────────────────────────────────

def save_raw_dumps(records: list[CrawlRecord], output_dir: Path | None = None) -> None:
    """Persist raw wikitext to ``dataset/raw_wiki_dumps/`` for provenance."""
    out = output_dir or Path(__file__).resolve().parents[2] / "dataset" / "raw_wiki_dumps"
    out.mkdir(parents=True, exist_ok=True)

    for rec in records:
        if not rec.raw_wikitext:
            continue
        fname = rec.page_title.replace(" ", "_").replace("/", "_") + ".json"
        payload = {
            "page_title": rec.page_title,
            "page_id": rec.page_id,
            "wiki_url": rec.wiki_url,
            "crawled_at": rec.crawled_at,
            "wikitext": rec.raw_wikitext,
        }
        (out / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2))


# ── CLI entry-point ───────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl BG3 wiki spell data")
    parser.add_argument("--spell", type=str, help="Crawl a single spell by name")
    parser.add_argument("--db", type=Path, help="SQLite database path")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't store")
    parser.add_argument("--save-raw", action="store_true", help="Also save raw wikitext to disk")
    args = parser.parse_args()

    if args.spell:
        client = _make_client()
        db = None if args.dry_run else SpellDB(args.db) if args.db else SpellDB()
        rec = crawl_spell(client, args.spell, db)
        if rec.parsed:
            console.print_json(rec.parsed.model_dump_json(indent=2))
        else:
            console.print(f"[red]Failed:[/red] {rec.parse_errors}")
        if db:
            db.close()
    else:
        records = crawl_all(db_path=args.db, dry_run=args.dry_run)
        if args.save_raw:
            save_raw_dumps(records)


if __name__ == "__main__":
    main()
