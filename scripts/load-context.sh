#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_FILE="$ROOT_DIR/.codex-context.md"

if [[ ! -f "$CONTEXT_FILE" ]]; then
  echo "Context file not found: $CONTEXT_FILE" >&2
  exit 1
fi

if command -v less >/dev/null 2>&1 && [[ -t 1 ]]; then
  less "$CONTEXT_FILE"
else
  cat "$CONTEXT_FILE"
fi
