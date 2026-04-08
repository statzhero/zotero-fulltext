---
description: Look up one Zotero item by citekey
argument-hint: "<citekey>"
allowed-tools: ["mcp__plugin_zotero_zotero__lookup"]
---

Use the Zotero MCP server to look up this citekey exactly:

`$ARGUMENTS`

Rules:
- If the user did not provide a citekey, ask for one citekey.
- Use the Zotero `lookup` tool.
- Treat this as exact citekey lookup, not broad search.
- Do not invent metadata.
- If Zotero has no entry for the citekey, say so clearly.
- When an item is found, return a short metadata summary and include whether fulltext is available.
