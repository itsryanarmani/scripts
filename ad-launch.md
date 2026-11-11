# ad-launch

`ad-launch` creates one Meta image-ad test from an ad spec: one campaign, one ad
set and one ad per spec entry, all PAUSED. The tool has no code path that sets an
object to ACTIVE. It holds no account, Page, pixel, site or token: every value
comes from a flag, an environment variable or the spec. Standard library only.

## Use

Run Python with `-I`, so that a local file named like a standard module cannot replace it.

```sh
python3 -I ad-launch spec.json                       # dry run: no write to Meta
python3 -I ad-launch spec.json --execute --accept-currency CAD
```

| Flag or variable | Meaning |
| --- | --- |
| `--env-file`, `AD_LAUNCH_ENV_FILE` | File with `META_MARKETING_TOKEN=`. Keep it outside the repository. |
| `--ad-account-id`, `--page-id`, `--pixel-id` | Or `META_AD_ACCOUNT_ID`, `META_PAGE_ID`, `META_PIXEL_ID`. |
| `--instagram-user-id`, `META_INSTAGRAM_USER_ID` | Instagram identity. Without it, placements are Facebook only. |
| `--accept-currency` | Required with `--execute`. Must equal the ad account currency. |
| `--start` | ISO start time with an offset. Default: tomorrow 06:00 local time. |

Exit: 0 clean, 1 dry-run problem, 2 refused before any write, 3 a create failed part
way (each object that exists is listed, PAUSED), 4 read-back shows an object not PAUSED.

## Ad spec

[`ad-launch.example.json`](ad-launch.example.json) is an example for a made-up business. Paths are relative to the spec.

| Field | Meaning |
| --- | --- |
| `campaign.name` | Must be new. An existing campaign with this name stops the run. |
| `campaign.special_ad_categories` | For example `["HOUSING"]`. Needs `special_ad_category_country`. |
| `ad_set.lifetime_budget`, `duration_days` | Budget in the account currency, sent in minor units. The end date is start plus the days. |
| `ad_set.countries`, `age_min`, `age_max` | Broad targeting. HOUSING needs ages 18 to 65. |
| `ad_set.custom_event_type` | Pixel event to optimize for. Default `LEAD`. |
| `source_text` or `source_text_file` | The text that the copy quotes. |
| `ads[]` | `id`, `name`, `primary_text`, `headline`, `description`, `link_url` (with UTMs), `cta`, `image`. |

The copy guard refuses wording about the reader's own hardship ("behind on",
"are you"), and any number or price that is not in the source text.

## Safe-launch order

1. Make the landing page live. The tool refuses a link that does not return 200.
2. Run the dry run. Read every call it prints.
3. Run `--execute`. Every object is created PAUSED.
4. Read the read-back: configured and effective status, budget, dates, targeting, link.
5. Check that the pixel receives the conversion event from the live page.
6. A person activates the ads in Ads Manager. This tool never does.

## Platform traps

- **Budget sharing flag.** Ad-set budget needs `is_adset_budget_sharing_enabled=false` on the campaign.
- **Instagram identity.** An Instagram placement with no Instagram identity fails.
- **HOUSING.** A special ad category needs its country and limits age targeting.
- **Currency.** The budget is in the ad account currency. `--accept-currency` confirms it.
- **Rate limit.** Code 17 / 2446079: waits of 60, 120, 240 s, then stop. No other retries.
- **Page-creation limit.** Meta limits new Pages per account. Create the Page days before.

## Test

`AD_LAUNCH_TRANSCRIPT=/tmp/ad-launch.txt python3 -I ad-launch.test.py` runs the real tool
against a fake Graph API server. The failure cases are at the top of the test file.
