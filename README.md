# zotero-fulltext

Access your [Zotero](https://www.zotero.org/) library with your favorite AI tool.

This MCP server for Zotero 8+ gives Claude and Codex citekey-native access to your library. It talks directly to Zotero's local API and aims to keep token usage low. Fulltext is fetched only on demand.

## Quick Start

1. Make sure Zotero 8+ is running with the [local API enabled](https://www.zotero.org/support/kb/connector_zotero_unavailable) (Settings → Advanced → "Allow other applications on this computer to communicate with Zotero").
2. Install the Claude Code plugin:

```bash
claude plugin marketplace add statzhero/zotero-fulltext
claude plugin install zotero
```

3. Run `/mcp` to confirm the server is connected, and try a slash command:

```
/zotero:find attention
```

Also works with [Claude Desktop](#claude-desktop), [Codex](#codex), and as a [standalone MCP server](#configuration) without slash commands.

## Commands

The Claude Code plugin provides four slash commands:

| Command | What it does |
|---|---|
| `/zotero:find <query>` | Search the whole library |
| `/zotero:lookup <citekey>` | Exact citekey metadata lookup |
| `/zotero:read <citekey>` | Numbered fulltext paragraphs |
| `/zotero:within <citekey> <query>` | Search inside one paper's fulltext |

`find` searches the whole library. `lookup` is lightweight metadata confirmation. `read` returns the actual paper text. `within` searches only one item's indexed fulltext.

Without the plugin, all the same functionality is available through the MCP tools directly (see [Tools](#tools)).

## Installation

```bash
uv tool install zotero-fulltext
# or
pipx install zotero-fulltext
```

This makes the `zotero-fulltext` command permanently available. You can also use `uvx zotero-fulltext` to run without installing.

## Configuration

### Claude Code (plugin with slash commands)

```bash
claude plugin marketplace add statzhero/zotero-fulltext
claude plugin install zotero
```

This permanently installs the MCP server and slash commands. Run `/mcp` to confirm the server is connected.

If you only want the MCP tools without slash commands:

```bash
claude mcp add --transport stdio --scope user zotero -- zotero-fulltext
```

### Claude Desktop

Add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
      "command": "zotero-fulltext"
    }
  }
}
```

Restart Claude Desktop, open a chat, and confirm the server is available.

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.zotero]
command = "zotero-fulltext"
```

Restart Codex, then run `codex mcp list` to verify it is configured.

## Design

The server is intentionally simple and read-only. It relies on Zotero's own search index rather than building a second one.

- Startup builds a metadata index mapping citekeys to items and attachments.
- Library changes are tracked with Zotero version headers and incremental sync.
- Fulltext is fetched only on demand and cached in memory (TTL/LRU).
- All outputs are bounded by default: 10 search hits, 80 paragraphs, 20 fulltext matches.
- Item results include `item_uri` and `fulltext_uri` so clients can attach standard `zotero://...` resources directly.
- If a lookup finds no citekey, it returns `found=false`. If a search finds nothing, it returns `results=[]`. There is no web fallback.

## Tools

The server exposes five MCP tools. The slash commands above are convenience wrappers.

### `lookup(citekey)`

Exact citekey lookup. Citekeys are resolved in order:

1. Native Zotero 8 `citationKey`
2. Legacy Better BibTeX `Citation Key:` line in `Extra`
3. Deterministic generated fallback

If an item later gains a real citekey, the generated key is kept as an alias.

### `search(query, collection?, tag?, limit?)`

Searches Zotero with `qmode=everything`, collapses attachment hits to parent items, and ranks exact citekey matches first.

### `collections()`

Lists collections in the current library.

### `fulltext(citekey, offset?, limit?)`

Fetches indexed attachment fulltext, splits it into numbered paragraphs, and returns a bounded slice (default: 80 paragraphs).

### `fulltext_search(citekey, query, before?, after?, limit?)`

Searches within a single item's paragraphized fulltext and returns matching paragraphs with surrounding context.



## Roadmap

- Remote API support (beyond local)
- Write-back (notes, annotations)
- Embeddings or semantic search
- Web fallback for items not in the local library

## Environment Variables

By default the server connects to a local personal library with no authentication. Set these variables to change that:

| Variable | Default | Description |
|---|---|---|
| `ZOTERO_LIBRARY_TYPE` | `user` | `user` for personal libraries, `group` for group libraries |
| `ZOTERO_LIBRARY_ID` | `0` | Zotero user or group ID (required for group libraries) |
| `ZOTERO_API_KEY` | — | API key for authenticated or remote access |
| `ZOTERO_API_BASE_URL` | `http://127.0.0.1:23119/api` | Base URL for the Zotero API |

Example for a group library in Claude Code:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
      "command": "zotero-fulltext",
      "env": {
        "ZOTERO_LIBRARY_TYPE": "group",
        "ZOTERO_LIBRARY_ID": "12345"
      }
    }
  }
}
```

## Related Projects

Other MCP servers for Zotero, with different design goals:

- [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp) — Feature-rich: read-write operations, optional semantic search via ChromaDB, Web API support. Heavier dependencies.
- [kujenga/zotero-mcp](https://github.com/kujenga/zotero-mcp) — Minimal read-only server with Web API support via pyzotero. No citekey resolution or in-document search.
- [kaliaboi/mcp-zotero](https://github.com/kaliaboi/mcp-zotero) — Cloud-only (Zotero Web API). Metadata browsing, no fulltext.

To remove an existing Zotero MCP server before switching:

```bash
claude mcp remove zotero
```

Or delete the `zotero` entry from `.mcp.json` / `claude_desktop_config.json` / `~/.codex/config.toml` manually.

## Requirements

- Zotero 8+ with the local API enabled
- Python 3.11+
- Better BibTeX (optional but recommended)

## License

MIT
