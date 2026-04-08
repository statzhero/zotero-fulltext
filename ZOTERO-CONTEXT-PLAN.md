# zotero-context: Build Plan

## Name

**zotero-context**. PyPI: `zotero-context`. URI scheme: `zotero://`. Import: `zotero_context`.

Alternatives considered: `paperlens` (brand-independent but vague), `citekey-mcp` (too narrow), `zotra` (meaningless to newcomers).

---

## Pitch Options

Pick one for the README opening. Written for academics who use Zotero + LaTeX and are skeptical about AI tooling.

**A (narrative):**
> If you use Zotero and occasionally talk to an AI about your research, you've done the dance: open Zotero, find the paper, copy the text, paste it into the chat, repeat tomorrow. `zotero-context` is an MCP server that lets your AI assistant read your Zotero library directly. You search with the citekeys you already use in LaTeX.

**B (factual):**
> An MCP server that connects your Zotero library to AI assistants like Claude. Search your library, read papers, and reference them by citekey -- the same keys you use in `\cite{}`. Papers you've accessed stay available across conversations. No vector databases, no PDF re-processing, no magic. Just your library, accessible.

**C (workflow-first):**
> You already organize your papers in Zotero and cite them by key in LaTeX. `zotero-context` makes those same papers available to your AI assistant. Search your library, pull up a paper by citekey, search within it. Accessed papers persist as resources you can @mention in future conversations instead of re-fetching them every time.

**Tagline (for badge area):** Connect your Zotero library to AI assistants via MCP.

---

## Core Design Principle

Two problems, two MCP primitives:

| Problem | Solution | MCP primitive |
|---|---|---|
| "Find me the paper about X" | LLM searches autonomously | **Tools** (model-controlled) |
| "I need that same paper again" | User attaches by citekey | **Resources** (user-controlled) |

Tools handle discovery. Resources handle reuse. The bridge: every tool call that touches a paper registers it as a named resource keyed by its citekey.

---

## Tools (4)

| Tool | Parameters | Returns |
|---|---|---|
| `search` | `query`, `collection?`, `tag?`, `qmode?`, `limit?` | Items with citekeys, titles, authors, dates |
| `collections` | -- | Collections with keys, names, item counts |
| `fulltext` | `citekey`, `offset?`, `limit?` | Numbered paragraphs (default: first 80) |
| `fulltext_search` | `citekey`, `query`, `context?` | Matching paragraphs with surrounding context |

### Example: `search`

```
1. marinelli2014 -- Marinelli & Weissensteiner (2014)
   "Analysts' accuracy and herding behavior"
   Journal of Banking & Finance

2. hong_activity_2000 -- Hong, Kubik & Solomon (2000)
   "Security analysts' career concerns and herding"
   RAND Journal of Economics
```

### Example: `fulltext`

```
# Marinelli & Weissensteiner (2014)
Analysts' accuracy and herding behavior
Journal of Banking & Finance, 38, 18-29

---

[1] This paper investigates the relationship between analyst
forecast accuracy and the profitability of trading strategies...

[2] The theoretical framework builds on the observation that
forecast errors across analysts are typically correlated...

[3] When errors are correlated, an analyst whose forecast
deviates from the consensus may generate profitable trades
even when less accurate in absolute terms...

(paragraphs 1-80 of 142. Use offset=80 for more.)
```

### Example: `fulltext_search`

```
fulltext_search("marinelli2014", "correlated errors")

3 matches in Marinelli & Weissensteiner (2014):

[2] ...The theoretical framework builds on the observation that
forecast errors across analysts are typically correlated...

[3] When errors are correlated, an analyst whose forecast
deviates from the consensus may generate profitable trades
even when less accurate in absolute terms...

[47] ...our simulation results confirm that under correlated
errors, the accuracy-profitability relationship becomes
non-monotonic...
```

500 tokens instead of 10,000.

---

## Resources (dynamic, citekey-based)

Every paper accessed via `fulltext` or `fulltext_search` gets auto-registered as a resource:

| URI | Display name |
|---|---|
| `zotero://marinelli2014` | Marinelli & Weissensteiner (2014) |
| `zotero://marinelli2014/fulltext` | Marinelli & Weissensteiner (2014) -- Full Text |

