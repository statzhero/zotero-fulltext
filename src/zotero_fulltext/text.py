"""Paragraph extraction and paragraph-level search helpers."""

from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
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


def _normalized_query(query: str) -> str:
    return normalize_whitespace(query).casefold()


def paragraph_matches(text: str, query: str) -> bool:
    """Case-insensitive paragraph match."""
    normalized_query = _normalized_query(query)
    terms = [term for term in normalized_query.split(" ") if term]
    return _paragraph_matches_normalized(text, normalized_query, terms)


def _paragraph_matches_normalized(text: str, normalized_query: str, terms: list[str]) -> bool:
    normalized_text = normalize_whitespace(text).casefold()
    if not normalized_query:
        return False
    if normalized_query in normalized_text:
        return True
    return bool(terms) and all(term in normalized_text for term in terms)


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
    normalized_query = _normalized_query(query)
    terms = [term for term in normalized_query.split(" ") if term]
    results: list[dict[str, object]] = []
    for index, paragraph in enumerate(paragraphs):
        if not _paragraph_matches_normalized(paragraph, normalized_query, terms):
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
