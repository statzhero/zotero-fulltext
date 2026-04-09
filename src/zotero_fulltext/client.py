"""Minimal Zotero local API client."""

from __future__ import annotations

from collections.abc import Iterator
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import Settings
from .errors import NoFulltextError, ZoteroClientError, ZoteroNotFoundError, ZoteroUnavailableError


class ZoteroClient:
    """HTTP client for Zotero's local API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_all_items(self) -> tuple[list[dict[str, Any]], int | None]:
        """Fetch all items, including attachments, from the library."""
        all_items: list[dict[str, Any]] = []
        start = 0
        library_version: int | None = None
        while True:
            status, headers, payload = self._request_json(
                "GET",
                f"{self.settings.library_prefix}/items",
                params={"includeTrashed": 1, "limit": 100, "start": start},
            )
            if status != 200:
                raise ZoteroClientError(f"Unexpected Zotero status {status} while fetching items.")
            if library_version is None:
                library_version = _header_int(headers, "Last-Modified-Version")
            items = payload if isinstance(payload, list) else []
            all_items.extend(items)
            if len(items) < 100:
                break
            start += len(items)
        return all_items, library_version

    def get_changed_item_versions(
        self,
        since: int,
        *,
        if_modified_since_version: int | None = None,
    ) -> tuple[bool, dict[str, int], int | None]:
        """Return changed item versions after a given library version."""
        headers: dict[str, str] = {}
        if if_modified_since_version is not None:
            headers["If-Modified-Since-Version"] = str(if_modified_since_version)
        status, response_headers, payload = self._request_json(
            "GET",
            f"{self.settings.library_prefix}/items",
            params={"since": since, "format": "versions", "includeTrashed": 1},
            headers=headers,
        )
        if status == 304:
            return False, {}, if_modified_since_version
        if status != 200:
            raise ZoteroClientError(
                f"Unexpected Zotero status {status} while checking for item changes."
            )
        versions = {
            str(key): int(value)
            for key, value in (payload or {}).items()
        }
        return True, versions, _header_int(response_headers, "Last-Modified-Version")

    def get_deleted(self, since: int) -> tuple[list[str], int | None]:
        """Return deleted item keys since a given library version.

        Returns an empty list when the endpoint is unavailable (e.g. the
        local Zotero API does not implement ``/deleted``).
        """
        try:
            status, headers, payload = self._request_json(
                "GET",
                f"{self.settings.library_prefix}/deleted",
                params={"since": since},
            )
        except ZoteroClientError:
            return [], None
        if status == 404:
            return [], None
        if status != 200:
            raise ZoteroClientError(f"Unexpected Zotero status {status} while fetching deletes.")
        deleted_items = payload.get("items", []) if isinstance(payload, dict) else []
        return [str(value) for value in deleted_items], _header_int(headers, "Last-Modified-Version")

    def get_items_by_keys(self, item_keys: list[str]) -> list[dict[str, Any]]:
        """Retrieve specific items in batches of up to fifty keys."""
        if not item_keys:
            return []
        status, _, payload = self._request_json(
            "GET",
            f"{self.settings.library_prefix}/items",
            params={"itemKey": ",".join(item_keys), "includeTrashed": 1},
        )
        if status != 200:
            raise ZoteroClientError(f"Unexpected Zotero status {status} while fetching items by key.")
        return payload if isinstance(payload, list) else []

    def search_items(
        self,
        query: str,
        *,
        collection: str | None = None,
        tag: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search library items using Zotero's quick search."""
        params: dict[str, object] = {
            "q": query,
            "qmode": "everything",
            "limit": max(1, min(100, limit)),
            "includeTrashed": 0,
            "sort": "dateModified",
            "direction": "desc",
        }
        if tag:
            params["tag"] = tag
        path = f"{self.settings.library_prefix}/items"
        if collection:
            path = f"{self.settings.library_prefix}/collections/{collection}/items"
        status, _, payload = self._request_json("GET", path, params=params)
        if status == 404:
            raise ZoteroNotFoundError(f"Collection {collection!r} was not found in Zotero.")
        if status != 200:
            raise ZoteroClientError(f"Unexpected Zotero status {status} while searching items.")
        return payload if isinstance(payload, list) else []

    def list_collections(self) -> list[dict[str, Any]]:
        """Return all collections in the current library."""
        collections: list[dict[str, Any]] = []
        start = 0
        while True:
            status, _, payload = self._request_json(
                "GET",
                f"{self.settings.library_prefix}/collections",
                params={"limit": 100, "start": start},
            )
            if status != 200:
                raise ZoteroClientError(
                    f"Unexpected Zotero status {status} while listing collections."
                )
            batch = payload if isinstance(payload, list) else []
            collections.extend(batch)
            if len(batch) < 100:
                break
            start += len(batch)
        return collections

    def get_children(self, item_key: str) -> list[dict[str, Any]]:
        """Return child items for a Zotero item."""
        status, _, payload = self._request_json(
            "GET",
            f"{self.settings.library_prefix}/items/{item_key}/children",
        )
        if status == 404:
            raise ZoteroNotFoundError(f"Item {item_key!r} was not found in Zotero.")
        if status != 200:
            raise ZoteroClientError(
                f"Unexpected Zotero status {status} while fetching child items."
            )
        return payload if isinstance(payload, list) else []

    def get_fulltext(self, attachment_key: str) -> dict[str, Any]:
        """Return indexed fulltext for an attachment."""
        status, _, payload = self._request_json(
            "GET",
            f"{self.settings.library_prefix}/items/{attachment_key}/fulltext",
        )
        if status == 404:
            raise NoFulltextError(
                f"Attachment {attachment_key!r} has no indexed fulltext in Zotero."
            )
        if status != 200:
            raise ZoteroClientError(
                f"Unexpected Zotero status {status} while fetching attachment fulltext."
            )
        if not isinstance(payload, dict):
            raise ZoteroClientError("Expected JSON object for Zotero fulltext response.")
        return payload

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], Any]:
        status, response_headers, payload = self._request(method, path, params=params, headers=headers)
        if status == 304:
            return status, response_headers, None
        if payload in ("", None):
            return status, response_headers, None
        try:
            return status, response_headers, json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ZoteroClientError(f"Invalid JSON response from Zotero for {path!r}.") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], str]:
        query = f"?{urlencode(_normalize_params(params), doseq=True)}" if params else ""
        url = f"{self.settings.api_base_url}/{path.lstrip('/')}{query}"
        request_headers = {
            "Accept": "application/json",
            "Zotero-API-Version": "3",
        }
        if self.settings.api_key:
            request_headers["Zotero-API-Key"] = self.settings.api_key
        if headers:
            request_headers.update(headers)
        request = Request(url=url, method=method, headers=request_headers)
        try:
            with urlopen(request, timeout=10) as response:
                return (
                    int(response.status),
                    dict(response.headers.items()),
                    response.read().decode("utf-8"),
                )
        except HTTPError as exc:
            if exc.code == 304:
                return 304, dict(exc.headers.items()), ""
            if exc.code == 404:
                return 404, dict(exc.headers.items()), exc.read().decode("utf-8")
            raise ZoteroClientError(
                f"Zotero API request to {url!r} failed with status {exc.code}."
            ) from exc
        except URLError as exc:
            raise ZoteroUnavailableError(
                f"Unable to reach the Zotero local API at {self.settings.api_base_url}."
            ) from exc


def batched(values: list[str], size: int) -> Iterator[list[str]]:
    """Yield a list in fixed-size batches."""
    safe_size = max(1, size)
    for start in range(0, len(values), safe_size):
        yield values[start : start + safe_size]


def _normalize_params(params: dict[str, object] | None) -> dict[str, object]:
    if params is None:
        return {}
    return {
        key: value
        for key, value in params.items()
        if value not in (None, "")
    }


def _header_int(headers: dict[str, str], name: str) -> int | None:
    raw = headers.get(name)
    return None if raw in (None, "") else int(raw)
