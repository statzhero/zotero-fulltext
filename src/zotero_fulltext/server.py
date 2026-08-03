"""MCP server wrapper for zotero-fulltext."""

from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .errors import ZoteroFulltextError
from .service import ZoteroFulltextService


def create_server(
    settings: Settings | None = None,
    *,
    service: ZoteroFulltextService | None = None,
):
    """Create the MCP server instance.

    ``service`` can be injected for testing; otherwise one is built from
    ``settings`` (or the environment).
    """
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise RuntimeError(
            "The 'mcp' SDK is not installed. Install zotero-fulltext with its "
            "runtime dependencies first."
        ) from exc

    if service is None:
        runtime_settings = settings or Settings.from_env()
        service = ZoteroFulltextService(runtime_settings)
    else:
        runtime_settings = settings or service.settings
    service.try_startup_sync()

    # Resource annotations in the MCP SDK carry audience/priority, not the
    # read-only hints tools use, so hints are attached to tools only.
    tool_annotations = ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )

    mcp = FastMCP("zotero")

    def safe_call(callback, *args, **kwargs) -> dict[str, Any]:
        try:
            return callback(*args, **kwargs)
        except ZoteroFulltextError as exc:
            return {
                "source": "zotero-local",
                "available": False,
                "error": exc.code,
                "detail": str(exc),
            }

    def safe_resource(callback, *args, **kwargs) -> str:
        return json.dumps(safe_call(callback, *args, **kwargs), indent=2, sort_keys=True)

    @mcp.tool(
        name="lookup",
        annotations=tool_annotations,
        description=(
            "Look up a Zotero item by its exact citekey (a single token with no spaces, "
            "e.g. 'atz2022' not 'atz 2022'). Use this first when you know the citekey."
        ),
    )
    def lookup(citekey: str) -> dict[str, Any]:
        return safe_call(service.lookup, citekey)

    @mcp.tool(
        name="search",
        annotations=tool_annotations,
        description=(
            "Search Zotero metadata and indexed fulltext by keywords. "
            "For a known citekey (e.g. 'atz2022'), use `lookup` instead."
        ),
    )
    def search(
        query: str,
        collection: str | None = None,
        tag: str | None = None,
        limit: int = runtime_settings.default_search_limit,
    ) -> dict[str, Any]:
        return safe_call(
            service.search,
            query,
            collection=collection,
            tag=tag,
            limit=limit,
        )

    @mcp.tool(
        name="collections",
        annotations=tool_annotations,
        description="List Zotero collections in the current library.",
    )
    def collections() -> dict[str, Any]:
        return safe_call(service.collections)

    @mcp.tool(
        name="fulltext",
        annotations=tool_annotations,
        description="Return numbered paragraphs for a Zotero item's indexed fulltext. The citekey is a single token with no spaces (e.g. 'atz2022').",
    )
    def fulltext(
        citekey: str,
        offset: int = 0,
        limit: int = runtime_settings.default_fulltext_limit,
    ) -> dict[str, Any]:
        return safe_call(service.fulltext, citekey, offset=offset, limit=limit)

    @mcp.tool(
        name="fulltext_search",
        annotations=tool_annotations,
        description="Search within a Zotero item's indexed fulltext and return local paragraph context. The citekey is a single token with no spaces (e.g. 'atz2022').",
    )
    def fulltext_search(
        citekey: str,
        query: str,
        before: int = runtime_settings.default_fulltext_context,
        after: int = runtime_settings.default_fulltext_context,
        limit: int = 20,
    ) -> dict[str, Any]:
        return safe_call(
            service.fulltext_search,
            citekey,
            query,
            before=before,
            after=after,
            limit=limit,
        )

    @mcp.resource(
        "zotero://library",
        name="Zotero Library Summary",
        mime_type="application/json",
    )
    def library_resource() -> str:
        return safe_resource(service.library_summary)

    @mcp.resource(
        "zotero://item/{citekey}",
        name="Zotero Item",
        mime_type="application/json",
    )
    def item_resource(citekey: str) -> str:
        return safe_resource(service.lookup, citekey)

    @mcp.resource(
        "zotero://fulltext/{citekey}",
        name="Zotero Fulltext",
        mime_type="application/json",
    )
    def fulltext_resource(citekey: str) -> str:
        return safe_resource(
            service.fulltext,
            citekey,
            offset=0,
            limit=runtime_settings.default_fulltext_limit,
        )

    return mcp


def main() -> None:
    """Run the server over stdio."""
    server = create_server()
    server.run()
