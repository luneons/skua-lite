"""Loader and keyword retrieval for local AQW Ultra Boss guides."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_STOPWORDS = frozenset({
    "ultra", "boss", "aqw", "cara", "melawan", "lawan", "info", "tentang",
    "gimana", "bagaimana", "apa", "yang", "itu", "ini", "dan", "atau",
    "dengan", "untuk", "dari", "ke", "di", "ya", "dong", "sih", "bro",
    "tuan", "mele", "the", "a", "of", "to", "in", "on", "is", "how", "do",
    "what", "about", "guide", "panduan",
})
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.MULTILINE)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_WORD_RE = re.compile(r"[a-z0-9']+")
_MIN_TOKEN_LEN = 4

# Context window sizing. The AQW reply itself is capped at 150 chars, but the
# model can read far more before summarising, so give it a wide slice of the
# guide (mechanics + setup + mistakes) while keeping the prompt bounded.
_SECTION_CHAR_LIMIT = 1200
_MAX_SECTIONS = 10
_TOTAL_PROMPT_BUDGET = 7000
# Sections that must always travel with a named boss so the AI can answer
# "how do I fight it" without losing the standard recipe.
_CORE_SECTION_HINTS = (
    "party composition",
    "setup",
    "overview",
    "informasi dasar",
    "tldr",
    "tl;dr",
    "inti",
)


def _strip_markdown(text: str) -> str:
    text = _FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)


def _tokens(text: str) -> list[str]:
    return [
        word
        for word in _WORD_RE.findall(text.lower())
        if word not in _STOPWORDS and len(word) >= _MIN_TOKEN_LEN
    ]


def _contains_word(haystack: str, word: str) -> bool:
    """Whole-word match so short tokens don't hit inside other words."""
    return re.search(rf"\b{re.escape(word)}\b", haystack) is not None


def _boss_key_from_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _display_name(stem: str) -> str:
    base = stem.lower()
    if base.startswith("ultra"):
        base = "Ultra " + base[5:]
    return base.title()


def _trim(text: str, limit: int) -> str:
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(".", 1)[0]
    return (cut or text[:limit]).rstrip() + "..."


def _cap_prompt(text: str, budget: int) -> str:
    """Truncate a context block to ``budget`` characters on a section boundary."""
    if len(text) <= budget:
        return text
    # Keep the header (first paragraph) and as many `### ...` blocks as fit.
    head, _, body = text.partition("\n")
    header = head + "\n"
    blocks: list[str] = []
    used = len(header)
    for block in body.split("\n### "):
        chunk = "### " + block if blocks or block.startswith("### ") else block
        size = len(chunk) + 2  # account for the joining "\n\n"
        if used + size > budget and blocks:
            break
        blocks.append(chunk)
        used += size
    if not blocks:
        return header + text[len(header):][: budget - len(header)].rstrip()
    return header + "\n\n".join(blocks).rstrip()


def _is_core_section(title: str) -> bool:
    lowered = title.lower()
    return any(hint in lowered for hint in _CORE_SECTION_HINTS)


@dataclass
class UltraBossDoc:
    key: str
    display_name: str
    source_file: str
    sections: list[tuple[str, str]] = field(default_factory=list)

    def loadout_sections(self, keywords: list[str]) -> list[tuple[str, str]]:
        """Sections whose heading is a per-class loadout heading.

        Handles both "Enhancement & Potion" style headings and the Darkon guide's
        "StoneCrusher — Taunter/HoT" heading style. Class-name headings win when
        the question names that class.
        """
        generic = ("enhancement", "potion", "equipment", "gear", "loadout", "build")
        wanted = [k.lower() for k in keywords if len(k) >= 2]
        scored: list[tuple[int, str, str]] = []
        for title, body in self.sections:
            lowered = title.lower()
            score = 0
            if any(hint in lowered for hint in generic):
                score += 1
            if any(word in lowered for word in wanted):
                score += 2
            if score:
                scored.append((score, title, body))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(title, body) for _, title, body in scored]

    def scored_sections(
        self,
        keywords: list[str],
        limit: int = _MAX_SECTIONS,
        keep_core: bool = True,
    ) -> list[tuple[int, str, str]]:
        """Rank sections by matches in heading/body.

        ``keep_core=True`` guarantees that a few always-useful sections
        (setup, party composition, overview, TL;DR) travel with the prompt
        so the model can answer "how do I fight it" without missing the
        standard recipe even when no keyword matched them directly.
        """
        scored: list[tuple[int, str, str]] = []
        seen: set[int] = set()
        for title, body in self.sections:
            heading = title.lower()
            haystack = f"{heading}\n{body.lower()}"
            score = sum(
                3 if _contains_word(heading, word) else 1
                for word in keywords
                if _contains_word(haystack, word)
            )
            if score:
                scored.append((score, title, body))
        if keep_core:
            extras = [
                (title, body)
                for title, body in self.sections
                if _is_core_section(title)
                and id(body) not in seen
                and not any(body is b for _, _, b in scored)
            ]
            scored = [(0, title, body) for title, body in extras] + scored
            seen.update(id(body) for _, _, body in scored)
        scored.sort(key=lambda item: (item[0], self._title_order(item[1])), reverse=True)
        return scored[:limit]

    @staticmethod
    def _title_order(title: str) -> int:
        """Slight bias: earlier sections (low indices) win ties."""
        # Use negative because sort is descending on score.
        return -len(title)

    def matched_keywords(self, keywords: list[str]) -> set[str]:
        """Which query keywords actually appear in this boss's sections."""
        hits: set[str] = set()
        for _title, body in self.sections:
            haystack = body.lower()
            for word in keywords:
                if _contains_word(haystack, word):
                    hits.add(word)
        return hits

    def summary(
        self,
        keywords: list[str] | None = None,
        max_sections: int = _MAX_SECTIONS,
        section_char_limit: int = _SECTION_CHAR_LIMIT,
    ) -> str:
        head = (
            f"## {self.display_name}\n"
            "Kutipan bagian relevan; rujuk file sumber untuk detail lengkap.\n"
        )
        chosen = self.scored_sections(keywords or [], max_sections)
        if not chosen:
            chosen = [(0, title, body) for title, body in self.sections[:max_sections]]
        parts = [
            f"### {title}\n{_trim(_strip_markdown(body), section_char_limit)}"
            for _, title, body in chosen
        ]
        return head + "\n".join(parts)


