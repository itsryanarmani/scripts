# reviewer-venues

A dataset of 287 places that accept new peer reviewers worldwide, plus a small
script to filter it. Every venue is legitimate and charges no fee: journals,
publisher reviewer programs, reviewer databases, conference program committees,
artifact evaluation committees and practitioner magazines.

Files:

| File | What |
|---|---|
| `reviewer-venues.csv` | The dataset, one venue per row |
| `reviewer-venues.json` | The same rows as JSON |
| `filter_venues.py` | Filter script, Python 3 standard library only |

## Columns

| Column | Meaning |
|---|---|
| `name` | Venue or program name |
| `publisher` | Publisher, society or organiser |
| `region` | `Global`, `North America`, `EU/UK`, `Asia`, `Latin America`, `Africa`, `Middle East` or `Oceania` |
| `country` | Country of the publisher or organiser |
| `field` | Specific subject area |
| `field_group` | Broader subject group |
| `venue_type` | `journal`, `conference PC`, `publisher program`, `practitioner magazine`, `reviewer database` or `artifact evaluation` |
| `signup_url` | Page to start from |
| `phd_required` | `yes`, `no`, `preferred` or `unknown` |
| `publications_required` | Whether prior publications are needed |
| `orcid_required` | Whether an ORCID iD is needed |
| `other_criteria` | Anything else the venue asks for |
| `application_type` | `account + reviewer profile`, `email editor`, `volunteer form`, `invitation only` or `open form` |
| `form_asks` | What the application asks for |
| `deadline_cadence` | `Rolling`, `Annual` and similar |
| `fee` | Fee charged to reviewers (`none` throughout) |
| `predatory_check` | Why the venue was judged legitimate |
| `url_check` | Result of the link check |

## Counts

By region:

| Region | Venues |
|---|---|
| Global | 102 |
| North America | 64 |
| EU/UK | 64 |
| Asia | 27 |
| Latin America | 13 |
| Africa | 11 |
| Middle East | 4 |
| Oceania | 2 |

By venue type:

| Venue type | Venues |
|---|---|
| journal | 195 |
| conference PC | 42 |
| publisher program | 17 |
| practitioner magazine | 15 |
| reviewer database | 9 |
| artifact evaluation | 9 |

By application type:

| Application type | Venues |
|---|---|
| account + reviewer profile | 133 |
| email editor | 85 |
| volunteer form | 45 |
| invitation only | 20 |
| open form | 4 |

## Filter

```bash
python3 filter_venues.py [--region R] [--field F] [--type T] [--apply A] [--no-phd] [--format csv|json|table]
```

Flags combine with AND. `--region`, `--type` and `--apply` match a
case-insensitive substring of `region`, `venue_type` and `application_type`.
`--field` matches `field` or `field_group`. `--no-phd` drops venues where
`phd_required` is `yes`. The default format is `csv`; the match count goes to
stderr.

```bash
# Journals in the EU/UK that do not need a PhD, in AI
python3 filter_venues.py --region "EU/UK" --field ai --type journal --no-phd --format table

# Every venue you can apply to by emailing the editor, as JSON
python3 filter_venues.py --apply "email editor" --format json

# Artifact evaluation committees
python3 filter_venues.py --type artifact
```

## Caveats

- Compiled in November 2026. Check the venue before relying on a row.
- Many requirement fields are `unknown`. The venue did not publish the
  requirement, or it was not found.
- A `url_check` of bot-blocked means the page refuses scripts. Open it in a
  browser.
- Conference pages point at the 2026 cycle. Look for the next year's call.
- Predatory and fee-charging venues are excluded.
- Verify the requirements on the official page before you apply.

## How to become a reviewer

The
[`journal-reviewer-applications`](https://github.com/pooriaarab/skills/tree/main/journal-reviewer-applications)
skill in [skills](https://github.com/pooriaarab/skills) walks through the
profiles to set up first and how to apply.
