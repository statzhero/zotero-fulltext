"""Paragraph extraction and paragraph-level search helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .index import fold_text


_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
# What a line break can leave inside a word: whitespace, and the hyphen of a
# word hyphenated at the line end ("sus pect", "robust- ness").
_WORD_GAP = r"[\s\-\u2010\u2011\u00ad]*"
DEFAULT_MAX_PARAGRAPH_CHARS = 1800


def normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace while preserving readable text."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_paragraphs(text: str, *, max_chars: int = DEFAULT_MAX_PARAGRAPH_CHARS) -> list[str]:
    """Convert raw fulltext into stable, numbered paragraphs."""
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs: list[str] = []
    for chunk in _PARAGRAPH_SPLIT_RE.split(normalized):
        paragraph = normalize_whitespace(chunk)
        if paragraph:
            paragraphs.extend(split_long_paragraph(paragraph, max_chars=max_chars))
    return paragraphs


def split_long_paragraph(text: str, *, max_chars: int = DEFAULT_MAX_PARAGRAPH_CHARS) -> list[str]:
    """Split oversized paragraphs into bounded, word-aware chunks."""
    safe_max_chars = max(1, max_chars)
    if len(text) <= safe_max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + safe_max_chars, text_length)
        if end < text_length:
            split_at = text.rfind(" ", start, end + 1)
            if split_at > start:
                end = split_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
        while start < text_length and text[start].isspace():
            start += 1
    return chunks


def paragraph_slice(
    paragraphs: list[str],
    offset: int = 0,
    limit: int = 80,
    *,
    max_chars: int | None = None,
) -> list[dict[str, object]]:
    """Return a numbered slice of paragraphs."""
    safe_offset = max(0, offset)
    safe_limit = max(1, limit)
    selected = paragraphs[safe_offset : safe_offset + safe_limit]
    payload: list[dict[str, object]] = []
    used_chars = 0
    for index, text in enumerate(selected):
        if max_chars is not None and payload and used_chars + len(text) > max_chars:
            break
        payload.append({"paragraph": safe_offset + index + 1, "text": text})
        used_chars += len(text)
    return payload


def _fold(text: str) -> str:
    """Fold case, diacritics, and ligatures, and collapse whitespace."""
    return normalize_whitespace(fold_text(text))


def _loose_pattern(folded: str) -> re.Pattern[str] | None:
    """Match the letters and digits of ``folded`` from a word start.

    Whitespace and hyphens may sit between any two of them, so a word that
    the PDF text broke across lines still matches.
    """
    chars = [char for char in folded if char.isalnum()]
    if not chars:
        return None
    return re.compile(r"(?<![^\W_])" + _WORD_GAP.join(re.escape(char) for char in chars))


@dataclass(frozen=True)
class _Query:
    phrase: str
    phrase_pattern: re.Pattern[str] | None
    terms: tuple[tuple[str, re.Pattern[str] | None], ...]

    @classmethod
    def compile(cls, query: str) -> "_Query":
        phrase = _fold(query)
        terms = tuple((term, _loose_pattern(term)) for term in phrase.split(" ") if term)
        return cls(phrase, _loose_pattern(phrase), terms)

    def matches(self, text: str) -> bool:
        """Match the whole phrase, or else every term somewhere in ``text``."""
        if not self.phrase:
            return False
        folded = _fold(text)
        if self.phrase in folded:
            return True
        if self.phrase_pattern is not None and self.phrase_pattern.search(folded):
            return True
        return all(
            term in folded or (pattern is not None and pattern.search(folded) is not None)
            for term, pattern in self.terms
        )


def paragraph_matches(text: str, query: str) -> bool:
    """Match a paragraph ignoring case, diacritics, ligatures, and line-broken words."""
    return _Query.compile(query).matches(text)


def search_paragraphs(
    paragraphs: list[str],
    query: str,
    *,
    before: int = 1,
    after: int = 1,
    limit: int = 20,
) -> list[dict[str, object]]:
    """Search paragraphs and return local context around each match."""
    safe_before = max(0, before)
    safe_after = max(0, after)
    safe_limit = max(1, limit)
    compiled = _Query.compile(query)
    results: list[dict[str, object]] = []
    for index, paragraph in enumerate(paragraphs):
        if not compiled.matches(paragraph):
            continue
        context_before = [
            {"paragraph": context_index + 1, "text": paragraphs[context_index]}
            for context_index in range(max(0, index - safe_before), index)
        ]
        context_after = [
            {"paragraph": context_index + 1, "text": paragraphs[context_index]}
            for context_index in range(index + 1, min(len(paragraphs), index + safe_after + 1))
        ]
        results.append(
            {
                "paragraph": index + 1,
                "text": paragraph,
                "context_before": context_before,
                "context_after": context_after,
            }
        )
        if len(results) >= safe_limit:
            break
    return results
