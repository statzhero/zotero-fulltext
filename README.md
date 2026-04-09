# zotero-fulltext

Access your [Zotero](https://www.zotero.org/) library with your favorite AI tool. Fast and token-efficient.

This MCP server for Zotero 8+ gives Claude and Codex citekey-native access to your library. It talks directly to Zotero's local API and returns bounded outputs to keep token usage low. Fulltext is fetched only on demand.

## Quick Start

1. Make sure Zotero 8+ is running with the [local API enabled](https://www.zotero.org/support/kb/connector_zotero_unavailable) (Settings → Advanced → "Allow other applications on this computer to communicate with Zotero").
2. Run the server:

```bash
uvx zotero-fulltext
```

3. Add it to your client (see [Configuration](#configuration) below).

## Commands

If you use the optional Claude Code plugin from this repo, you get four slash commands:

| Command | What it does |
|---|---|
| `/zotero:find <query>` | Search the whole library |
| `/zotero:lookup <citekey>` | Exact citekey metadata lookup |
| `/zotero:read <citekey>` | Numbered fulltext paragraphs |
| `/zotero:within <citekey> <query>` | Search inside one paper's fulltext |

`lookup` is lightweight metadata confirmation. `read` returns the actual paper text. `find` searches the whole library. `within` searches only one item's indexed fulltext.

Without the plugin, all the same functionality is available through the MCP tools directly (see [Tools](#tools)).

## Installation

`uvx` runs the package in a temporary environment with no permanent install. This is the recommended approach:

```bash
uvx zotero-fulltext
```

For a persistent install (the command stays available across sessions):

```bash
uv tool install zotero-fulltext
# or
pipx install zotero-fulltext
```

If you want the optional Claude Code slash commands, clone this repo and point Claude Code at it (see [Configuration](#configuration)).

## Configuration

### Claude Code

**Option A** (standard MCP setup):

```bash
claude mcp add --transport stdio --scope project zotero -- uvx zotero-fulltext
```

Or add to `.mcp.json` in your project:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
      "command": "uvx",
      "args": ["zotero-fulltext"]
    }
  }
}
```

**Option B** (local plugin with slash commands):

```bash
claude --plugin-dir /absolute/path/to/zotero-fulltext
```

Then restart Claude Code if needed, run `/mcp` to confirm the server is connected, and test with `Look up citekey smith2020 in Zotero.` or use the slash commands.

### Claude Desktop

Add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
      "command": "uvx",
      "args": ["zotero-fulltext"]
    }
  }
}
```

Restart Claude Desktop, open a chat, and confirm the server is available.

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.zotero]
command = "uvx"
args = ["zotero-fulltext"]
```

Restart Codex, then run `codex mcp list` to verify it is configured.

## Tools

The server exposes five MCP tools. Clients call these directly; the slash commands above are convenience wrappers.

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

## Design

The server is intentionally small-surface and read-only. It relies on Zotero's own search index rather than building a second one.

- Startup builds a metadata index mapping citekeys to items and attachments.
- Library changes are tracked with Zotero version headers and incremental sync.
- Fulltext is fetched only on demand and cached in memory (TTL/LRU).
- All outputs are bounded by default: 10 search hits, 80 paragraphs, 20 fulltext matches.
- Item results include `item_uri` and `fulltext_uri` so clients can attach standard `zotero://...` resources directly.
- If a lookup finds no citekey, it returns `found=false`. If a search finds nothing, it returns `results=[]`. There is no web fallback.

## Roadmap

- Remote API support (beyond local)
- Write-back (notes, annotations)
- Embeddings or semantic search
- Web fallback for items not in the local library

## Requirements

- Zotero 8+ with the local API enabled
- Python 3.11+
- Better BibTeX (optional but recommended)

## License

MIT
