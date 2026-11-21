# typefully-quote-chain

Posts a launch series where each X post quotes the one before it. A post has no X URL until it publishes, so
the chain fills one link at a time: when post N is live, this sets draft N+1's `quote_post_url` (X only) and
schedules it `gap_days` later. A draft is never scheduled before its quote is set. LinkedIn, Threads and
Bluesky post the same draft's text and media at the same time.

It is the tool half of the `social-launch-post` skill in pooriaarab/skills.

## Use

1. Create the drafts in Typefully, all platforms enabled, with no `publish_at`. Schedule the first one by
   hand, with its quote if it quotes an older post.
2. Write a chain file:

   ```json
   {"social_set": 23679, "gap_days": 2, "chain": [11168919, 11168920, 11168921]}
   ```

3. Install the job. It runs every 15 minutes and stops itself when the chain is done:

   ```sh
   TYPEFULLY_API_KEY=... typefully-quote-chain/typefully-quote-chain install chain.json
   ```

| Command | Does |
| --- | --- |
| `run` | One pass. Prints `waiting`, `scheduled` or `complete`. Errors go to the log; the exit status stays 0. |
| `selftest <draft>` | Re-sends a draft unchanged and checks its text, media and platforms survive. |
| `install <chain.json>` | Copies the tool and chain file to `~/Library/Application Support/typefully-quote-chain/` and starts the launchd job. |
| `uninstall` | Stops the job and removes its plist. |

The log is `~/Library/Application Support/typefully-quote-chain/chain.log`.

## Why it is built this way

- **launchd cannot read `~/Documents`** under the macOS privacy rules. `install` copies the tool out of the
  checkout and stores the key in the login Keychain item `typefully-api`.
- **A PATCH re-sends every enabled platform**, built from the draft just read. The quote goes on the first X
  post only.
- **Each platform keeps its own text.** An edit in the Typefully editor often changes X only. Compare the
  platforms after any edit; this tool keeps whatever each one holds.
- **The job waits on a post that never publishes.** X can block a post with a URL from automated publishing.
  If a post fails at its time, publish it in Typefully's UI, and the chain continues.

## Test

```sh
./typefully-quote-chain/typefully-quote-chain.test.sh
```

It runs against `fake_typefully.py`, a local stand-in that drops any platform a PATCH leaves out.