One static resource always present:

| URI | Display name |
|---|---|
| `zotero://library` | Zotero Library Summary |

### How it works in practice

**First conversation:**
1. User: "Find the Marinelli paper"
2. LLM calls `search("marinelli")` -> finds `marinelli2014`
3. LLM calls `fulltext("marinelli2014")` -> reads paper
4. Server registers `zotero://marinelli2014/fulltext` as a resource
5. Server sends `list_changed` notification
6. Claude Code autocomplete now includes "Marinelli & Weissensteiner (2014)"

**Every subsequent conversation:**
1. User types `@` -> sees "Marinelli & Weissensteiner (2014) -- Full Text"
2. Selects it -> fulltext loads into context
3. No tool call needed, no re-fetching

---

## Citekey Resolution

**Source 1: Better BibTeX Extra field (preferred).** BBT writes `Citation Key: marinelli2014` into each item's Extra field. The server reads this from metadata. Most academics using Zotero + LaTeX have BBT installed.

**Source 2: Auto-generated fallback.** For items without a BBT citekey, generate `{first_author_surname}{year}` from metadata. Collisions get suffixes: `smith2020`, `smith2020a`, `smith2020b`.

### Registry file

`~/.cache/zotero-context/keys.json`:

```json
{
  "marinelli2014": {
    "item_key": "ABC123XY",
    "attachment_key": "PDF456ZZ",
    "title": "Analysts' accuracy and herding behavior",
    "authors": "Marinelli & Weissensteiner",
    "year": "2014"
  }
}
```

Built incrementally as papers are accessed. Persists across conversations and server restarts. The attachment key is cached here too, avoiding the two-step parent -> children -> PDF lookup on repeat access.

---

## Caching Architecture

| Layer | What | Storage | TTL | Solves |
|---|---|---|---|---|
| **Citekey registry** | citekey -> keys + display info | JSON on disk | Permanent | "Resolve this citekey fast" |
| **Content cache** | Fulltext blobs, metadata | In-memory dict | 2 hours | "Don't re-fetch within a session" |
| **Zotero versioning** | `Last-Modified-Version` header | Single int on disk | -- | "Has the library changed since last startup?" |

On server startup:
1. Load `keys.json` -> register all known papers as resources
2. Load stored library version -> send `If-Modified-Since-Version` to Zotero
3. If `304 Not Modified` -> cache is valid
4. If `200` -> incrementally update changed items

No external dependencies (no Redis, no SQLite, no ChromaDB).

---

## Requirements

- **Zotero 8.0+** with local API enabled (Settings > Advanced)
- **Better BibTeX** recommended for citekeys (auto-generated fallback available)
- **Python 3.11+**

---

## What We Don't Build

| Feature | Why not |
|---|---|
| Semantic search / embeddings | Requires ChromaDB, indexing step, embedding API. Zotero's `qmode=everything` does fulltext keyword search. |
| PDF re-extraction | Zotero 8 indexes PDFs. Not indexed = not attached or needs OCR in Zotero. Not our problem. |
| Annotations / highlights | Scope creep. Requires BBT RPC or PDF parsing library. |
| Note creation / write-back | Read-only is simpler to trust and maintain. |
| Better BibTeX RPC | We read the citekey from the Extra field. No RPC needed. |
| CLI setup wizard | Env vars. |
| Background sync daemon | Version check on startup. |
| Table/figure extraction | Zotero's text extraction doesn't preserve table structure. Accept the limitation. The narrative around tables ("Table 3 shows...") is usually enough for an LLM. |

---

## Project Structure

```
.github/
  workflows/ci.yml          # ruff + pytest on push
  ISSUE_TEMPLATE/
    bug_report.yml
public/
  cover.png                 # README banner
src/zotero_context/
  __init__.py               # FastMCP server, tool + resource definitions
  client.py                 # pyzotero wrapper, attachment resolution
  text.py                   # paragraph chunking, fulltext_search
  registry.py               # citekey registry (disk-persisted)
  cache.py                  # TTL content cache + version tracking
tests/
  test_text.py
  test_registry.py
  conftest.py               # fixtures with sample Zotero responses
CHANGELOG.md
LICENSE                     # MIT
README.md
pyproject.toml
smithery.yaml
```

