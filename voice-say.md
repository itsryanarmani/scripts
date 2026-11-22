# voice-say

`voice-say` turns text into speech in the owner's saved voice clone. It calls
the `wavespeed` CLI with `minimax/speech-02-hd`. The repo holds no voice ID and
no key. Both stay in `~/Documents/Personal/.secrets/`.

## Use

```sh
voice-say "Thanks for watching." line.mp3
voice-say "A long script" out.wav --dry-run   # price only, nothing sent
voice-say "A very long script" out.mp3 --yes  # go past the spend cap
```

| Flag | Meaning |
| --- | --- |
| `--dry-run` | Print the price. Send nothing. |
| `--cap USD` | Spend cap for one call. Default 1.00. |
| `--yes` | Allow a call over the cap. |
| `--voice-file F` | Voice record to use. Default `wavespeed-voice/voice.json` in the secrets folder. |

Exit: 0 ok, 1 the call failed or no audio came back, 2 usage, setup or cap
refusal. The price is $0.10 per 1,000 characters.

## Setup

Train the voice once with the `voice-clone-from-video` skill. That writes
`voice.json`. `WAVESPEED_API_KEY` comes from the environment or from
`wavespeed.env` in the same secrets folder. The key never goes on a command line.

## Rules

- Use your own voice only.
- Synthetic speech does not match lips. Say it is synthetic where a viewer would care, such as a job application.

## Test

`./voice-say.test.sh` makes one real call (about $0.001). It also runs four
controls that must fail: over the cap, no voice record, empty text, bad file
type. It prints a JSON verdict.
