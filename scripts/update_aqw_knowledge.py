"""Update the local AQW Wiki SQLite mirror (offline builder)."""
from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skua_lite.wiki_knowledge import SOURCE_REPO, build_wiki_database, default_wiki_db_path


def _detect_commit(source_dir: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=source_dir,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _resolve_commit(repo_dir: Path | None, explicit: str) -> str:
    if explicit != "detect":
        return explicit
    if repo_dir is None:
        return "unknown"
    git_dir = repo_dir / ".git"
    repo_root = repo_dir if git_dir.is_dir() else repo_dir.parent
    return _detect_commit(repo_root)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", required=True,
        help="Folder berisi WikiItems.json, quests.json, merge_shops.json, locations.json",
    )
    parser.add_argument(
        "--out", default=str(default_wiki_db_path()),
        help="Path database tujuan (atomically replaced).",
    )
    parser.add_argument(
        "--repo-dir", default=None,
        help="Checkout AQWikiTools untuk deteksi commit (opsional).",
    )
    parser.add_argument("--commit", default="detect", help="Commit sumber (default: detect).")
    args = parser.parse_args(argv)
    args.repo_dir = Path(args.repo_dir) if args.repo_dir else None
    if args.repo_dir is not None and not args.repo_dir.is_dir():
        parser.error(f"--repo-dir tidak ada: {args.repo_dir}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_dir = Path(args.source_dir)
    started = time.time()
    try:
        counts = build_wiki_database(
            source_dir, args.out,
            source_commit=_resolve_commit(args.repo_dir, args.commit),
        )
    except FileNotFoundError as exc:
        print(f"[WIKI] {exc}")
        return 1
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"[WIKI] build gagal: {exc}")
        return 1
    elapsed = time.time() - started
    total = sum(counts.values())
    print(
        f"[WIKI] {total} baris ({counts['items']} item, {counts['quests']} quest, "
        f"{counts['merge_shops']} merge shop, {counts['locations']} lokasi) "
        f"-> {args.out} dalam {elapsed:.1f}s. Sumber: {SOURCE_REPO}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
