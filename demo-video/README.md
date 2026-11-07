# demo-video

Builds and checks short HyperFrames demo videos from a JSON spec, in a named style. It is the tooling half of the
`ship-demo-video` skill in itsryanarmani/skills. The skill owns the process (capture, storyboard, gates); this folder
owns the code.

## Commands

```sh
demo-video build <spec.json> <project-dir>   # index.html + compositions/ for the spec's style
demo-video audit <video> <grid.png>          # one frame every 1.5 s, tiled 6 wide
demo-video energy <audio>                    # loudness per second (EBU R128 momentary, LUFS)
demo-video beats <project-dir>               # first beat, period and strongest beats from beats/*.json
demo-video avatar --look ID --voice ID --script TEXT --out FILE [--speed 1.08] [--aspect 1:1]
```

Exit status: 0 on success, 1 when the spec or a check fails, 2 on bad usage. Results print as one JSON object on
standard output; diagnostics go to standard error.

## Requirements

- `ffmpeg` and `ffprobe` on the PATH, and Python 3 with Pillow (for `audit`).
- HyperFrames for the project itself: `npx hyperframes init <dir> --example blank --resolution landscape`, then
  `npx hyperframes beats`, `check`, `snapshot` and `render`.
- `avatar` reads `HEYGEN_API_KEY` from the environment. It never prints the key.

## Spec fields every style reads

| Field | Meaning |
| --- | --- |
| `style` | The builder in `styles/` (`keynote-whip` loads `styles/keynote_whip.py`) |
| `duration` | Render length in seconds |
| `beat.first`, `beat.period` | The beat grid from `demo-video beats`. Scenes start on beats. |
| `footage.<name>.src`, `footage.<name>.safe_end` | A footage file and its last frame that still shows the product |
| `music` | The bed and its fades and ducks; see each style's example spec |

## Guards

- **Footage safe end.** A test-harness recording keeps running after the browser closes and shows the desktop. Every
  clip reads `media + dur × rate`; the build fails when that passes the footage's `safe_end`.
- **SFX slots.** Each SFX gets its own track and a slot exactly as long as its file, so overlapping hits stay audible.

## Test

```sh
./demo-video/demo-video.test.sh
```
