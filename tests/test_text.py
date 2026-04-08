"""Tests for paragraph extraction and paragraph-level search."""

from __future__ import annotations

import unittest

from zotero_fulltext.text import extract_paragraphs, paragraph_matches, paragraph_slice, search_paragraphs


class TextHelpersTest(unittest.TestCase):
    def test_extract_paragraphs_collapses_whitespace(self) -> None:
        raw = "First line\ncontinues.\n\nSecond   paragraph.\n\n\nThird\tparagraph."
        self.assertEqual(
            extract_paragraphs(raw),
            [
                "First line continues.",
                "Second paragraph.",
                "Third paragraph.",
            ],
        )

    def test_paragraph_slice_returns_stable_numbers(self) -> None:
        paragraphs = ["a", "b", "c", "d"]
        self.assertEqual(
            paragraph_slice(paragraphs, offset=1, limit=2),
            [
                {"paragraph": 2, "text": "b"},
                {"paragraph": 3, "text": "c"},
            ],
        )

    def test_paragraph_matches_phrase_or_termwise(self) -> None:
        self.assertTrue(paragraph_matches("Correlated forecast errors matter.", "forecast errors"))
        self.assertTrue(paragraph_matches("Correlated forecast errors matter.", "correlated matter"))
        self.assertFalse(paragraph_matches("Correlated forecast errors matter.", "analyst career"))

    def test_search_paragraphs_includes_context(self) -> None:
        paragraphs = [
            "Intro",
            "Errors are correlated across analysts.",
            "The model predicts a profitability wedge.",
            "Conclusion",
        ]
        matches = search_paragraphs(paragraphs, "correlated", before=1, after=1, limit=5)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["paragraph"], 2)
        self.assertEqual(matches[0]["context_before"][0]["paragraph"], 1)
        self.assertEqual(matches[0]["context_after"][0]["paragraph"], 3)


if __name__ == "__main__":
    unittest.main()
