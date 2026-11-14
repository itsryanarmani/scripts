#!/usr/bin/env bash
# Generate a WaveSpeed still, then apply a lo-fi 2000s phone-photo degrade.
# Follows assetgen: never pass --sync; --dry-run makes no API call.
# The key is read only from WAVESPEED_API_KEY in the environment.
set -euo pipefail
FORMAT="" MODEL="" PROMPT="" OUTPUT="" INPUT="" ASPECT="4:5" DRY=0 LIST=0 DEGRADE=0

usage() {
  echo "usage: $0 --format <id> --prompt TEXT --output PATH [--aspect 4:5|9:16] [--model ID] [--dry-run]"
  echo "       $0 --degrade-only --input PATH --output PATH [--aspect 4:5|9:16]"
  echo "       $0 --list-models"
  echo "HTML formats (notes, imessage, blurred-pdf, us-vs-them, chat-reveal): use templates.mjs and renderer.mjs."
}

model_for() {
  case "$1" in
    lo-fi|organic|before-after|meme|whiteboard) echo "bytedance/seedream-v5.5" ;;
    stickman) echo "recraft-ai/recraft-v4.1-flash/text-to-image" ;;
    zack-d) echo "google/nano-banana-2-lite/text-to-image" ;;
    notes|imessage|blurred-pdf|us-vs-them|chat-reveal) echo "html" ;;
    *) return 1 ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prompt) PROMPT="${2:-}"; shift 2 ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    --input) INPUT="${2:-}"; shift 2 ;;
    --aspect) ASPECT="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --format) FORMAT="${2:-}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --list-models) LIST=1; shift ;;
    --degrade-only) DEGRADE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "$LIST" -eq 1 ]; then
  for id in notes imessage lo-fi blurred-pdf organic whiteboard us-vs-them before-after zack-d stickman meme chat-reveal; do
    printf '%s\t%s\n' "$id" "$(model_for "$id")"
  done
  exit 0
fi

if [ "$ASPECT" != "4:5" ] && [ "$ASPECT" != "9:16" ]; then
  echo "aspect must be 4:5 or 9:16" >&2; exit 2
fi

degrade() {
  local src="$1" dest="$2" w=1080 h=1350
  [ "$ASPECT" = "9:16" ] && h=1920
  command -v ffmpeg >/dev/null || { echo "ffmpeg is required for degrade" >&2; return 1; }
  local tmp; tmp="$(mktemp --suffix=.jpg)"
  # Mild rotation, soft blur, grain, slightly warm/flat contrast, then scale to target.
  ffmpeg -y -i "$src" -vf "rotate=2*PI/180:c=black:ow=iw:oh=ih,crop=iw*0.92:ih*0.92,scale=720:-2,gblur=sigma=0.8,noise=alls=18:allf=t+u,eq=saturation=0.85:contrast=0.93:gamma=0.97:brightness=-0.02,scale=${w}:${h}:force_original_aspect_ratio=increase,crop=${w}:${h}" -q:v 8 "$tmp" >/dev/null 2>&1
  ffmpeg -y -i "$tmp" -q:v 10 "$dest" >/dev/null 2>&1
  rm -f "$tmp"
}

if [ "$DEGRADE" -eq 1 ]; then
  [ -n "$INPUT" ] && [ -n "$OUTPUT" ] || { echo "--degrade-only needs --input and --output" >&2; exit 2; }
  [ -f "$INPUT" ] || { echo "input not found" >&2; exit 2; }
  degrade "$INPUT" "$OUTPUT"
  echo "wrote degraded still to $OUTPUT"
  exit 0
fi

if [ -n "$FORMAT" ]; then
  resolved="$(model_for "$FORMAT")" || { echo "unknown format: $FORMAT" >&2; exit 2; }
  [ -n "$MODEL" ] || MODEL="$resolved"
fi
[ -n "$MODEL" ] || { echo "either --format or --model is required" >&2; exit 2; }

if [ "$MODEL" = "html" ]; then
  echo "format $FORMAT is an HTML static; render it with templates.mjs and renderer.mjs" >&2
  exit 2
fi

[ -n "$PROMPT" ] && [ -n "$OUTPUT" ] || { usage >&2; exit 2; }

if [ "$DRY" -eq 1 ]; then
  echo "dry-run: would run wavespeed $MODEL (no API calls; no key required)"
  echo "  prompt: $PROMPT"
  echo "  aspect_ratio: $ASPECT"
  echo "  output: $OUTPUT"
  exit 0
fi

if [ -z "${WAVESPEED_API_KEY:-}" ]; then
  echo "refusing: WAVESPEED_API_KEY is not set. export it, or pass --dry-run." >&2
  exit 2
fi

# Never pass --sync: assetgen found that it aborts the submission.
if ! wavespeed run "$MODEL" -i "prompt=$PROMPT" -i "aspect_ratio=$ASPECT" -i "resolution=1.5k" --download "$OUTPUT"; then
  echo "wavespeed run failed" >&2
  exit 1
fi
[ -f "$OUTPUT" ] || { echo "wavespeed did not write $OUTPUT" >&2; exit 1; }
degrade "$OUTPUT" "$OUTPUT"
echo "wrote $OUTPUT"
