"""Tests for the offline-online hybrid research agent (planned, intent-only).

The bot runs inside a REPL that is periodically kicked with `intent`. These
tests exercise the pure building blocks that the full agent will use, without
touching the network: URL discovery, HTML-to-text extraction, the `RESEARCH:`
marker parser, and cache-key extraction. Network fetches themselves are
expected to be exercised only through the `scripts/research_agent.py` runner
against a live endpoint — never asserted here.
"""
from skua_lite import research


def test_find_stonecrusher_page_url_extracts_aqw_wiki_link():
    html = (
        "<a href='https://aqwwiki.wikidot.com/stonecrusher'>StoneCrusher</a> "
        "<a href='https://aqwwiki.wikidot.com/stonecrusher'>x</a>"
    )
    urls = research.extract_wiki_urls(html)
    assert any("aqwwiki.wikidot.com/stonecrusher" in url for url in urls)
    assert len(urls) == 1


def test_extract_wiki_urls_skips_non_wikidot_domains():
    html = (
        "<a href='https://www.reddit.com/r/AQW'>r</a> "
        "<a href='https://aqwwiki.wikidot.com/void-highlord'>vhl</a>"
    )
    urls = research.extract_wiki_urls(html)
    assert any("aqwwiki.wikidot.com/void-highlord" in url for url in urls)
    assert all("aqwwiki.wikidot.com" in url for url in urls)


def test_html_to_text_keeps_headings_and_paragraphs():
    html = (
        "<html><body><h1>StoneCrusher</h1>"
        "<p>Roles: Support.</p><table><tr><td>Skill</td></tr></table>"
        "</body></html>"
    )
    text = research.html_to_text(html)
    assert "StoneCrusher" in text
    assert "Support" in text


def test_research_marker_parser_returns_intent():
    assert research.parse_research_marker(
        "RESEARCH: what does StoneCrusher do?"
    ) == "what does StoneCrusher do?"


def test_research_marker_parser_none_for_plain_text():
    assert research.parse_research_marker("just a normal message") is None


def test_cache_key_is_stable_and_host_namespaced():
    a = research.cache_key("https://aqwwiki.wikidot.com/stonecrusher")
    b = research.cache_key("https://aqwwiki.wikidot.com/stonecrusher")
    assert a == b
    assert a.startswith("aqwwiki.wikidot.com_")


def test_cache_round_trip_returns_stored_text(tmp_path):
    cache = research.ResearchCache(tmp_path)
    url = "https://aqwwiki.wikidot.com/stonecrusher"
    assert cache.get(url) is None
    cache.put(url, "StoneCrusher is a support class.", source="live")
    entry = cache.get(url)
    assert entry is not None
    assert "support class" in entry.text
    assert entry.source == "live"
    assert cache.path_for(url).exists()


def test_cache_survives_a_new_instance(tmp_path):
    url = "https://aqwwiki.wikidot.com/void-highlord"
    research.ResearchCache(tmp_path).put(url, "VHL is a DPS class.", source="wayback")
    reopened = research.ResearchCache(tmp_path)
    entry = reopened.get(url)
    assert entry is not None
    assert "DPS" in entry.text


def test_cache_reports_age_for_stale_snapshot_warnings(tmp_path):
    cache = research.ResearchCache(tmp_path)
    url = "https://aqwwiki.wikidot.com/dage"
    cache.put(url, "Ultra Dage guide.", source="wayback")
    entry = cache.get(url)
    assert entry is not None
    assert entry.age_seconds >= 0


def test_researcher_direct_url_fetches_page_and_caches(tmp_path):
    url = "https://aqwwiki.wikidot.com/archpaladin"

    class FakeResearcher(research.Researcher):
        def _http_get(self, request_url, accept, timeout=None):
            assert request_url == url
            return "<h1>ArchPaladin</h1><p>Class support.</p>"

    cache = research.ResearchCache(tmp_path)
    result = FakeResearcher(cache).answer(url + " | ArchPaladin class")

    assert result.ok is True
    assert result.source == "live"
    assert "ArchPaladin" in result.text
    assert cache.get(url) is not None


def test_researcher_uses_wayback_after_live_fetch_fails(tmp_path):
    url = "https://aqwwiki.wikidot.com/archpaladin"
    snapshot = "https://web.archive.org/web/20250821170524/http://aqwwiki.wikidot.com/archpaladin"

    class FakeResearcher(research.Researcher):
        def _http_get(self, request_url, accept, timeout=None):
            if request_url == url:
                raise research._Blocked("blocked")
            if request_url.startswith("https://archive.org/wayback/available?"):
                return {
                    "archived_snapshots": {
                        "closest": {"available": True, "url": snapshot.replace("https:", "http:", 1)}
                    }
                }
            if request_url == snapshot:
                return "<h1>ArchPaladin</h1><p>Archived class information.</p>"
            raise AssertionError(f"unexpected URL: {request_url}")

    result = FakeResearcher(research.ResearchCache(tmp_path)).fetch(url)

    assert result.ok is True
    assert result.source == "wayback"
    assert "Archived class information" in result.text


def test_researcher_reuses_cache_without_network(tmp_path):
    url = "https://aqwwiki.wikidot.com/archpaladin"
    cache = research.ResearchCache(tmp_path)
    cache.put(url, "cached ArchPaladin data", source="wayback")

    class NetworkMustNotRun(research.Researcher):
        def _http_get(self, request_url, accept, timeout=None):
            raise AssertionError("cache hit must not access network")

    result = NetworkMustNotRun(cache).fetch(url)

    assert result.ok is True
    assert result.source == "cache"
    assert result.text == "cached ArchPaladin data"