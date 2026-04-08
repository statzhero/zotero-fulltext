"""Tests for citekey indexing and incremental updates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zotero_fulltext.index import MetadataIndex


def make_item(
    key: str,
    *,
    title: str,
    version: int = 1,
    citation_key: str | None = None,
    extra: str = "",
    creators: list[dict[str, str]] | None = None,
    date: str = "2020",
    item_type: str = "journalArticle",
    deleted: bool = False,
) -> dict[str, object]:
    return {
        "key": key,
        "version": version,
        "data": {
            "key": key,
            "version": version,
            "itemType": item_type,
            "title": title,
            "date": date,
            "citationKey": citation_key,
            "extra": extra,
            "creators": creators or [{"creatorType": "author", "lastName": "Smith"}],
            "collections": [],
            "tags": [],
            "deleted": deleted,
        },
    }


def make_attachment(
    key: str,
    *,
    parent: str,
    version: int = 1,
    content_type: str = "application/pdf",
) -> dict[str, object]:
    return {
        "key": key,
        "version": version,
        "data": {
            "key": key,
            "version": version,
            "itemType": "attachment",
            "parentItem": parent,
            "title": "PDF",
            "contentType": content_type,
            "linkMode": "imported_file",
        },
    }


class MetadataIndexTest(unittest.TestCase):
    def test_prefers_native_citation_key_over_extra(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [
                make_item(
                    "AAA111",
                    title="Paper",
                    citation_key="native2024",
                    extra="Citation Key: legacy2024",
                )
            ],
            5,
        )
        record = index.get_by_citekey("native2024")
        self.assertIsNotNone(record)
        self.assertEqual(record.citation_key, "native2024")

    def test_uses_legacy_extra_when_native_missing(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [make_item("AAA111", title="Paper", extra="Citation Key: legacy2024")],
            5,
        )
        self.assertIsNotNone(index.get_by_citekey("legacy2024"))

    def test_generates_stable_collision_suffixes(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [
                make_item("AAA111", title="One", citation_key=None),
                make_item("BBB222", title="Two", citation_key=None),
            ],
            5,
        )
        keys = sorted(record.citation_key for record in index.items_by_key.values())
        self.assertEqual(keys, ["smith2020", "smith2020a"])

    def test_promotes_generated_key_to_real_key_and_keeps_alias(self) -> None:
        previous = MetadataIndex.rebuild_from_items(
            [make_item("AAA111", title="Paper", citation_key=None)],
            5,
        )
        generated_key = previous.items_by_key["AAA111"].citation_key

        updated = [make_item("AAA111", title="Paper", citation_key="real2020", version=6)]
        previous.apply_updates(updated, [], 6)
        record = previous.items_by_key["AAA111"]
        self.assertEqual(record.citation_key, "real2020")
        self.assertIn(generated_key, record.aliases)
        self.assertEqual(previous.get_by_citekey(generated_key).item_key, "AAA111")

    def test_attachment_selection_prefers_pdf(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [
                make_item("AAA111", title="Paper", citation_key="paper2020"),
                make_attachment("ATTTXT", parent="AAA111", content_type="text/plain"),
                make_attachment("ATTPDF", parent="AAA111", content_type="application/pdf"),
            ],
            5,
        )
        self.assertEqual(index.items_by_key["AAA111"].attachment_key, "ATTPDF")

    def test_deleted_items_are_removed(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [
                make_item("AAA111", title="Paper", citation_key="paper2020"),
                make_attachment("ATTPDF", parent="AAA111"),
            ],
            5,
        )
        index.apply_updates([], ["AAA111"], 6)
        self.assertIsNone(index.get_by_citekey("paper2020"))
        self.assertNotIn("ATTPDF", index.attachments_by_key)

    def test_round_trip_save_and_load(self) -> None:
        index = MetadataIndex.rebuild_from_items(
            [make_item("AAA111", title="Paper", citation_key="paper2020")],
            5,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "index.json"
            index.save(path)
            loaded = MetadataIndex.load(path)
        self.assertEqual(loaded.library_version, 5)
        self.assertIsNotNone(loaded.get_by_citekey("paper2020"))


if __name__ == "__main__":
    unittest.main()
