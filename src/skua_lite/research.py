"""Offline building blocks for the research agent.

These helpers are pure-Python so the unit tests can run without network access.
The agent itself is wired in `ai_router.py` and the live runner in
`scripts/research_agent.py`. Together they implement a single-turn plan-and-answer
loop: the model can emit ``RESEARCH: <question>`` once, the bot fetches up to
one page (with Wayback fallback), injects the cleaned text, then asks the model
to answer. All extracted text is cached to disk by URL so restart does not
repeat fetches.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

_AQW_WIKI_RE = re.compile(r"https?://(?:[\w\-]+\.)?aqwwiki\.wikidot\.com/[A-Za-z0-9_\-/]+")
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']')
_QUESTION_STOP = frozenset({
    "aqw", "what", "is", "info", "how", "to", "do", "the", "a", "an", "for",
    "of", "in", "on", "skill", "skills", "guide", "boss", "ultra", "page",
    "wiki", "class", "item", "quest", "tell", "me", "about", "with",
})
_H_TAG_RE = re.compile(r"<(/?)h([1-6])[^>]*>", re.IGNORECASE)
_RESEARCH_RE = re.compile(r"(?:^|\n)\s*RESEARCH\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def extract_wiki_urls(html: str) -> list[str]:
    """Return the unique AQW Wiki page URLs found inside an HTML body.

    Search engines wrap the target URL inside their redirector; this helper
    looks for raw mentions of the wikidot domain anywhere in the markup so
    the wrapped Bing/DuckDuckGo/Google result links still count.
    """
    if not html:
        return []
    found = _AQW_WIKI_RE.findall(html)
    if not found:
        found = [
            m for m in (h.strip() for h in _HREF_RE.findall(html))
            if _AQW_WIKI_RE.match(m)
        ]
    seen: set[str] = set()
    return [u for u in found if not (u in seen or seen.add(u))]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._heading_level = 0
        self._heading_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "noscript", "aside"):
            self._skip_depth = getattr(self, "_skip_depth", 0)
            self._skip_depth += 1
            return
        if tag.lower().startswith("h") and tag[1:].isdigit():
            self._heading_level = int(tag[1:])
            self._heading_buf = []
        if tag in ("br", "p", "li", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower().startswith("h") and tag[1:].isdigit():
            level = int(tag[1:])
            if self._heading_buf:
                prefix = "#" * level
                self._parts.append(f"\n{prefix} " + " ".join(self._heading_buf) + "\n")
                self._heading_buf = []
            self._heading_level = 0
        depth = getattr(self, "_skip_depth", 0)
        if depth and tag in ("script", "style", "noscript", "aside"):
            self._skip_depth = depth - 1

    def handle_data(self, data: str) -> None:
        depth = getattr(self, "_skip_depth", 0)
        if depth:
            return
        text = data.strip()
        if not text:
            return
        if self._heading_level:
            self._heading_buf.append(text)
        else:
            self._parts.append(text + " ")


def html_to_text(html: str) -> str:
    """Return a minimal but readable plain-text representation of ``html``."""
    parser = _TextExtractor()
    parser.feed(html or "")
    text = "".join(parser._parts)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_research_marker(reply: str) -> str | None:
    """Extract the question after a ``RESEARCH:`` directive, if present.

    The directive may appear on any line (the model sometimes prefixes it with
    an apology or a short explanation), so search the whole reply rather than
    only its first characters.
    """
    if not reply:
        return None
    match = _RESEARCH_RE.search(reply)
    return match.group(1).strip() if match else None


def cache_key(url: str) -> str:
    """Stable, host-namespaced filename token for ``url``."""
    if not url:
        return "empty"
    without_query = url.split("?", 1)[0]
    host_part = without_query.split("//", 1)[-1].split("/", 1)[0].replace(":", "_")
    path_part = without_query.split("//", 1)[-1].split("/", 1)
    slug = path_part[1].strip("/").replace("/", "_").lower() if len(path_part) > 1 else "root"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"{host_part}_{slug or 'root'}_{digest}"


@dataclass
class ResearchEntry:
    text: str
    source: str
    fetched_at: float
    url: str

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.fetched_at)


class ResearchCache:
    """JSON-per-URL store kept on disk so we don't refetch on every restart."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def path_for(self, url: str) -> Path:
        return self._base / (cache_key(url) + ".json")

    def get(self, url: str) -> ResearchEntry | None:
        path = self.path_for(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        try:
            return ResearchEntry(
                text=str(payload["text"]),
                source=str(payload.get("source", "unknown")),
                fetched_at=float(payload.get("fetched_at", 0.0)),
                url=str(payload.get("url", url)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def put(self, url: str, text: str, *, source: str = "live") -> ResearchEntry:
        entry = ResearchEntry(
            text=text or "",
            source=source,
            fetched_at=time.time(),
            url=url,
        )
        path = self.path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "text": entry.text,
                    "source": entry.source,
                    "fetched_at": entry.fetched_at,
                    "url": entry.url,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return entry


@dataclass
class ResearchResult:
    """What the agent saw and where it came from (used by the AI prompt)."""

    question: str
    url: str
    text: str
    source: str  # "live", "wayback", "cache", "none"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.source != "none"


class _Blocked(urllib.error.URLError):
    """Marker so tests can distinguish blocked fetches from real errors."""


class Researcher:
    """Single-turn AQW web researcher with offline cache and Wayback fallback.

    Search uses Bing (``https://www.bing.com/search?q=site:aqwwiki.wikidot.com <q>``)
    because AQW Wiki itself does not answer from this host's network. When a
    direct fetch to the page fails (most common case here), the Wayback Machine
    ``/available`` endpoint is consulted and that snapshot is used instead.
    """

    DEFAULT_SEARCH_URL = "https://www.bing.com/search?q={query}"
    DEFAULT_WAYBACK_API = "https://archive.org/wayback/available?url={url}"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123 Safari/537.36 skua-lite/0.1"
    )

    def __init__(
        self,
        cache: ResearchCache,
        *,
        search_url: str | None = None,
        wayback_api: str | None = None,
        timeout: float = 8.0,
        page_timeout: float = 12.0,
    ) -> None:
        self._cache = cache
        self._search_url = search_url or self.DEFAULT_SEARCH_URL
        self._wayback_api = wayback_api or self.DEFAULT_WAYBACK_API
        self._timeout = timeout
        self._page_timeout = page_timeout

    # Public API -----------------------------------------------------------
    def fetch(self, url: str) -> ResearchResult:
        return self._fetch_from(url)

    def answer(self, question: str) -> ResearchResult:
        """Search the open web for ``question`` and return the best matching page.

        The marker may include a direct URL (``URL | original question``); that
        takes precedence and avoids unreliable search-result HTML.
        """
        question = (question or "").strip()
        if not question:
            return ResearchResult(question="", url="", text="", source="none",
                                  error="empty question")
        direct = extract_wiki_urls(question)
        if direct:
            return self._fetch_from(direct[0])
        try:
            html = self._http_get(self._format_search_url(question), "text/html")
            urls = extract_wiki_urls(html)
        except _Blocked:
            urls = []
        except Exception:
            urls = []
        if urls:
            return self._fetch_from(urls[0])
        # Bound the fallback: we never want an AQW chat reply to hang while
        # iterating dozens of guessed URLs.
        for slug in self._guess_slugs(question)[:6]:
            result = self._fetch_from(f"https://aqwwiki.wikidot.com/{slug}")
            if result.ok:
                return result
        return ResearchResult(
            question=question, url="", text="", source="none",
            error="no AQW Wiki URL found in search results",
        )

    def _fetch_from(self, url: str) -> ResearchResult:
        cached = self._cache.get(url)
        if cached is not None:
            return ResearchResult(
                question="", url=url, text=cached.text, source="cache",
            )
        text, html_error = self._try_fetch(url)
        if text:
            entry = self._cache.put(url, text, source="live")
            return ResearchResult(
                question="", url=url, text=entry.text, source=entry.source,
            )
        # Wayback fallback when the live fetch returns 0 useful bytes.
        wb_error = ""
        snapshot = self._wayback_url(url)
        if snapshot:
            wb_text, wb_error = self._try_fetch(snapshot)
            if wb_text:
                entry = self._cache.put(url, wb_text, source="wayback")
                return ResearchResult(
                    question="", url=url, text=entry.text,
                    source=entry.source,
                )
        return ResearchResult(
            question="", url=url, text="", source="none",
            error=html_error or wb_error or "empty page",
        )

    def _try_fetch(self, url: str) -> tuple[str, str]:
        try:
            html = self._http_get(url, "text/html", self._page_timeout)
            text = html_to_text(html)
        except _Blocked as exc:
            return "", f"network blocked: {exc}"
        except Exception as exc:  # noqa: BLE001
            return "", f"{type(exc).__name__}: {exc}"
        return text, ""

    _SLUG_SUFFIXES = ("", "-class", "-item", "-quest", "-monster", "-location")

    def _guess_slugs(self, question: str) -> list[str]:
        """Return slug candidates on AQW Wiki for a free-form question."""
        words = [
            w for w in re.findall(r"[A-Za-z][A-Za-z0-9']+", question)
            if w.lower() not in _QUESTION_STOP
        ]
        phrases: list[str] = []
        # Prefer the longest contiguous phrase, then shorter ones.
        for n in (4, 3, 2, 1):
            for i in range(len(words) - n + 1):
                phrases.append("-".join(w.lower() for w in words[i:i + n]))
        slug_set: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            for suffix in self._SLUG_SUFFIXES:
                slug = phrase + suffix
                if slug and slug not in seen:
                    slug_set.append(slug)
                    seen.add(slug)
        return slug_set

    # Internals -------------------------------------------------------------
    def _format_search_url(self, query: str) -> str:
        scoped = f"site:aqwwiki.wikidot.com {query}"
        return self._search_url.replace("{query}", urllib.parse.quote(scoped, safe=""))

    def _wayback_url(self, url: str) -> str | None:
        api = self._wayback_api.replace("{url}", urllib.parse.quote(url, safe=""))
        try:
            body = self._http_get(api, "application/json", self._timeout)
            snap = body.get("archived_snapshots", {}).get("closest") or {}
            candidate = snap.get("url")
        except _Blocked:
            return None
        except Exception:
            return None
        if not candidate or snap.get("available") is not True:
            return None
        # Force HTTPS for the Wayback redirector when present.
        return "https:" + candidate[5:] if candidate.startswith("http:") else candidate

    def _http_get(self, url: str, accept: str, timeout: float | None = None):
        """Tiny dependency-light fetcher; raises _Blocked on transport failure."""
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": accept + ", text/html;q=0.9, */*;q=0.5",
                "Accept-Language": "en-US,en;q=0.7,id;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self._timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise _Blocked(f"HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise _Blocked(str(exc)) from exc
        if accept.startswith("application/json"):
            try:
                return json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                raise _Blocked("invalid JSON body")
        return raw.decode("utf-8", "replace")


def _probe(question: str) -> None:
    """Light CLI for ``python -m skua_lite.research <question>``.

    Uses a per-user temp directory so Heartbeat probes never interfere with
    the bot's long-lived cache.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = Researcher(ResearchCache(Path(tmp))).answer(question)
    if not result.ok:
        print(f"[probe] gagal: {result.error}", flush=True)
        return
    snippet = result.text[:600].replace("\n", " ")
    print(
        f"[probe] src={result.source} url={result.url}\n"
        f"[probe] text={snippet}",
        flush=True,
    )


if __name__ == "__main__":
    import sys
    _probe(sys.argv[1] if len(sys.argv) > 1 else "Blade of Awe")