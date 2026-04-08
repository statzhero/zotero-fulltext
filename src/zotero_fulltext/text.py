"""Paragraph extraction and paragraph-level search helpers."""

from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")


def normalize_whitespace(text: str) -> str:
    """Collapse internal whitespace while preserving readable text."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def extract_paragraphs(text: str) -> list[str]:
    """Convert raw fulltext into stable, numbered paragraphs."""
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    paragraphs = [
        normalize_whitespace(chunk)
        for chunk in _PARAGRAPH_SPLIT_RE.split(normalized)
        if normalize_whitespace(chunk)
    ]
    return paragraphs


def paragraph_slice(paragraphs: list[str], offset: int = 0, limit: int = 80) -> list[dict[str, object]]:
    """Return a numbered slice of paragraphs."""
    safe_offset = max(0, offset)
    safe_limit = max(1, limit)
    selected = paragraphs[safe_offset : safe_offset + safe_limit]
    return [
        {"paragraph": safe_offset + index + 1, "text": text}
        for index, text in enumerate(selected)
    ]


def _normalized_query(query: str) -> str:
    return normalize_whitespace(query).casefold()


def paragraph_matches(text: str, query: str) -> bool:
    """Case-insensitive paragraph match."""
    normalized_text = normalize_whitespace(text).casefold()
    normalized_query = _normalized_query(query)
    if not normalized_query:
        return False
    if normalized_query in normalized_text:
        return True
    terms = [term for term in normalized_query.split(" ") if term]
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
    results: list[dict[str, object]] = []
    for index, paragraph in enumerate(paragraphs):
        if not paragraph_matches(paragraph, query):
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
