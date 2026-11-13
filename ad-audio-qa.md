# ad-audio-qa

`ad-audio-qa` runs measured audio rule checks on a finished video. It calls
[earshot](https://github.com/Leonxlnx/earshot) (MIT) as an external runtime
dependency: this repo holds no earshot code or models. Every rule prints
PASS, FAIL, NOT CHECKED or OWNER CHECK with the measured value. Exit: 0 no
FAIL, 1 any FAIL, 2 usage error or missing earshot, 3 `--require-stems` with every sfx rule NOT CHECKED.

## Use

```sh
python3 ad-audio-qa video.mp4 --earshot /path/to/earshot \
    --sfx-stem sfx.wav --voice-stem voice.wav --transcript words.json
python3 ad-audio-qa video.mp4 --out report.json
```

`--earshot` (or `AD_AUDIO_QA_EARSHOT`) points at an earshot checkout (a dir
holding `venv/`), the venv itself, or its python binary. With it the tool
re-execs into that python so `import earshot` works (an env marker stops a
wrapper from looping it). It runs any binary the flag names — the same
trust as `PATH`. If earshot cannot be imported it exits 2 with a one-line
error. The tool never runs `earshot llm`: that command uploads audio.

| Flag | Meaning |
| --- | --- |
| `--sfx-stem FILE` | Wav of the sfx alone (leave the laugh track out). Needed for R14 cut sync and `sfx_vs_voice`. |
| `--voice-stem FILE` | Wav of the voice track alone. Needed with `--sfx-stem` for `sfx_vs_voice`. |
| `--lines DIR\|GLOB` | Per-line voice wavs for the R8 consistency check. |
| `--voice-map JSON` | `{line_name: character}` grouping for R8. |
| `--transcript JSON` | Word timings for true WPS (R7) and caption sync (R10). A `groups` list gives caption segments directly; word-only input is chunked into 3-word segments. |
| `--cuts T1,T2,...` | Comma-separated cut times in seconds. Overrides ffmpeg scene detection for R14; the detail always lists the cut times used. |
| `--require-stems` | Exit 3 when every sfx rule is NOT CHECKED. |
| `--out FILE` | Write the full JSON report (all values and details). |

## Rules and thresholds

| Rule | Pass condition |
| --- | --- |
| `R6_dead_audio` | No dead stretch >= 1.5 s below -60 LUFS; no all-digital-silence file. The 400 ms momentary window can shorten a gap by ~0.4 s, so run the ffmpeg `silencedetect` and `freezedetect` check from the skill rule as the gate; this tool is a coarse guard. |
| `loudness` | Integrated -16 to -12 LUFS (target -14); true peak <= -1 dBTP. |
| `R14_sound_and_cuts` | >= 80% of sfx-stem onsets land within 80 ms of a picture cut (ffmpeg scene > 0.3, or `--cuts`). A cue counts as on a cut when the start, the attack (first frame within 10 dB of its max) or the peak of any of its sounds is within 80 ms, so a riser into a cut, a swell from a cut, a held hit and a soft pre-hit before a boom all sync; a sound that starts within 0.25 s of a cue's first sound joins that cue (a second, unrelated hit 200 ms after an on-cut hit is absorbed), and a steady tick bed does not chain into one cue. Precision, not recall: sfx only on events, never one per cut, so a cut with no sfx is fine. No onsets = FAIL "Sound is required". |
| `sfx_onset_80ms` | Same onset-on-cut share as R14, reported as its own row. |
| `sfx_vs_voice` | Voice-stem per-event RMS at least 6 dB over sfx-stem per-event RMS. Both decode to 48 kHz through one chain; levels read the louder channel per frame, so mono, stereo, panned and 22.05 kHz stems agree within ~0.5 dB and time shifts do not move the reading. |
| `R7_speech_pace` | True WPS <= 3.4 with `--transcript`; NOT CHECKED without it. |
| `R8_voice_consistency` | Per-character F0 ratio (max/min line median): <= 1.25 PASS, above 1.25 OWNER CHECK "pitch spread is a weak proxy, listen to these lines". It never FAILs: a calibration on our own videos found that neither pitch spread nor a speaker embedding separated the one voice the owner rejected from eleven voices the owner accepted. NOT CHECKED unless some character has 2 or more usable lines. |
| `R10_caption_sync` | Caption-segment median offset <= 300 ms and >= 70% within 300 ms of speech onsets. |
| `R8_voice_face_fit`, `R11_mouth_vs_voice`, `owner_judgment` | OWNER CHECK: always need a person. |

Without `--sfx-stem`, R14 and `sfx_onset_80ms` print NOT CHECKED: a mixed
track cannot separate sfx from voice (earshot counts voice syllables as
sound events). Without both stems, `sfx_vs_voice` prints NOT CHECKED for
the same reason. Stems are assumed to start at t=0 with the video; a stem
shorter or longer by more than 0.5 s prints a WARN line. A bad
`--transcript` or `--voice-map` JSON prints a `transcript_input` /
`voice_map_input` NOT CHECKED row with the parse error, and a bad
`--voice-map` also marks R8 NOT CHECKED. An unreadable `--sfx-stem`
prints its decode error in the R14 rows.

## What it cannot judge

Audio-only tooling cannot verify voice-to-face fit, ethnicity/age/character
fit, mouth-to-voice sync, acting quality, joke quality, music taste or mix
feel. Those rows stay OWNER CHECK. The F0 check measures consistency, not
correctness: one voice can be consistent and still wrong for the face.

## Honest limits

- Thresholds are tuned for short ad spots; long-form pacing differs.
- Cut sync and sfx level need the separated stems; on a mix they are NOT
  CHECKED, never guessed.
- `sfx_vs_voice` compares the median per-event RMS of each stem (events
  are active runs above a fixed -60 dBFS floor), not perceived loudness.
- R7 and R10 need `--transcript`; R10 onsets come from an energy VAD.
- A laugh track inside `--sfx-stem` lowers onset precision: laughs do not
  land on cuts. Export the laugh as a separate file or leave it out of
  `--sfx-stem`.
- A click or beep on every cut passes: the tool measures timing, not what
  the sound is.
- A soft picture cut under the scene > 0.3 threshold is missed; the R14
  detail lists the detected cut times, and `--cuts` overrides detection.
- earshot's `mono=True` decode downmixes stereo at -3 dB per channel;
  level checks use the stereo decode and the louder channel instead.
- The first earshot run downloads about 1.1 GB of model weights from
  Hugging Face; no audio is uploaded, and later runs work offline.
- Earshot is CPU-only and local; large files take minutes.
