# ad-audio-qa failure modes

`ad-audio-qa` measures a finished video's audio with earshot and prints one
status per rule. This file lists every way a run can mislead. The E2E test
`ad-audio-qa.test.py` covers the rows marked "tested".

| # | Failure | Wanted behavior | Tested |
|---|---|---|---|
| 1 | ffmpeg/ffprobe missing (test only). | Test SKIPs, exit 0. | yes |
| 2 | No speech source for fixture words. | Test SKIPs, exit 0. | yes |
| 3 | earshot not importable and no `--earshot`/`AD_AUDIO_QA_EARSHOT`. | Exit 2, one-line error on stderr. | no |
| 4 | `earshot llm` would upload audio. | Never called; only `measure`/`timeline`/audio helpers. | by design |
| 5 | Video has no audio stream. | `R6_dead_audio` FAIL (`has_audio=false`). | no |
| 6 | File is digital silence. | `R6_dead_audio` FAIL via `digital_silence_frac`. | no |
| 7 | Dead gap >= 1.5 s below -60 LUFS mid-file. | `R6_dead_audio` FAIL with gap time. | yes |
| 8 | Integrated loudness outside -16..-12 LUFS. | `loudness` FAIL with measured LUFS. | no |
| 9 | True peak above -1 dBTP (clipped final). | `loudness` FAIL with measured dBTP. | no |
| 10 | Sfx stem has no onsets at all (no sound effects). | `R14_sound_and_cuts` FAIL "Sound is required"; voice syllables on a mix never count. | yes |
| 11 | Under 80% of sfx onsets land within 80 ms of a picture cut (sfx floating between cuts). | `R14_sound_and_cuts` and `sfx_onset_80ms` FAIL with the onset share; sfx on only some cuts still PASSes. | yes |
| 12 | No `--sfx-stem`: cut sync cannot separate sfx from voice. | Both rows NOT CHECKED with the reason, never a mixed-track PASS. | yes |
| 13 | SFX stem level within 6 dB of voice stem level. | `sfx_vs_voice` FAIL with the dB margin; needs both stems. | yes |
| 14 | Speech faster than 3.4 WPS (transcript given). | `R7_speech_pace` FAIL with true WPS. | yes |
| 15 | No transcript for pace. | `R7_speech_pace` NOT CHECKED; the old onset proxy never failed so it was removed. | yes |
| 16 | Per-character F0 ratio far above 1.25x across line wavs. | `R8_voice_consistency` OWNER CHECK, never FAIL (pitch flags voices the owner accepted). | yes |
| 16a | Per-character F0 ratio above 1.25x (possible voice swap on one character). | `R8_voice_consistency` OWNER CHECK "pitch spread is a weak proxy, listen to these lines" with the ratio and per-line medians; <= 1.25x PASSes. | yes |
| 17 | No `--lines`: consistency unmeasurable. | `R8_voice_consistency` NOT CHECKED. | yes |
| 18 | `--lines` given but every wav fails or is unvoiced. | `R8_voice_consistency` NOT CHECKED with the recorded errors, never `PASS {}`. | no |
| 19 | Lines dir name contains glob characters (`[x]`). | `glob.escape` keeps the dir literal; files still found. | no |
| 20 | Caption segments > 300 ms off speech onsets. | `R10_caption_sync` FAIL with median/p90; word-only transcripts chunk into 3-word segments. | yes |
| 21 | No transcript for captions (no VAD onsets is not tested). | `R10_caption_sync` NOT CHECKED. | yes |
| 22 | Bad transcript JSON. | `transcript_input` NOT CHECKED row prints the parse error in the table. | yes |
| 23 | Missing or unreadable video or stem, or an undecodable video. | Exit 2 with a one-line error; a text file named .mp4 exits 2 with the ffprobe error. A stem that exists but does not decode gives NOT CHECKED with the error (row 36). | yes |
| 24 | First earshot run. | Downloads about 1.1 GB of model weights from Hugging Face once; no audio is uploaded, later runs work offline. | by design |
| 25 | `--earshot` names a wrapper that re-invokes the tool. | `AD_AUDIO_QA_REEXEC` env marker skips a second re-exec and imports earshot in the current Python; it exits 2 only if that import fails. | no |
| 26 | Subjective quality (face fit, acting, mix feel). | OWNER CHECK rows; never auto-PASS. | yes |
| 27 | Tool crashes mid-run. | Exit non-zero; `--out` JSON absent or partial. | no |
| 28 | Machine paths or secrets in output. | Report holds the input path and measurements only. | by design |
| 29 | Bad `--voice-map` JSON. | `voice_map_input` NOT CHECKED row prints the parse error in the table. | yes |
| 30 | Stem shorter or longer than the video by > 0.5 s. | WARN line; stems are assumed aligned at t=0 with the video. | yes |
| 31 | `--require-stems` and every sfx rule NOT CHECKED. | Exit 3 instead of 0. | yes |
| 32 | Mono, stereo, panned, 22.05 kHz versions of the same stems, or stems shifted 60 ms (0-150 ms was checked by hand in review). | `sfx_vs_voice` margin agrees within 0.5 dB: one 48 kHz decode chain, louder channel per frame, per-event RMS over a fixed -60 dBFS floor. | yes |
| 33 | R8 lines where no character repeats (one line each). | `R8_voice_consistency` NOT CHECKED; a spread needs a repeat. | yes |
| 34 | Sfx with a ramp-in (riser/whoosh) ending on each cut. | R14 PASSes: an event syncs at its start, attack or peak. | yes |
| 35 | Bad `--voice-map` JSON while `--lines` groups by filename anyway. | `R8_voice_consistency` NOT CHECKED too; the filename fallback never PASSes a bad map. | yes |
| 36 | `--sfx-stem` file exists but cannot be decoded. | R14 rows NOT CHECKED with the decode error as the value, not `null`. | yes |
| 37 | Soft picture cut under the scene > 0.3 threshold, or known cut times. | R14 detail lists the detected cut times; `--cuts T1,T2,...` overrides detection. | yes |
| 38 | Laugh track mixed into `--sfx-stem`. | Onset precision drops: laughs do not land on cuts. Export the laugh separately or leave it out. | no |
| 39 | A click or beep on every cut. | R14 PASSes: the tool measures timing, not what the sound is. | no |
| 40 | A held hit, or a soft hit followed within 0.25 s by a louder boom. | R14 PASSes: one cue, attack on the cut. | yes |
| 41 | A soft pre-hit 200 ms before a boom on the cut, or a swell that starts on the cut and peaks 500 ms later. | R14 PASSes: the cue keeps every sound's start, attack and peak. | yes |
| 42 | A steady bed of ticks or foley (a sound every 0.2 s). | R14 FAILs: cues are measured from the cue's first sound, so the bed does not chain into one always-passing cue. | yes |
| 43 | A second unrelated hit within 0.25 s after an on-cut hit. | Absorbed into the cue: R14 PASSes. A 0.25 s window cannot tell a layered cue from an unrelated sound. | no |
