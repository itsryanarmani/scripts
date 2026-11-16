# ad-event-switch

`ad-event-switch` moves Meta ad sets to a new conversion event. Meta does not let you edit the
event of a published ad set (`error_subcode 3260011`, "Can't Make Edits to Published Ad Set"). So the
tool copies each ad set with the new event and, when you ask, retires the original. Standard library
only. It holds no account, pixel or token: every value comes from a flag or an environment variable.

## Use

Run Python with `-I`, so that a local file named like a standard module cannot replace it.

```sh
python3 -I ad-event-switch --ad-account-id 123 --env-file ~/meta.env \
  --from-event ADD_TO_CART --to-event INITIATED_CHECKOUT                 # dry run: no write to Meta
python3 -I ad-event-switch ... --execute                                  # create PAUSED copies
python3 -I ad-event-switch ... --execute --activate                       # activate copies, pause originals
python3 -I ad-event-switch.test.py                                        # E2E test on a fake Graph API server
```

| Flag | Meaning |
| --- | --- |
| `--from-event`, `--to-event` | Required. The tool copies active ad sets that optimize for the first event. |
| `--adset` | Limit to one ad set id. Repeat for more. |
| `--execute` | Create each copy `PAUSED`, with its ads `PAUSED`. Nothing runs and the original is untouched. |
| `--activate` | With `--execute`: activate the ads and the copy, then pause the original. |
| `--max-extra-cents` | Most extra budget one copy may need to meet Meta's minimum. Default 200. |
| `--env-file`, `META_MARKETING_TOKEN` | The token. Keep the file outside the repository. |

Exit: 0 clean, 2 refused (bad input, or at least one ad set refused because its minimum budget is over the cap or it has no ACTIVE ad or a setting the tool cannot copy; the others are still copied), 3 a call failed (the output lists what exists). If a write got no reply at all, the output says `OUTCOME UNKNOWN`: Meta may have applied it, so check Ads Manager before a rerun.

## What a copy keeps

Same campaign, targeting, end time, billing event, attribution window and lowest-cost bid strategy. Same ads: each ad keeps its
`creative_id`, so the ad keeps its post and the likes and comments on it. The pixel stays; only the
event changes. A copy is named `<old name> [<EVENT>]`, and a rerun skips an ad set that already has one.

The tool refuses an ad set that has a bid cap, a cost cap, dayparting, a frequency cap, or a budget on the campaign, because the copy would lose it. A refusal counts in the summary and gives exit 2.
It also refuses an ad set with no ACTIVE ad, so it never replaces a running ad set with an empty one.

## Order of steps

Run `--activate` in the same run as `--execute`. A copy from an earlier `--execute` run counts as existing, so a later
`--execute --activate` skips it. Activate such a copy by hand in Ads Manager.
With `--activate`, the tool activates the ads and the copy, then pauses the original. If that last pause fails, the
output says `BOTH ARE LIVE` and names the original. Pause it at once, or spend can double.

## Budget

A copy gets the budget that remains on the original, not the original total. Meta sets a minimum
lifetime budget and states it in the error ("must be more than CA$7.59"). When the remainder is lower,
the tool retries with that minimum. For a lifetime budget, total spend rises once by the difference. For a daily budget,
the rise repeats each day, so read `--max-extra-cents` as a per-day cap there. It skips an ad set whose rise is over
`--max-extra-cents`, creates nothing for it, goes on to the next, and prints the amount for any rise it makes.

## Limits

- The tool reads every ad set of the account, a page at a time. It follows the cursor, not `paging.next`, because that URL carries the token.
- It copies ad sets with a lifetime budget or a daily budget. A campaign-level budget is not copied.
- It copies the first 50 ads of an ad set.
- The ad account has its own call limit (`code 17`, `subcode 2446079`). The tool waits 60, 120 and 240 seconds, then stops.
- A new ad set shows `IN_PROCESS` while its ads are in review. That is normal.
- Check first that the site really sends the new event. Switching to an event that never fires gives empty Results again. See the `ads-meta` skill.
