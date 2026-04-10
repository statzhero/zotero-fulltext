# Changelog

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
