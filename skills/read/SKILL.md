---
name: read
description: Read numbered paragraphs from a Zotero item by citekey.
---

Use the Zotero MCP server to read indexed fulltext for an item.

If the user did not provide a citekey, ask for one.

Use the Zotero `fulltext` tool with the citekey.

Rules:
- Return the numbered paragraphs from the tool result.
- Do not summarize unless the user also asked for a summary.
- If the item is missing or has no indexed fulltext, say that clearly without inventing content.
- If the result has `partial_index: true`, tell the user that Zotero indexed only `indexed_pages` of `total_pages` and that the remaining pages were not read.