~500 lines of logic across 5 source files.

**Dependencies:** `fastmcp`, `pyzotero`, `cachetools`.

---

## README Structure

```
[cover.png]

[Smithery] [Glama] [PyPI] [License] [Python 3.11+]

# zotero-context

[Chosen pitch from options above]

## Without zotero-context
- Open Zotero, find the paper, copy text, paste into chat
- Repeat for every new conversation
- Entire PDFs dumped into context when you only need one paragraph

## With zotero-context
- Ask your AI to search your library by topic, author, or collection
- Read papers by citekey -- the same keys you use in \cite{}
- Search within a paper and get matching paragraphs, not the whole PDF
- Papers you've accessed are @mentionable in future conversations

[30-second demo video]

<nav TOC>

## Installation
uvx zotero-context
[Config for Claude Code / Cursor / Claude Desktop]

## How It Works
[One paragraph: tools for discovery, resources for reuse]

## Tools
### Find papers -> search
### Browse collections -> collections
### Read a paper -> fulltext
### Search within a paper -> fulltext_search

## Resources
[@citekey pattern, dynamic registration, persistence]

## Configuration
[ZOTERO_LOCAL=true default for Zotero 8]

## Requirements
- Zotero 8.0+ with local API enabled
- Better BibTeX recommended (fallback available)

## FAQ
- "Do I need Better BibTeX?" -> Recommended, not required
- "What about scanned PDFs?" -> Needs OCR in Zotero first
- "Group libraries?" -> Yes, set ZOTERO_LIBRARY_TYPE=group
- "Does it work with ChatGPT/Cursor/...?" -> Any MCP-compatible client

## Contributing
## License (MIT)
```

---

## Build Order

| Step | What | Effort | Depends on |
|---|---|---|---|
| 1 | `text.py` + `test_text.py` | Small | Nothing |
| 2 | `registry.py` + `test_registry.py` | Small | Nothing |
| 3 | `client.py` | Medium | pyzotero |
| 4 | `cache.py` | Small | cachetools |
| 5 | `__init__.py` -- tools | Medium | Steps 1-4 |
| 6 | `__init__.py` -- resources | Medium | Step 5 |
| 7 | `pyproject.toml` + local testing | Small | Step 6 |
| 8 | Record demo video | -- | Step 7 |
| 9 | Cover image | -- | Anytime |
| 10 | README | Medium | Steps 8-9 |
| 11 | Publish PyPI + Smithery + Glama | Small | Step 10 |

Steps 1+2 can run in parallel. Steps 8+9 can run in parallel.

---

## GitHub Presentation Checklist

Based on analysis of top MCP repos (Context7, GhidraMCP, Figma-Context-MCP, FastMCP):

- [ ] Custom cover image in `public/` (Zotero logo + citekey + AI prompt concept)
- [ ] Badge row: Smithery, Glama, PyPI, License, Python version
- [ ] Without/With contrast block
- [ ] Demo video (MP4 uploaded to GitHub, renders inline) within first 10 lines
- [ ] Centered nav TOC
- [ ] Tool descriptions written as use cases, not function signatures
- [ ] Config snippets for Claude Code, Cursor, Claude Desktop
- [ ] `smithery.yaml` in repo root
- [ ] `CHANGELOG.md`
- [ ] Issue templates in `.github/`
- [ ] `CONTRIBUTING.md` (even minimal)

---

## Competitive Landscape

| | kujenga/zotero-mcp (v0.1.6) | 54yyyu/zotero-mcp (v0.6+) | zotero-context |
|---|---|---|---|
| Tools | 3 (search, metadata, fulltext) | 15+ | 4 |
| Resources | None | None | Dynamic, citekey-based |
| Fulltext | Dumps entire blob | Dumps entire blob | Chunked paragraphs + search within |
| Citekey support | No | No | Yes (BBT Extra field + fallback) |
| Cross-conversation reuse | None | None | Persistent resource registry |
| Dependencies | pyzotero | pyzotero, chromadb, pdfannots, BBT RPC | pyzotero, cachetools |
| Lines of code | ~200 | ~2000+ | ~500 |
