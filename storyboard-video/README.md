# storyboard-video

Turns one `board.json` into a cast sheet, consistent storyboard stills, a review board, Veo
image-to-video clips, and an edited film with camera moves, transitions and a ducked voice-over.
It is the generated-film counterpart of [`demo-video`](../demo-video), which edits real product
footage. The process and the reasons behind each step live in the `launch-video-generation`
skill in pooriaarab/skills.

## Commands

```sh
storyboard-video check  <dir>                       # validate <dir>/board.json
storyboard-video stills <dir> [ids...]              # img/cast.png, then img/shot-NN.png anchored on it
storyboard-video board  <dir> <out.html>            # review board; shows clips once vid/ has them
storyboard-video veo    <dir> --confirm-spend [ids] # vid/shot-NN.mp4, 8 s, 720p, with sound
storyboard-video cut    <dir>                       # out/film.mp4 and out/timeline.json
```

Run them in order and stop after `board`. Show the stills to whoever approves the look, and only
then run `veo`. Veo bills each job when it is submitted, so stopping the command later saves
nothing. Without `--confirm-spend`, `veo` prints a cost estimate and exits.

## Setup

- `ffmpeg`, `ffprobe`, `gcloud` and Python 3 (standard library only).
- A Google Cloud project with the Vertex AI API on (`gcloud services enable aiplatform.googleapis.com`).
- `export VERTEX_PROJECT=<project-id>`. The token comes from `gcloud auth print-access-token`, so
  set `CLOUDSDK_CONFIG` to choose a gcloud profile without switching the active one.
- Optional model overrides: `SV_IMAGE_MODEL` (default `gemini-3-pro-image`), `SV_VIDEO_MODEL`
  (default `veo-3.1-fast-generate-001`; use `veo-3.1-generate-001` for the final pass),
  `SV_VIDEO_LOCATION` (default `us-central1`) and `SV_TTS_MODEL` (default
  `gemini-3.1-flash-tts-preview`). Model IDs change, so list what your project can call:

  ```sh
  curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "x-goog-user-project: $VERTEX_PROJECT" \
    "https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models?pageSize=300" | grep -oE '"name": "[^"]*(image|veo|tts)[^"]*"'
  ```

## board.json

See [`examples/board.json`](examples/board.json). Top level: `title`, `theme` (the visual block
every prompt repeats), `cast` (every character, described the same way every time), optional
`edit.voice` and `edit.scene_volume`. Each shot:

| Field | Meaning |
| --- | --- |
| `id`, `title`, `stage`, `action` | What happens, and where it sits in the arc (HOOK, PROBLEM, SOLUTION, PAYOFF, CTA) |
| `image` | The still prompt: framing, who is in frame, props, readable text |
| `motion` | The Veo prompt: what moves; quote any line a character says |
| `vo` | The narrator line for this shot. Keep it shorter than the shot. |
| `cut` | `[start, duration]` in seconds: the best window of the 8 s clip |
| `camera` | Zoom as an ffmpeg expression in `t`: `1+0.06*t/3` pushes in, `if(lt(t,1.2),1,1.12)` punches in on a beat |
| `transition` | `["fade", 0.4]` into this shot; any ffmpeg `xfade` type. Omit for a hard cut. |
| `scene_volume` | Level of Veo's own sound; `0` mutes a clip where Veo invented speech |
| `still_picture` | `true` shows the approved still instead of the clip (when Veo drifts) and keeps the clip's sound |

## What `cut` guards

- Video and audio both start at 0. Shifting timestamps by the AAC delay left a 0.021 s gap that
  players showed as a black first frame.
- Voice-over lines queue and never overlap. A line too long for its slot prints a warning
  instead of running into the next one.
- The narrator ducks the scene sound through a sidechain compressor, and every cut has a short
  audio fade, so cuts do not click.

## Test

```sh
./storyboard-video/storyboard-video.test.sh   # offline: synthetic clips, no project, no keys
```
