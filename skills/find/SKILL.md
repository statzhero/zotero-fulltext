---
name: find
description: Search your Zotero library by keyword.
---

Use the Zotero MCP server to search the local Zotero library.

If the user did not provide a query, ask for one concise search phrase.

Use the Zotero `search` tool with the query.

Rules:
- Do not invent papers or metadata.
- If there are no local matches, say that Zotero returned no results.
- Report a paper as absent only after `lookup` on the likely citekey and a search by author surnames (and year) both miss, and say which checks you ran.
- Keep the response compact and list the citekey first for each result.
