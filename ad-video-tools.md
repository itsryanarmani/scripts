# ad-video-tools

Three ffmpeg/Vision checks for a finished ad video. Each prints PASS or
FAIL with numbers, exit 0/1/2. Needs `ffmpeg`/`ffprobe`;
`ad-caption-ocr` also needs `swiftc` (macOS). Stdlib only, no keys.

| Tool | What it does |
| --- | --- |
| `ad-video-master` | Two-pass `loudnorm` master: parses pass-1 JSON, remuxes with `-c:v copy`, AAC 192k, then measures the FINAL mp4 — AAC encoding moves the true peak. PASS needs -16 to -12 LUFS and true peak <= -1.0 dBTP. `--target`, `--tp` override the -14 / -1.5 aim. |
| `ad-caption-ocr` | `VIDEO.mp4 CAPTIONS.json` (list or `{"groups"|"captions": [...]}` of `{"start","end","text"}`). One frame per caption midpoint, read by macOS Vision (`VNRecognizeTextRequest`, accurate, en-US, language correction off). Per-card CER = edit distance / expected length, upper case, punctuation/emoji/spaces collapsed; FAIL above 0.10 on any card. The Swift helper is compiled with `swiftc -O` — never `swift file.swift`, the interpreter hangs — and retried once on a Vision `e5rt` crash. |
| `ad-video-sync` | `VIDEO.mp4 [--out report.json]`. Dead gap = `freezedetect n=-60dB:d=0.3` crossed with `silencedetect -35dB:d=0.25`. FAIL on any dead gap or a tail after the last sound >= 0.3 s. Also reports scene cut times (score > 0.3), cut count and average shot length; `--out` writes JSON. |

Order: `ad-video-master` on the mix, then `ad-video-sync` and
`ad-caption-ocr` on the final mp4.

## Honest limits

These tools measure signals, not sight or sound: a person still judges
the look (framing, jank, safe zones) and the voice (fit, acting, mix).
`ad-caption-ocr` reads burned-in text only — not caption timing, words
per card, or spacing; normalization strips punctuation and emoji too,
CER exactly 0.10 passes (strict >), so one letter swap in a 20+
character caption can hide. `ad-video-sync` finds dead air and tails,
not beat placement; score > 0.3 misses soft transitions, fires on flashes.

## Failure modes

See [`ad-video-tools.failure-modes.md`](ad-video-tools.failure-modes.md).

## Test

`python3 ad-video-tools.test.py [EVIDENCE.json]` builds good and broken
clips and writes an evidence JSON. macOS only (needs `swiftc`, Pillow).
