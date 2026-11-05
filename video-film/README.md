# video-film

Tools to make a beat-cut film from generated footage. Built and verified on one 25.7 s film (2026-11-05).
The skill that explains when and why: `ship-demo-video` (style `anime-heavy-cut`) and `launch-video-generation`.

| Tool | What it does | Needs |
| --- | --- | --- |
| `ws_image.py shots.json outdir` | Stills from a shot list. The `hero` shot goes first. The rest use it as the reference. | `WAVESPEED_API_KEY` or `WAVESPEED_ENV_FILE` |
| `veo.py clips.json stilldir outdir [--only a,b]` | Image to video with Veo 3.1 on Vertex. 4 clips run in parallel. Logs an estimate to `spend.jsonl`. | `VERTEX_PROJECT`, a logged-in `gcloud` (`CLOUDSDK_CONFIG` optional) |
| `lyria.py out.wav "<prompt>" "<negative>"` | An instrumental bed of about 32 s with Lyria 2. | same as `veo.py` |
| `film_build.py spec.json [out.html]` | Writes a HyperFrames `index.html` that cuts on a beat grid. Every time in the spec is in beats. | `npx hyperframes` for `check`, `snapshot`, `render` |

`clips.json`: `{"model": "veo-3.1-fast-generate-001", "secs": 4, "usd_per_s": 0.15, "style": "...", "negative": "...",
"clips": [{"id": "button", "still": "button", "motion": "Camera: ... Motion: ..."}]}`.
`shots.json`: `{"anchor": "<style text>", "size": "1920*1080", "shots": [{"id": "hero", "prompt": "...", "ref": false}, ...]}`.
`example-spec.json` shows the full `film_build.py` spec: 17 shots, 8 texts, 19 sound effects, a proof panel and an end card.

## Run order
1. `ws_image.py` for the hero, look at it, then the rest. Build a contact sheet. Fix stray text.
2. `veo.py` on the hero shots only. One camera move and one action per clip.
3. `lyria.py` for the bed. `npx hyperframes beats bed.mp3 --json` for the beat grid.
4. Put assets in `assets/`, write the spec, run `film_build.py spec.json index.html`.
5. `npx hyperframes check`, then `snapshot --at ...`, then `render --quality high`, then `loudnorm` to about -16 LUFS.

Keys come from the environment. The tools never print a key. Veo and Lyria bill the cloud project you name.
