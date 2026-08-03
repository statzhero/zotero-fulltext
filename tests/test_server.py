"""Tests for the MCP server wiring: tool/resource registration and the error envelope."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import anyio

from zotero_fulltext.config import Settings
from zotero_fulltext.errors import NoFulltextError, ZoteroUnavailableError
from zotero_fulltext.index import MetadataIndex
from zotero_fulltext.server import create_server
from zotero_fulltext.service import ZoteroFulltextService


class FakeClient:
    """Minimal client; ``list_collections`` fails to exercise the error envelope."""

    def fetch_all_items(self):
        return [], 0

    def get_changed_item_versions(self, since, *, if_modified_since_version=None):
        return False, {}, since

    def get_deleted(self, since):
        return [], since

    def get_items_by_keys(self, item_keys):
        return []

    def search_items(self, query, *, collection=None, tag=None, limit=10):
        return []

    def list_collections(self):
        raise ZoteroUnavailableError("Zotero is not running")

    def get_children(self, item_key):
        return []

    def get_fulltext(self, attachment_key):
        raise NoFulltextError("no fulltext")


def make_settings(cache_dir: str) -> Settings:
    return Settings(
        api_base_url="http://127.0.0.1:23119/api",
        library_type="user",
        library_id="0",
        api_key=None,
        cache_dir=Path(cache_dir),
        index_refresh_min_interval_sec=999999,
        paragraph_cache_ttl_sec=60,
        paragraph_cache_size=16,
        default_search_limit=10,
        default_fulltext_limit=80,
        default_fulltext_context=1,
        startup_sync=False,
        max_paragraph_chars=1800,
        max_fulltext_chars=60000,
    )


class CreateServerTest(unittest.TestCase):
    def build(self, cache_dir: str):
        service = ZoteroFulltextService(
            make_settings(cache_dir),
            client=FakeClient(),
            index=MetadataIndex(library_version=5),
        )
        return create_server(service=service)

    def test_registers_expected_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp = self.build(temp_dir)
            tools = anyio.run(mcp.list_tools)
        self.assertEqual(
            sorted(tool.name for tool in tools),
            ["collections", "fulltext", "fulltext_search", "lookup", "search"],
        )

    def test_registers_expected_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp = self.build(temp_dir)
            resources = anyio.run(mcp.list_resources)
            templates = anyio.run(mcp.list_resource_templates)
        self.assertIn("zotero://library", [str(resource.uri) for resource in resources])
        self.assertEqual(
            sorted(template.uriTemplate for template in templates),
            ["zotero://fulltext/{citekey}", "zotero://item/{citekey}"],
        )

    def test_client_failure_becomes_error_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mcp = self.build(temp_dir)

            async def call():
                return await mcp.call_tool("collections", {})

            _content, structured = anyio.run(call)
        self.assertFalse(structured["available"])
        self.assertEqual(structured["error"], "ZOTERO_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
