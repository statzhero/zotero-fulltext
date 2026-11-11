---
name: within
description: Search within one Zotero item's fulltext by citekey.
---

Use the Zotero MCP server to search within a single item's indexed fulltext.

If the user did not provide both a citekey and a search query, ask for them.

Use the Zotero `fulltext_search` tool with the citekey and query.

Rules:
- Return matching paragraphs with their context.
- Do not turn this into a whole-library search.
- If the item is missing or has no indexed fulltext, say that clearly without inventing content.
- If the result has `partial_index: true`, tell the user that only `indexed_pages` of `total_pages` were searched, so a miss does not show the text is absent.
