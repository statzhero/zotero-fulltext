# zotero-fulltext

Access your Zotero library with your favorite AI tool.

This MCP server for Zotero 8+ that gives Claude and Codex citekey-native access to your library. Key features are:

- Efficient fulltext retrieval
- Keyword search over Zotero's own metadata and citekeys
- Local-first: talks to Zotero's local API and uses Zotero's own index
- No invented local matches when Zotero has no entry

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

If you want the optional Claude Code slash commands in this repo, `uv` is recommended so the plugin can start the server from the checkout.

## Configuration

### Client Setup

Use `uvx zotero-fulltext` if you installed from PyPI, or use a repo-local executable such as `/path/to/zotero-mcp/.venv/bin/zotero-fulltext` if you are running from a checkout.

For the best resource UX, configure the MCP server with the short name `zotero` even though the package name is `zotero-fulltext`. That keeps resource mentions short, for example `@zotero:zotero://item/smith2020`.

### Claude Code Terminal

You have two good options.

Option A: standard MCP setup.

```bash
claude mcp add --transport stdio --scope project zotero -- uvx zotero-fulltext
```

Or add it to `.mcp.json` in your project:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
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

Option B: local plugin from this repo, which adds four slash commands and starts the same MCP server for you.

```bash
claude --plugin-dir /absolute/path/to/zotero-mcp
```

The plugin adds exactly these commands:

- `/zotero:find <query>`
- `/zotero:lookup <citekey>`
- `/zotero:read <citekey>`
- `/zotero:within <citekey> <query>`

Then:

1. Restart Claude Code if needed.
2. Run `/mcp` to confirm the server is connected.
3. Test with prompts like `Look up citekey smith2020 in Zotero.` or use the plugin commands above.

### Claude App

For Claude Desktop, add the server to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zotero": {
      "type": "stdio",
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

Then:

1. Restart Claude Desktop.
2. Open a chat and confirm the connector/server is available.
3. Test with the same lookup, search, and fulltext prompts.

Note: a Claude Desktop extension package (`.mcpb`) could be added later, but v1 uses the standard local MCP config path.

### Codex Terminal

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.zotero]
command = "uvx"
args = ["zotero-fulltext"]

[mcp_servers.zotero.env]
ZOTERO_LIBRARY_TYPE = "user"
ZOTERO_LIBRARY_ID = "0"
```

Then:

1. Restart Codex terminal.
2. Run `codex mcp list` to verify it is configured.
3. Test with prompts like `Show the first 3 paragraphs of smith2020.` or `Search within smith2020 for correlated errors.`

### Codex App

The Codex app uses the same MCP configuration as Codex terminal, so the same `~/.codex/config.toml` entry applies.

Then:

1. Restart the Codex app.
2. Start a new chat in the app.
3. Test the same Zotero prompts you use in Codex terminal.

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
- Item results include `item_uri` and `fulltext_uri` so clients can attach standard `zotero://...` resources directly.
- If a lookup finds no citekey, it returns `found=false`. If a search finds nothing, it returns `results=[]`. There is no web fallback.

## Claude UX

If you use the optional Claude Code plugin in this repo, the intended command set is exactly four commands:

- `/zotero:find <query>` for whole-library search
- `/zotero:lookup <citekey>` for exact citekey metadata lookup
- `/zotero:read <citekey>` for numbered fulltext paragraphs
- `/zotero:within <citekey> <query>` for search inside one paper

`lookup` is lightweight metadata confirmation. `read` is the actual paper text. `find` searches the whole library. `within` searches only one item's indexed fulltext.

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
