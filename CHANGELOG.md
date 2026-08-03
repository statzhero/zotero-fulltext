# Changelog

## 0.4.0

- Switch the runtime from the `fastmcp` wrapper to the official `mcp` SDK, dropping around 15 unused transitive dependencies. Installing and running the server is unchanged (`uvx zotero-fulltext`, stdio).
- Freshness: detect re-indexed attachment fulltext via Zotero's `/fulltext?since=` endpoint and evict stale cached paragraphs. The cache resets when the Zotero database (`Zotero-Server-ID`) changes.
- Robustness: write the metadata index atomically (temp file plus rename) and recover from a corrupt index instead of failing startup. The stored library version can no longer move backwards, which previously could permanently skip deletions. The full index is no longer rewritten on every fulltext read.
- Docs: document all supported environment variables in the README.
- Remove the orphaned `.codex-mcp.json` (the Codex plugin already uses `.mcp.json`).

## 0.3.4

- Fix: when an item has several attachments (for example the article plus a supplemental appendix), `fulltext` now returns the attachment with the most indexed text instead of whichever attachment key sorts first. This stops a short appendix from being served in place of the full paper.

## 0.3.3

- Clarify tool descriptions so LLMs treat citekeys as exact single-token matches (e.g. `atz2022` not `atz 2022`)
- Steer LLMs toward `lookup` over `search` when they already have a citekey

## 0.3.2

- Preserve creator roles (author, editor, translator, etc.) instead of flattening all creators into a single `authors` array
- Lookup and search results now return `creators` grouped by role
- Backward-compatible: existing cached indexes with flat creator lists are migrated on load

## 0.3.1

- Bound large fulltext responses by both paragraph count and character budget
- Add `truncated`, `next_offset`, `returned_chars`, and `max_chars` metadata to `fulltext` responses
- Add `ZOTERO_MAX_PARAGRAPH_CHARS` and `ZOTERO_MAX_FULLTEXT_CHARS` configuration
- Improve incremental delete sync error handling
- Speed up citekey deduplication and warm attachment reads

## 0.3.0

- Codex plugin with skills (`find`, `lookup`, `read`, `within`) and dedicated MCP config
- Added `.codex-plugin/` manifest, `.codex-mcp.json`, and `skills/` directory

## 0.2.1

- Fix: gracefully handle missing `/deleted` endpoint on local Zotero API

## 0.2.0

- Published to PyPI (`uv tool install zotero-fulltext`)
- Claude Code plugin with marketplace install (`claude plugin marketplace add statzhero/zotero-fulltext`)
- Added environment variable documentation for group and remote libraries

## 0.1.0

- initial `zotero-fulltext` package skeleton
- local Zotero API client with version-aware metadata sync
- citekey-native lookup with native Zotero 8 keys, legacy Better BibTeX parsing, and generated fallback keys
- bounded paragraph-level fulltext retrieval and search
- FastMCP server for Codex and Claude
