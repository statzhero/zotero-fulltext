"""Tests for Zotero API client edge cases."""

from __future__ import annotations

import unittest
from pathlib import Path

from zotero_fulltext.client import ZoteroClient
from zotero_fulltext.config import Settings
from zotero_fulltext.errors import ZoteroClientError


def make_settings() -> Settings:
    return Settings(
        api_base_url="http://127.0.0.1:23119/api",
        library_type="user",
        library_id="0",
        api_key=None,
        cache_dir=Path("unused"),
        index_refresh_min_interval_sec=15,
        paragraph_cache_ttl_sec=60,
        paragraph_cache_size=16,
        default_search_limit=10,
        default_fulltext_limit=80,
        default_fulltext_context=1,
        startup_sync=False,
    )


class FakeRequestClient(ZoteroClient):
    def __init__(self, status: int, payload: str) -> None:
        super().__init__(make_settings())
        self.status = status
        self.payload = payload

    def _request(self, method, path, *, params=None, headers=None):
        return self.status, {}, self.payload


class FakeDeletedClient(ZoteroClient):
    def __init__(self, response) -> None:
        super().__init__(make_settings())
        self.response = response

    def _request_json(self, method, path, *, params=None, headers=None):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ZoteroClientTest(unittest.TestCase):
    def test_request_json_allows_plain_text_404(self) -> None:
        client = FakeRequestClient(404, "Not Found")
        status, _, payload = client._request_json("GET", "users/0/deleted")
        self.assertEqual(status, 404)
        self.assertIsNone(payload)

    def test_get_deleted_treats_404_as_unavailable_endpoint(self) -> None:
        client = FakeDeletedClient((404, {}, None))
        deleted, version = client.get_deleted(5)
        self.assertEqual(deleted, [])
        self.assertIsNone(version)

    def test_get_deleted_propagates_client_errors(self) -> None:
        client = FakeDeletedClient(ZoteroClientError("temporary failure"))
        with self.assertRaises(ZoteroClientError):
            client.get_deleted(5)

    def test_not_modified_reports_lower_library_version(self) -> None:
        # Zotero answers 304 when its version is below the cursor too.
        client = FakeDeletedClient((304, {"Last-Modified-Version": "58"}, None))
        changed, versions, version = client.get_changed_item_versions(
            26853, if_modified_since_version=26853
        )
        self.assertFalse(changed)
        self.assertEqual(versions, {})
        self.assertEqual(version, 58)

    def test_not_modified_without_header_keeps_cursor(self) -> None:
        client = FakeDeletedClient((304, {}, None))
        _, _, version = client.get_changed_item_versions(5, if_modified_since_version=5)
        self.assertEqual(version, 5)


if __name__ == "__main__":
    unittest.main()
