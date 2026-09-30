"""Build and query a fast local AQW Wiki knowledge database.

The source snapshot is AQWikiTools' MIT-licensed JSON export.  Runtime lookup is
read-only SQLite, so answering an item question never waits for Wikidot or a
search engine.
"""
from __future__ import annotations

import difflib
import html
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SOURCE_REPO = "https://github.com/R41CY/AQWikiTools"
WIKI_BASE = "https://aqwwiki.wikidot.com"
ALIASES = {
    "vhl": "void highlord",
    "lr": "legion revenant",
    "blod": "blinding light of destiny",
    "nsod": "necrotic sword of doom",
    "sdka": "seppy doomknight armor",
    "ap": "archpaladin",
    "loo": "lord of order",
    "sc": "stonecrusher",
    "cav": "chaos avenger",
    "dot": "dragon of time",
}
_SOURCE_HINT_RE = re.compile(
    r"(?:dapat|dapet|dropped?|drop|asal|source|sumber|where|from|cara dapat|"
    r"dari mana|di mana|dimana|quest|merge|shop|beli|farm)", re.IGNORECASE,
)
_QUESTION_TRIM_RE = re.compile(
    r"\b(?:item|ini|itu|yg|yang|dapat|dapet|didapat|didapet|dari|di|mana|"
    r"dimana|where|from|source|sumber|cara|gimana|bagaimana|drop|oleh|siapa|"
    r"quest|shop|merge|beli|farm|nya|dong|bro|gan|aqw)\b",
    re.IGNORECASE,
)
_VARIANT_RE = re.compile(
    r"\s*\((?:class|armor|helm|cape|weapon|pet|misc|necklace|sword|dagger|"
    r"axe|mace|polearm|staff|wand|bow|gun|0\s*ac|ac|legend|non-legend|merge|"
    r"rare|vip|monster)\)\s*$", re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _norm(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def _base_name(value: Any) -> str:
    return _norm(_VARIANT_RE.sub("", html.unescape(str(value or ""))))


def _integer(value: Any, default: int | None = None) -> int | None:
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def _property_map(row: list[Any]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for part in row[1:]:
        if isinstance(part, list) and len(part) >= 2 and isinstance(part[0], str):
            props[part[0].casefold()] = part[1]
    return props


def _entity(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict):
        return "", ""
    return str(value.get("name") or "").strip(), str(value.get("slug") or "").strip()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE items(
 item_id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_cf TEXT NOT NULL,
 base_name_cf TEXT NOT NULL, slug TEXT NOT NULL, category TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', price_kind TEXT NOT NULL DEFAULT 'unknown',
 price_currency TEXT, price_amount INTEGER, price_ref_name TEXT, price_ref_slug TEXT,
 price_raw TEXT NOT NULL DEFAULT '', ac INTEGER NOT NULL DEFAULT 0,
 rare INTEGER NOT NULL DEFAULT 0, legend INTEGER NOT NULL DEFAULT 0,
 seasonal INTEGER NOT NULL DEFAULT 0, pseudo_rare INTEGER NOT NULL DEFAULT 0,
 special_offer INTEGER NOT NULL DEFAULT 0, color_custom INTEGER NOT NULL DEFAULT 0,
 wiki_url TEXT NOT NULL
);
CREATE INDEX idx_items_name_cf ON items(name_cf);
CREATE INDEX idx_items_base_cf ON items(base_name_cf);
CREATE INDEX idx_items_slug ON items(slug);
CREATE TABLE item_merge_ingredients(
 item_id INTEGER NOT NULL REFERENCES items(item_id), ing_name TEXT NOT NULL,
 ing_cf TEXT NOT NULL, ing_slug TEXT, qty INTEGER NOT NULL
);
CREATE TABLE quest_pages(
 page_id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL,
 npc_name TEXT, loc_name TEXT, rare INTEGER, pseudo_rare INTEGER, tags_json TEXT
);
CREATE TABLE quests(
 quest_id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES quest_pages(page_id),
 name TEXT NOT NULL, name_cf TEXT NOT NULL, description TEXT, requirements_note TEXT,
 loc_name TEXT, npc_name TEXT, gold INTEGER, exp INTEGER
);
CREATE INDEX idx_quests_name_cf ON quests(name_cf);
CREATE TABLE quest_requirements(
 quest_id INTEGER NOT NULL REFERENCES quests(quest_id), req_name TEXT NOT NULL,
 req_cf TEXT NOT NULL, slug TEXT, qty INTEGER NOT NULL
);
CREATE TABLE quest_drops(
 quest_id INTEGER NOT NULL REFERENCES quests(quest_id), req_name TEXT NOT NULL,
 monster_name TEXT NOT NULL, monster_cf TEXT NOT NULL, monster_slug TEXT
);
CREATE TABLE quest_rewards(
 quest_id INTEGER NOT NULL REFERENCES quests(quest_id), item_name TEXT NOT NULL,
 item_cf TEXT NOT NULL, slug TEXT, qty INTEGER NOT NULL,
 is_random INTEGER NOT NULL DEFAULT 0, is_choice INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_qrew_item_cf ON quest_rewards(item_cf);
CREATE INDEX idx_qreq_req_cf ON quest_requirements(req_cf);
CREATE TABLE merge_shops(
 shop_id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL,
 npc_name TEXT, loc_name TEXT, rare INTEGER, pseudo_rare INTEGER, tags_json TEXT
);
CREATE TABLE merge_items(
 entry_id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES merge_shops(shop_id),
 tab_name TEXT, item_name TEXT NOT NULL, item_cf TEXT NOT NULL, slug TEXT,
 type_icon TEXT, cost_type TEXT, price_amount INTEGER, price_currency TEXT
);
CREATE INDEX idx_merge_item_cf ON merge_items(item_cf);
CREATE TABLE merge_ingredients(
 entry_id INTEGER NOT NULL REFERENCES merge_items(entry_id), ing_name TEXT NOT NULL,
 ing_cf TEXT NOT NULL, slug TEXT, qty INTEGER NOT NULL
);
CREATE TABLE locations(
 loc_id INTEGER PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL,
 map_name TEXT, map_cf TEXT, join_cmd TEXT, description TEXT
);
CREATE INDEX idx_locations_name_cf ON locations(map_cf);
CREATE TABLE loc_monsters(
 loc_id INTEGER NOT NULL REFERENCES locations(loc_id), monster_name TEXT NOT NULL,
 monster_cf TEXT NOT NULL, slug TEXT, count INTEGER
);
CREATE INDEX idx_loc_monster_cf ON loc_monsters(monster_cf);
CREATE VIRTUAL TABLE item_fts USING fts5(name, description, category,
 tokenize='unicode61 remove_diacritics 2');
"""


def _price_parts(price: Any) -> tuple[str, str | None, int | None, str | None, str | None, list]:
    if not isinstance(price, list) or not price:
        return "unknown", None, None, None, None, []
    kind = str(price[0] or "").strip()
    lower = kind.casefold()
    if lower in {"ac", "gold"}:
        amount = _integer(price[1] if len(price) > 1 else None)
        # AQWikiTools uses ``AC N/A`` for AC-tagged resources that are not
        # actually sold. Keep the fact unknown instead of claiming a purchase.
        if amount is None:
            return "unknown", None, None, None, None, []
        return "shop", kind.upper(), amount, None, None, []
    if lower in {"drop", "quest", "merge"}:
        ref_name = str(price[1] or "").strip() if len(price) > 1 else None
        ref_slug = str(price[2] or "").strip() if len(price) > 2 else None
        ingredients = price[3] if lower == "merge" and len(price) > 3 and isinstance(price[3], list) else []
        return lower, None, None, ref_name, ref_slug, ingredients
    if lower in {"n/a", "temporary", "login reward", "failed to retrive"}:
        return lower.replace(" ", "_"), None, None, None, None, []
    return lower or "unknown", None, None, None, None, []


def build_wiki_database(source_dir: str | os.PathLike[str], output: str | os.PathLike[str],
                        *, source_commit: str = "unknown", license_text: str = "MIT") -> dict[str, int]:
    """Build and atomically publish a SQLite DB from AQWikiTools' four JSON files."""
    source = Path(source_dir)
    required = ["WikiItems.json", "quests.json", "merge_shops.json", "locations.json"]
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError("AQWikiTools data kurang: " + ", ".join(missing))

    final = Path(output)
    final.parent.mkdir(parents=True, exist_ok=True)
    temp = final.with_name(f"{final.name}.tmp.{os.getpid()}")
    if temp.exists():
        temp.unlink()
    counts = {"items": 0, "quests": 0, "merge_shops": 0, "locations": 0}

    try:
        with sqlite3.connect(str(temp)) as con:
            con.executescript(_SCHEMA)
            con.execute("BEGIN")
            item_rows: list[tuple] = []
            item_ingredients: list[tuple] = []
            used_names: dict[str, int] = {}
            raw_items = _read_json(source / "WikiItems.json")
            for item_id, (raw_name, row) in enumerate(raw_items.items(), 1):
                if not isinstance(row, list) or not row:
                    continue
                name = html.unescape(str(raw_name))
                norm_name = _norm(name)
                seen = used_names.get(norm_name, 0)
                used_names[norm_name] = seen + 1
                if seen:
                    name = f"{name} ({seen + 1})"
                slug = str(row[0] or "")
                props = _property_map(row)
                price = props.get("price")
                kind, currency, amount, ref_name, ref_slug, ingredients = _price_parts(price)
                category = str(row[-1] or "") if isinstance(row[-1], str) else ""
                item_rows.append((
                    item_id, name, _norm(name), _base_name(name), slug, category,
                    html.unescape(str(props.get("description") or "")).strip(), kind,
                    currency, amount, ref_name, ref_slug,
                    json.dumps(price, ensure_ascii=False), _bool(props.get("ac")),
                    _bool(props.get("rare")), _bool(props.get("legend")),
                    _bool(props.get("seasonal")), _bool(props.get("pseudo rare")),
                    _bool(props.get("special offer")), _bool(props.get("color custom")),
                    WIKI_BASE + slug,
                ))
                for ingredient in ingredients:
                    if isinstance(ingredient, list) and ingredient:
                        ing_name = html.unescape(str(ingredient[0]))
                        item_ingredients.append((item_id, ing_name, _norm(ing_name),
                                                 str(ingredient[1]) if len(ingredient) > 1 else "",
                                                 _integer(ingredient[2] if len(ingredient) > 2 else 1, 1)))
            con.executemany("""INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", item_rows)
            con.executemany("INSERT INTO item_merge_ingredients VALUES (?,?,?,?,?)", item_ingredients)
            counts["items"] = len(item_rows)

            page_rows, quest_rows, requirements, drops, rewards = [], [], [], [], []
            page_id = quest_id = 0
            for page in _read_json(source / "quests.json").values():
                if not isinstance(page, dict):
                    continue
                page_id += 1
                npc_name, _ = _entity(page.get("npc"))
                loc_name, _ = _entity(page.get("location"))
                page_rows.append((page_id, page.get("name", ""), page.get("slug", ""),
                                  npc_name, loc_name, _bool(page.get("rare")),
                                  _bool(page.get("pseudo_rare")),
                                  json.dumps(page.get("tags") or [], ensure_ascii=False)))
                for quest in page.get("quests") or []:
                    if not isinstance(quest, dict):
                        continue
                    quest_id += 1
                    qloc, _ = _entity(quest.get("location"))
                    qnpc, _ = _entity(quest.get("npc"))
                    reward_block = quest.get("rewards") or {}
                    quest_rows.append((quest_id, page_id, quest.get("name", ""),
                                       _norm(quest.get("name")), quest.get("description", ""),
                                       quest.get("requirements_note", ""), qloc or loc_name,
                                       qnpc or npc_name, _integer(reward_block.get("gold"), 0),
                                       _integer(reward_block.get("exp"), 0)))
                    for req in quest.get("items_required") or []:
                        if not isinstance(req, dict):
                            continue
                        req_name = html.unescape(str(req.get("name") or ""))
                        requirements.append((quest_id, req_name, _norm(req_name), req.get("slug", ""),
                                             _integer(req.get("qty"), 1)))
                        for monster in req.get("dropped_by") or []:
                            mon_name, mon_slug = _entity(monster)
                            if mon_name:
                                drops.append((quest_id, req_name, mon_name, _norm(mon_name), mon_slug))
                    for reward in reward_block.get("items") or []:
                        if not isinstance(reward, dict):
                            continue
                        rname = html.unescape(str(reward.get("name") or ""))
                        rewards.append((quest_id, rname, _norm(rname), reward.get("slug", ""),
                                        _integer(reward.get("qty"), 1), _bool(reward.get("random")),
                                        _bool(reward.get("choice"))))
            con.executemany("INSERT INTO quest_pages VALUES (?,?,?,?,?,?,?,?)", page_rows)
            con.executemany("INSERT INTO quests VALUES (?,?,?,?,?,?,?,?,?,?)", quest_rows)
            con.executemany("INSERT INTO quest_requirements VALUES (?,?,?,?,?)", requirements)
            con.executemany("INSERT INTO quest_drops VALUES (?,?,?,?,?)", drops)
            con.executemany("INSERT INTO quest_rewards VALUES (?,?,?,?,?,?,?)", rewards)
            counts["quests"] = len(quest_rows)

            shop_rows, merge_items, merge_ings = [], [], []
            shop_id = entry_id = 0
            for shop in _read_json(source / "merge_shops.json").values():
                if not isinstance(shop, dict):
                    continue
                shop_id += 1
                npc_name, _ = _entity(shop.get("npc"))
                loc_name, _ = _entity(shop.get("location"))
                shop_rows.append((shop_id, shop.get("name", ""), shop.get("slug", ""),
                                  npc_name, loc_name, _bool(shop.get("rare")),
                                  _bool(shop.get("pseudo_rare")),
                                  json.dumps(shop.get("tags") or [], ensure_ascii=False)))
                for tab in shop.get("tabs") or []:
                    if not isinstance(tab, dict):
                        continue
                    for item in tab.get("items") or []:
                        if not isinstance(item, dict):
                            continue
                        entry_id += 1
                        price = item.get("price") or {}
                        merge_items.append((entry_id, shop_id, tab.get("name", ""),
                                            item.get("name", ""), _norm(item.get("name")),
                                            item.get("slug", ""), item.get("type_icon", ""),
                                            item.get("cost_type", ""), _integer(price.get("amount")),
                                            price.get("currency")))
                        for ing in item.get("ingredients") or []:
                            if not isinstance(ing, dict):
                                continue
                            merge_ings.append((entry_id, ing.get("name", ""), _norm(ing.get("name")),
                                               ing.get("slug", ""), _integer(ing.get("qty"), 1)))
            con.executemany("INSERT INTO merge_shops VALUES (?,?,?,?,?,?,?,?)", shop_rows)
            con.executemany("INSERT INTO merge_items VALUES (?,?,?,?,?,?,?,?,?,?)", merge_items)
            con.executemany("INSERT INTO merge_ingredients VALUES (?,?,?,?,?)", merge_ings)
            counts["merge_shops"] = len(shop_rows)

            loc_rows, monsters = [], []
            loc_id = 0
            for location in _read_json(source / "locations.json").values():
                if not isinstance(location, dict):
                    continue
                loc_id += 1
                loc_rows.append((loc_id, location.get("name", ""), location.get("slug", ""),
                                 location.get("map_name", ""), _norm(location.get("map_name")),
                                 location.get("join_cmd", ""), location.get("description", "")))
                for monster in location.get("monsters") or []:
                    if not isinstance(monster, dict):
                        continue
                    name = html.unescape(str(monster.get("name") or ""))
                    monsters.append((loc_id, name, _norm(name), monster.get("slug", ""),
                                     _integer(monster.get("count"), 1)))
            con.executemany("INSERT INTO locations VALUES (?,?,?,?,?,?,?)", loc_rows)
            con.executemany("INSERT INTO loc_monsters VALUES (?,?,?,?,?)", monsters)
            counts["locations"] = len(loc_rows)

            con.executemany(
                "INSERT INTO item_fts(rowid,name,description,category) VALUES (?,?,?,?)",
                [(row[0], row[1], row[6], row[5]) for row in item_rows],
            )
            meta = {
                "source_repo": SOURCE_REPO,
                "source_commit": source_commit,
                "built_at": str(int(time.time())),
                "license_name": "MIT",
                "license_text": license_text,
                "counts_json": json.dumps(counts, sort_keys=True),
                "schema_version": "1",
            }
            con.executemany("INSERT INTO meta(key,value) VALUES (?,?)", meta.items())
            con.commit()
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("SQLite integrity_check gagal")
        # sqlite3.Connection's context manager commits/rolls back but does not
        # close. Windows will refuse the atomic replace while the handle lives.
        con.close()
        os.replace(temp, final)
    finally:
        if temp.exists():
            temp.unlink()
    return counts


@dataclass(frozen=True)
class WikiHit:
    name: str
    category: str
    answer: str
    wiki_url: str
    match_kind: str
    confidence: float = 1.0

    def short_answer(self, limit: int = 150) -> str:
        text = " ".join(self.answer.split())
        if len(text) <= limit:
            return text
        return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


class WikiKnowledge:
    """Thread-safe, lazy, read-only local item source lookup."""

    def __init__(self, db_path: str | os.PathLike[str]):
        self.path = Path(db_path)
        self._lock = threading.RLock()
        self._con: sqlite3.Connection | None = None
        self._fingerprint: tuple[int, int] | None = None

    @property
    def ready(self) -> bool:
        return self.path.is_file() and self.path.stat().st_size > 0

    def close(self) -> None:
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None

    def _connection(self) -> sqlite3.Connection | None:
        if not self.ready:
            return None
        stamp = (self.path.stat().st_size, self.path.stat().st_mtime_ns)
        with self._lock:
            if self._con is not None and stamp != self._fingerprint:
                self._con.close()
                self._con = None
            if self._con is None:
                uri = self.path.resolve().as_uri() + "?mode=ro"
                self._con = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=3)
                self._con.row_factory = sqlite3.Row
                self._con.execute("PRAGMA query_only=ON")
                self._con.execute("PRAGMA temp_store=MEMORY")
                self._fingerprint = stamp
            return self._con

    def lookup_item(self, query: str) -> WikiHit | None:
        con = self._connection()
        wanted = self._clean_query(query)
        if con is None or not wanted:
            return None
        alias = ALIASES.get(wanted, wanted)
        with self._lock:
            row = con.execute(
                "SELECT * FROM items WHERE name_cf=? OR base_name_cf=? "
                "ORDER BY name_cf=? DESC, item_id LIMIT 1",
                (alias, alias, alias),
            ).fetchone()
            match_kind = "alias" if alias != wanted and row else "exact"
            confidence = 1.0
            if row is None:
                row = self._fts_row(con, alias)
                match_kind = "fts"
                confidence = 0.86
            if row is None:
                row = self._fuzzy_row(con, alias)
                match_kind = "fuzzy"
                confidence = 0.72
            if row is None:
                return None
            answer = self._answer_for(con, row)
            return WikiHit(row["name"], row["category"], answer, row["wiki_url"],
                           match_kind, confidence)

    def context_for(self, message: str) -> str:
        if not self.ready or not _SOURCE_HINT_RE.search(message or ""):
            return ""
        hit = self.lookup_item(message)
        if hit is None or hit.confidence < 0.80:
            return ""
        return (
            "KONTEKS WIKI AQW (database lokal; gunakan sebagai fakta, jangan mengarang):\n"
            f"Item: {hit.name}\nKategori: {hit.category}\n{hit.answer}\n"
            f"Halaman: {hit.wiki_url}"
        )[:1800]

    @staticmethod
    def _clean_query(query: str) -> str:
        text = html.unescape(str(query or ""))
        if _SOURCE_HINT_RE.search(text):
            text = _QUESTION_TRIM_RE.sub(" ", text)
        text = re.sub(r"[^A-Za-z0-9'&+ -]+", " ", text)
        return _norm(text)

    @staticmethod
    def _fts_row(con: sqlite3.Connection, query: str) -> sqlite3.Row | None:
        tokens = [token for token in _WORD_RE.findall(query) if len(token) >= 2]
        if not tokens:
            return None
        expression = " AND ".join(f'name:"{token}"*' for token in tokens[:8])
        try:
            row = con.execute(
                "SELECT i.* FROM item_fts f JOIN items i ON i.item_id=f.rowid "
                "WHERE item_fts MATCH ? ORDER BY bm25(item_fts) LIMIT 1", (expression,),
            ).fetchone()
            if row is not None:
                return row
        except sqlite3.OperationalError:
            pass
        # FTS prefix off karena stop-word/penggabungan token wiki (DragonBlade
        # vs "dragon blade") kadang tidak menghasilkan hit. Fallback LIKE
        # substring mengikuti tier agar jawaban tetap instan (<10ms).
        pattern = "%" + "%".join(t for t in tokens[:8]) + "%"
        return con.execute(
            "SELECT * FROM items WHERE replace(lower(name),' ','') LIKE "
            "replace(lower(?),' ','') ORDER BY length(name) LIMIT 1",
            (pattern,),
        ).fetchone()

    @staticmethod
    def _fuzzy_row(con: sqlite3.Connection, query: str) -> sqlite3.Row | None:
        token = next((t for t in _WORD_RE.findall(query) if len(t) >= 4), "")
        if not token:
            return None
        candidates = con.execute(
            "SELECT * FROM items WHERE name_cf LIKE ? LIMIT 250", (f"%{token[:4]}%",),
        ).fetchall()
        if not candidates:
            candidates = con.execute("SELECT * FROM items LIMIT 5000").fetchall()
        names = [row["name_cf"] for row in candidates]
        close = difflib.get_close_matches(query, names, n=1, cutoff=0.68)
        if not close:
            return None
        return next(row for row in candidates if row["name_cf"] == close[0])

    def _answer_for(self, con: sqlite3.Connection, item: sqlite3.Row) -> str:
        name_cf = item["name_cf"]
        parts: list[str] = []
        direct = item["price_kind"]

        if direct == "drop" and item["price_ref_name"]:
            source = item["price_ref_name"]
            loc = self._monster_location(con, source)
            parts.append(f"{item['name']} drop dari {source}" + (f" di {loc}" if loc else "") + ".")
        elif direct == "quest" and item["price_ref_name"]:
            parts.append(f"{item['name']} adalah reward quest {item['price_ref_name']}.")
        elif direct == "merge" and item["price_ref_name"]:
            ings = con.execute(
                "SELECT ing_name, qty FROM item_merge_ingredients WHERE item_id=? LIMIT 8",
                (item["item_id"],),
            ).fetchall()
            ingredients = self._format_ingredients(ings)
            suffix = f"; butuh {ingredients}" if ingredients else ""
            parts.append(f"{item['name']} dibuat di {item['price_ref_name']}{suffix}.")
        elif direct == "shop":
            price = f"{item['price_amount']} {item['price_currency']}" if item["price_amount"] is not None else item["price_currency"]
            parts.append(f"{item['name']} dibeli seharga {price}.")
        elif direct in {"n/a", "temporary", "login_reward"}:
            parts.append(f"Sumber {item['name']}: {direct.replace('_', ' ')}.")

        quest = con.execute(
            "SELECT q.*, qp.slug page_slug FROM quest_rewards qr "
            "JOIN quests q ON q.quest_id=qr.quest_id "
            "JOIN quest_pages qp ON qp.page_id=q.page_id "
            "WHERE qr.item_cf IN (?,?) ORDER BY q.quest_id LIMIT 1",
            (name_cf, item["base_name_cf"]),
        ).fetchone()
        if quest is not None:
            reqs = con.execute(
                "SELECT req_name, qty FROM quest_requirements WHERE quest_id=? LIMIT 10",
                (quest["quest_id"],),
            ).fetchall()
            need = self._format_ingredients(reqs, "req_name")
            loc = self._location_text(con, quest["loc_name"])
            clause = f"Quest {quest['name']}" + (f" di {loc}" if loc else "")
            if need:
                clause += f"; butuh {need}"
            sentence = clause + "."
            if not any(quest["name"].casefold() in p.casefold() for p in parts):
                parts.append(sentence)
            else:
                details: list[str] = []
                if loc and loc.casefold() not in " ".join(parts).casefold():
                    details.append(f"Lokasi {loc}")
                if need and need.casefold() not in " ".join(parts).casefold():
                    details.append(f"butuh {need}")
                if details:
                    parts.append("; ".join(details) + ".")

        merge = con.execute(
            "SELECT mi.*, ms.name shop_name, ms.loc_name FROM merge_items mi "
            "JOIN merge_shops ms ON ms.shop_id=mi.shop_id "
            "WHERE mi.item_cf IN (?,?) ORDER BY mi.entry_id LIMIT 1",
            (name_cf, item["base_name_cf"]),
        ).fetchone()
        if merge is not None:
            ings = con.execute(
                "SELECT ing_name, qty FROM merge_ingredients WHERE entry_id=? LIMIT 10",
                (merge["entry_id"],),
            ).fetchall()
            need = self._format_ingredients(ings)
            loc = self._location_text(con, merge["loc_name"])
            clause = f"Merge di {merge['shop_name']}" + (f" ({loc})" if loc else "")
            if need:
                clause += f"; butuh {need}"
            sentence = clause + "."
            if sentence.casefold() not in " ".join(parts).casefold():
                parts.append(sentence)

        if not parts:
            parts.append(f"Sumber {item['name']} belum terstruktur di snapshot lokal.")
        return " ".join(parts)

    @staticmethod
    def _format_ingredients(rows: Iterable[sqlite3.Row], name_col: str = "ing_name") -> str:
        return ", ".join(f"{row[name_col]} x{row['qty']}" for row in rows)

    @staticmethod
    def _location_text(con: sqlite3.Connection, name: str | None) -> str:
        if not name:
            return ""
        loc = con.execute(
            "SELECT name,join_cmd FROM locations WHERE lower(name)=? OR map_cf=? LIMIT 1",
            (_norm(name), _norm(name)),
        ).fetchone()
        if loc is None:
            return str(name)
        return f"{loc['name']} {loc['join_cmd']}".strip()

    @staticmethod
    def _monster_location(con: sqlite3.Connection, monster_name: str) -> str:
        loc = con.execute(
            "SELECT l.name,l.join_cmd FROM loc_monsters m JOIN locations l ON l.loc_id=m.loc_id "
            "WHERE m.monster_cf=? ORDER BY l.loc_id LIMIT 1", (_norm(monster_name),),
        ).fetchone()
        if loc is None:
            return ""
        return f"{loc['name']} {loc['join_cmd']}".strip()


def default_wiki_db_path() -> Path:
    explicit = os.getenv("SKUA_WIKI_DB")
    if explicit:
        return Path(explicit)
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(local) / "skua-lite" / "aqw_wiki.db"
