---
description: Read numbered paragraphs from a Zotero item by citekey
argument-hint: "<citekey>"
allowed-tools: ["mcp__plugin_zotero_zotero__fulltext"]
---

Use the Zotero MCP server to read indexed fulltext for this citekey:

`$ARGUMENTS`

Rules:
- If the user did not provide a citekey, ask for one citekey.
- Use the Zotero `fulltext` tool.
- Return the numbered paragraphs from the tool result.
- Do not summarize unless the user also asked for a summary.
- If the item is missing or has no indexed fulltext, say that clearly without inventing content.
