# ad-audio-qa failure modes

`ad-audio-qa` measures a finished video's audio with earshot and prints one
status per rule. This file lists every way a run can mislead. The E2E test
`ad-audio-qa.test.py` covers the rows marked "tested".

| # | Failure | Wanted behavior | Tested |
|---|---|---|---|
| 1 | ffmpeg/ffprobe missing (test only). | Test SKIPs, exit 0. | yes |
| 2 | No speech source for fixture words. | Test SKIPs, exit 0. | yes |
| 3 | earshot not importable and no `--earshot`/`AD_AUDIO_QA_EARSHOT`. | Exit 2, one-line error on stderr. | yes |
| 4 | `earshot llm` would upload audio. | Never called; only `measure`/`timeline`/audio helpers. | by design |
| 5 | Video has no audio stream. | `R6_dead_audio` FAIL (`has_audio=false`). | no |
| 6 | File is digital silence. | `R6_dead_audio` FAIL via `digital_silence_frac`. | no |
| 7 | Dead gap >= 1.5 s below -60 LUFS mid-file. | `R6_dead_audio` FAIL with gap time. | yes |
| 8 | Integrated loudness outside -16..-12 LUFS. | `loudness` FAIL with measured LUFS. | yes |
| 9 | True peak above -1 dBTP (clipped final). | `loudness` FAIL with measured dBTP. | yes |
| 10 | Sfx stem has no onsets at all (no sound effects). | `R14_sound_and_cuts` FAIL "Sound is required"; voice syllables on a mix never count. | yes |
| 11 | Fewer than 80% of cuts get an sfx onset within 80 ms. | `R14_sound_and_cuts` and `sfx_onset_80ms` FAIL with the share. | yes |
| 12 | No `--sfx-stem`: cut sync cannot separate sfx from voice. | Both rows NOT CHECKED with the reason, never a mixed-track PASS. | yes |
| 13 | SFX stem level within 6 dB of voice stem level. | `sfx_vs_voice` FAIL with the dB margin; needs both stems. | yes |
| 14 | Speech faster than 3.4 WPS (transcript given). | `R7_speech_pace` FAIL with true WPS. | yes |
| 15 | No transcript for pace. | `R7_speech_pace` NOT CHECKED; the old onset proxy never failed so it was removed. | yes |
| 16 | Per-character F0 spread > 1.6x across line wavs. | `R8_voice_consistency` FAIL. | no |
| 17 | No `--lines`: consistency unmeasurable. | `R8_voice_consistency` NOT CHECKED. | yes |
| 18 | `--lines` given but every wav fails or is unvoiced. | `R8_voice_consistency` NOT CHECKED with the recorded errors, never `PASS {}`. | no |
| 19 | Lines dir name contains glob characters (`[x]`). | `glob.escape` keeps the dir literal; files still found. | no |
| 20 | Caption segments > 300 ms off speech onsets. | `R10_caption_sync` FAIL with median/p90; word-only transcripts chunk into 3-word segments. | yes |
| 21 | No transcript or no VAD onsets for captions. | `R10_caption_sync` NOT CHECKED. | no |
| 22 | Bad transcript JSON. | `transcript_input` NOT CHECKED row prints the parse error in the table. | no |
| 23 | Missing or unreadable video or stem. | Exit 2 with a one-line error before any analysis. | yes |
| 24 | First earshot run. | Downloads models from Hugging Face once; no audio is uploaded. | by design |
| 25 | `--earshot` names a wrapper that re-invokes the tool. | `AD_AUDIO_QA_REEXEC` env marker allows one re-exec, then exits 2 instead of looping. | no |
| 26 | Subjective quality (face fit, acting, mix feel). | OWNER CHECK rows; never auto-PASS. | yes |
| 27 | Tool crashes mid-run. | Exit non-zero; `--out` JSON absent or partial. | no |
| 28 | Machine paths or secrets in output. | Report holds the input path and measurements only. | by design |
