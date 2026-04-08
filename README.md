# zotero-fulltext

Access your Zotero library with your favorite AI tool.

This MCP server for Zotero 8+ that gives Claude and Codex citekey-native access to your library. Key features are:

- Efficient fulltext retrieval
- Keyword search over Zotero's own metadata and citekeys
- Local-first: talks to Zotero's local API and uses Zotero's own index

## Quick Start

1. Make sure Zotero 8+ is running with the [local API enabled](https://www.zotero.org/support/kb/connector_zotero_unavailable) (Settings → Advanced → "Allow other applications on this computer to communicate with Zotero").
2. Run the server:

```bash
uvx zotero-fulltext
```

3. Add it to your client (see [Configuration](#configuration) below).

## Tools

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

## Resources

The server exposes MCP resource templates:

- `zotero://library` -- library summary
- `zotero://item/{citekey}` -- item metadata
- `zotero://fulltext/{citekey}` -- full text

These are templates, not a persistent registry. If you know the citekey, you can read the resource directly.

## Requirements

- Zotero 8+ with the local API enabled
- Python 3.11+
- Better BibTeX (optional but recommended)

## Installation

```bash
uvx zotero-fulltext
```

Or install persistently:

```bash
pipx install zotero-fulltext
```

## Configuration

### Codex

Add to `~/.codex/config.toml` (or project-scoped `.codex/config.toml`):

```toml
[mcp_servers.zotero_fulltext]
command = "uvx"
args = ["zotero-fulltext"]

[mcp_servers.zotero_fulltext.env]
ZOTERO_LIBRARY_TYPE = "user"
ZOTERO_LIBRARY_ID = "0"
```

Or from the CLI:

```bash
codex mcp add zotero_fulltext --env ZOTERO_LIBRARY_TYPE=user --env ZOTERO_LIBRARY_ID=0 -- uvx zotero-fulltext
```

### Claude Code

Add to `.mcp.json` in your project:

```json
{
  "mcpServers": {
    "zotero-fulltext": {
      "command": "uvx",
      "args": ["zotero-fulltext"],
      "env": {
        "ZOTERO_LIBRARY_TYPE": "user",
        "ZOTERO_LIBRARY_ID": "0"
      }
    }
  }
}
```

Or from the CLI:

```bash
claude mcp add zotero-fulltext --scope project --env ZOTERO_LIBRARY_TYPE=user --env ZOTERO_LIBRARY_ID=0 -- uvx zotero-fulltext
```

### Claude Desktop

Add the same JSON block to `claude_desktop_config.json`. The format is identical to the Claude Code example above.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ZOTERO_API_BASE_URL` | `http://127.0.0.1:23119/api` | Zotero local API endpoint |
| `ZOTERO_LIBRARY_TYPE` | `user` | `user` or `group` |
| `ZOTERO_LIBRARY_ID` | `0` | Library ID (0 for personal libraries) |
| `ZOTERO_API_KEY` | -- | Required only for non-public remote libraries |
| `ZOTERO_CACHE_DIR` | `~/.cache/zotero-fulltext` | Persistent index location |

## Design

The server is intentionally small-surface and read-only. It relies on Zotero's own search index rather than building a second one.

- Startup builds a metadata index mapping citekeys to items and attachments.
- Library changes are tracked with Zotero version headers and incremental sync.
- Fulltext is fetched only on demand and cached in memory (TTL/LRU).
- All outputs are bounded by default: 10 search hits, 80 paragraphs, 20 fulltext matches.
- If a lookup finds no citekey, it returns `found=false`. If a search finds nothing, it returns `results=[]`. There is no web fallback.

## Limits

- Local API only (v1)
- Read-only (no notes, annotations, or write-back)
- No embeddings or separate semantic index
- No built-in web fallback

## Development

```bash
python -m unittest discover -s tests
```

Benchmark harness:

```bash
PYTHONPATH=src python scripts/benchmark.py --query "forecast errors" --citekey smith2020
```

## License

MIT
