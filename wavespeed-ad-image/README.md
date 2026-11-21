# wavespeed-ad-image

Generate Meta ad stills: WaveSpeed plus a lo-fi phone-photo degrade, or HTML
statics for Notes, iMessage, and blurred-PDF.

The WaveSpeed key is read only from the `WAVESPEED_API_KEY` environment
variable. Never pass `wavespeed run --sync` (see `assetgen/README.md`).

```bash
# Model table
./wavespeed-ad-image.sh --list-models

# Plan a still (no key, no API call)
./wavespeed-ad-image.sh --dry-run --format lo-fi \
  --prompt "a candid kitchen still, 2000s phone photo" \
  --output ./ad.png --aspect 4:5

# Generate, then degrade (key required)
./wavespeed-ad-image.sh --format lo-fi \
  --prompt "a candid kitchen still, 2000s phone photo" \
  --output ./ad.png --aspect 4:5

# Degrade an existing file (no key)
./wavespeed-ad-image.sh --degrade-only --input ./raw.png --output ./ad.png

# HTML statics
node templates.mjs notes --aspect 4:5 > notes.html
node renderer.mjs --file notes.html --out notes.png --aspect 4:5 --dry-run
```

`--format` ids: `lo-fi`, `organic`, `whiteboard`, `before-after`, `zack-d`,
`stickman`, `meme` go through WaveSpeed; `notes`, `imessage`, `blurred-pdf`,
`us-vs-them`, and `chat-reveal` use the HTML templates. `--model` overrides
the default. `--aspect` is `4:5` or `9:16`.

Templates use placeholder names only (Alex, a friend). No logos, no invented
testimonials. Run `./test.sh` before a change; tests use no network and no key.
