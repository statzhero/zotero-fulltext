---
description: Search within one Zotero item's fulltext by citekey
argument-hint: "<citekey> <query>"
allowed-tools: ["mcp__plugin_zotero_zotero__fulltext_search"]
---

Use the Zotero MCP server to search within a single item's indexed fulltext.

Raw arguments:
`$ARGUMENTS`

Rules:
- Interpret the first token as the citekey and the remaining text as the query.
- If either part is missing, ask the user for `citekey` plus the in-paper query.
- Use the Zotero `fulltext_search` tool.
- Return matching paragraphs with their context.
- Do not turn this into a whole-library search.
- If the item is missing or has no indexed fulltext, say that clearly without inventing content.
