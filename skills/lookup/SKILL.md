---
name: lookup
description: Look up one Zotero item by citekey.
---

Use the Zotero MCP server to look up an item by its exact citekey.

If the user did not provide a citekey, ask for one.

Use the Zotero `lookup` tool with the citekey.

Rules:
- Treat this as exact citekey lookup, not broad search.
- Do not invent metadata.
- If Zotero has no entry for the citekey, say so clearly and list any `candidates` it returned (near keys with the same surname, year within one).
- Report a paper as absent only after `lookup` on the likely citekey and a search by author surnames (and year) both miss, and say which checks you ran.
- When an item is found, return a short metadata summary and include whether fulltext is available.
