#!/usr/bin/env bash

set -euo pipefail

plugin_root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
local_entrypoint="${plugin_root}/.venv/bin/zotero-fulltext"

if [ -x "${local_entrypoint}" ]; then
  exec "${local_entrypoint}"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "${plugin_root}" zotero-fulltext
fi

if command -v uvx >/dev/null 2>&1; then
  exec uvx zotero-fulltext
fi

cat >&2 <<'EOF'
zotero-fulltext could not start.

Expected one of:
- a repo-local entrypoint at .venv/bin/zotero-fulltext
- the `uv` command
- the `uvx` command
EOF

exit 1
