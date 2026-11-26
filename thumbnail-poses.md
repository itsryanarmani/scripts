# thumbnail-poses and thumbnail-export

Two scripts for YouTube thumbnails that show a real person. `thumbnail-poses`
makes many poses of one person. `thumbnail-export` turns a chosen layout into
a checked 1280x720 file. The skill `youtube-thumbnails` (in the skills repo)
says when to use each and holds the layouts, tactics and checklists.

## thumbnail-poses

```sh
python3 thumbnail-poses --dry-run --out poses                 # prompts and cost, no network
python3 thumbnail-poses --ref a.jpg --ref b.jpg --out poses --yes
python3 thumbnail-poses --ref a.jpg --out poses --tags sad,shocked,pointing --yes
```

| Flag | Meaning |
| --- | --- |
| `--ref PHOTO` | Reference photo of the person. Repeat it. Two or three with different expressions work best. |
| `--out DIR` | Where `<tag>.png` and `index.json` go. |
| `--tags` | `all` (25 poses, default) or a comma list. Tags: see `POSES` in the script. |
| `--model ID` | WaveSpeed image-edit model. Default `openai/gpt-image-2/edit`. |
| `--jobs N` | Parallel runs. Default 3. Each run uses its own input file. |
| `--force` | Redo poses that already exist. |
| `--yes` | Required. The reference photos go to WaveSpeed's CDN. |
| `--dry-run` | Print the prompts and the estimated cost. Needs no key. |

Each pose is a 16:9 photo with the person on the right 45% and a flat colour
behind, so a layout can put text on the left. The page reads the background
colour from the top-left pixel and picks a text colour from it.

**Cost.** About $0.07 per pose, $1.75 for all 25 (measured November 2026 on
`openai/gpt-image-2/edit`). A run of 15 poses with 3 jobs took about 6 minutes.
Existing poses are skipped, so a rerun only pays for the missing ones.

**Likeness.** The output is generated, not photographed. Use your own face, or a
person who agreed. Do not show an event that did not happen as if it did.

**Why no text in the image.** Image models misspell words. The gallery draws
the text, so every name is exact.

## thumbnail-export

```sh
python3 thumbnail-export --gallery gallery --out thumbs --layout 5 --item all
python3 thumbnail-export --gallery gallery --out thumbs --layout 5,12 --item 3 --pose sad
```

`--gallery` is a folder with `index.html`, `config.json` (`{"items":[{"title":"..."}]}`),
`poses/` and, optionally, `cutout.png`. The template is in the skills repo
under `youtube-thumbnails/assets/gallery`. Layout and item numbers start at 1.
It serves the folder on `127.0.0.1`, opens each thumbnail in headless Chrome,
and checks the file: PNG, exactly 1280x720, at most 2 MB. A larger PNG is
re-encoded as JPEG if `ffmpeg` is installed. It prints one JSON line per file.

Exit codes: 0 all ok, 1 a check failed, 2 usage error, a missing Chrome, or a
missing `wavespeed` CLI.

## Failure modes

| Symptom | Cause and fix |
| --- | --- |
| `Prediction submission failed ... must be an array` | The CLI turns a repeated `-i images=` into a string. The script uses `--input-file`, so this only appears if you call the CLI by hand. |
| A pose shows a different person | The reference photos were too few or too similar. Add a clearer front photo and rerun with `--force --tags TAG`. |
| Background not flat | The model added a gradient. Rerun that tag. The text colour is still read from the top-left pixel. |
| Export is not 1280x720 | The page did not size itself to 1280x720 or Chrome added a scrollbar. The page must draw exactly one 1280x720 box. |
| Export over 2 MB | `ffmpeg` converts it to JPEG. Without `ffmpeg` the file is reported as failed. |
| Blank export | The page needs `#solo=1`. A page loaded from `file://` cannot read pose pixels, so the script serves the folder over HTTP. |

## Test

`python3 thumbnail-export.test.py` builds a fixture gallery and runs both
scripts. It checks the exports (names, 1280x720, under 2 MB), the over-limit
failure, bad input, and the `thumbnail-poses` dry run and guards. It calls no
external service. It skips the export part when Chrome is missing.
