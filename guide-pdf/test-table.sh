#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/guide.md" <<'MD'
---
title: Table test
description: GFM tables
updated: 2026-01-15
---
| A | B |
| --- | --- |
| 1 | 2 |
MD
bun "$root/render.ts" "$tmp/guide.md" --out "$tmp/guide.pdf"
file "$tmp/guide.pdf" | grep -q 'PDF document'
