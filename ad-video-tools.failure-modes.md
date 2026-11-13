# ad-video-tools failure modes

- `ad-video-master` measures the file it wrote. If pass 1 reports
  `normalization_type: dynamic`, loudnorm rides the gated loudness and
  can land off target — the final-file FAIL is real. No audio stream
  fails at measure.
- `ad-caption-ocr` fails on ANY card over 0.10 CER, so one hard-to-read
  card (thin font, busy background) fails the video. Vision misreads
  stylized type a person reads fine — check `got` before blaming the
  render. Needs `swiftc` + Vision (macOS), else exit 2.
- `ad-video-sync` dead gaps need BOTH a freeze and a silence. Dead air
  under music above -35 dB is not silence and passes. `freezedetect` at
  -60 dB can miss a fade-to-black with grain noise. A static end card
  IS a freeze: even a 0.3 s breath pause fails as a dead gap.
- `ad-caption-ocr` CER is strict-greater-than 0.10: one letter swap in
  a 20+ character caption can hide; punctuation and emoji are stripped.
- `ad-video-sync` tail uses a -35 dBFS 0.1 s RMS floor on downmixed 8 kHz
  PCM; quiet reverb tails read as silence and inflate the tail.