@dataclass
class UltraGuide:
    bosses: dict[str, UltraBossDoc] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)

    @classmethod
    def discover(cls, base_dir: str | Path) -> "UltraGuide":
        base = Path(base_dir)
        guide = cls()
        if not base.exists():
            return guide
        for path in sorted(base.rglob("*.md")):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            key = _boss_key_from_name(path.stem)
            doc = UltraBossDoc(
                key=key,
                display_name=_display_name(path.stem),
                source_file=str(path.relative_to(base)),
                sections=_extract_sections(text),
            )
            guide.bosses[key] = doc
            guide.source_files.append(doc.source_file)
        return guide

    @property
    def boss_names(self) -> list[str]:
        return sorted(self.bosses)

    def section(self, key: str) -> str:
        doc = self.bosses.get(key)
        # Overview of the whole guide, so take more sections than a
        # keyword-scored answer would.
        return doc.summary(max_sections=12) if doc else ""

    def loadout_for(self, keywords: list[str], limit: int = 3) -> str:
        """Return enhancement/potion sections across bosses matching keywords.

        Used for class loadout questions that name no boss. Only sections whose
        heading is about loadout are returned, so the prompt stays small.
        """
        blocks: list[str] = []
        seen: set[str] = set()
        for doc in self.bosses.values():
            for title, body in doc.loadout_sections(keywords):
                key = f"{doc.key}:{title}"
                if key in seen:
                    continue
                seen.add(key)
                text = _trim(_strip_markdown(body), _SECTION_CHAR_LIMIT)
                blocks.append(f"### {doc.display_name} — {title}\n{text}")
                if len(blocks) >= limit:
                    return "\n\n".join(blocks)
        return "\n\n".join(blocks)

    def context_for(self, message: str) -> str:
        """Retrieve the boss/sections relevant to a question.

        A boss is included when the question names it, or when at least two
        distinct keywords from the question actually occur in its guide.
        A bare "ultra" question with no specific keywords gets a short index
        of every loaded guide rather than all of their contents.

        The returned text is bounded by ``_TOTAL_PROMPT_BUDGET`` so the prompt
        stays under typical chat-completion limits even with multiple bosses.
        """
        keywords = _tokens(message)
        lowered = message.lower()
        compact = re.sub(r"[^a-z0-9]+", "", lowered)

        # Match a named boss by full key (ultradage) or its bare name (dage).
        named: list[str] = []
        for key in self.bosses:
            bare = key.replace("ultra", "")
            if key in compact or (bare and _contains_word(lowered, bare)):
                named.append(key)

        is_generic_ultra = "ultra" in lowered and not named
        if not keywords and not named and not is_generic_ultra:
            return ""

        header = (
            "KONTEKS PANDUAN ULTRA BOSS AQW (gunakan hanya fakta relevan; jawab "
            "singkat dalam bahasa Indonesia; jangan menyebut nama file/sumber "
            "di jawaban chat; jangan mengarang mekanik):\n"
        )

        bodies: list[str] = []
        if named:
            bodies = [self.bosses[key].summary(keywords) for key in named]
        else:
            # No boss named: only include bosses with real keyword overlap.
            for doc in self.bosses.values():
                if len(doc.matched_keywords(keywords)) >= 2:
                    bodies.append(doc.summary(keywords))

        if bodies:
            return _cap_prompt(header + "\n\n".join(bodies), _TOTAL_PROMPT_BUDGET)

        # Generic ultra question: a one-line index, not the full guides.
        if is_generic_ultra and self.bosses:
            lines = [
                f"- {doc.display_name}: {doc.source_file}"
                for doc in self.bosses.values()
            ]
            return header + "Panduan yang tersedia:\n" + "\n".join(lines)
        return ""


def _extract_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((match.group(2).strip(), body))
    return sections
