# Drivers

One module per board. Run one with `python3 ../run.py <driver>`. Read `../README.md`
first for the setup, the settings and the loop rules.

| Driver | Board | What it does | Limit and gotchas | Needs |
|---|---|---|---|---|
| `nhs` | Not Human Search | Files the site URL in an anonymous form. | None seen. Check the board's search API for the domain to prove it. | Nothing. |
| `neeed` | Neeed Directory | Clicks "Verify Badge" on the product page, then reads the outbound link `rel`. Records `live`. | About 10 actions an hour, so the delay is 6 minutes. The slug is the slug of the site name. A held listing has no button and is recorded `blocked`. | The badge on the live site. |
| `greenrocket` | GreenRocket | Fills the launch form, picks a category, clicks the first enabled day, files. | At most 10 launches a day. Calendar days are not in the snapshot, so `eval` clicks the day. | Logo and cover images. Category in `categories.greenrocket` (default "Other Tools"). |
| `buildvoyage` | BuildVoyage | Fills a 3-step wizard. `--confirm` clicks the emailed links. It records a site only when the confirmation page shows the site name or host. Else it fails and writes no row. | HTTP 429 after about 9 in 70 minutes. The maker email must sit on the product domain. | Logo image. `DIRSUB_MAIL_ACCOUNT` for `--confirm`. |
| `unloc` | Unloc Tools | Fills the form, waits for the managed Turnstile, files. | About 6 submissions in 90 minutes per network. The Turnstile passes in the owner's Chrome. This is not a solve. | `DIRSUB_MAKER_NAME`. Category in `categories.unloc`. |
| `clapstorm` | Clapstorm | Fills the launch form and files. The page goes live on the weekly board. | 3 launches a week per account, so the retry is 7 days. | Logo image. Category in `categories.clapstorm`. |
| `aitoolshunt` | AI Tools Hunt | Fills the free listing form. | The page shows no confirmation. An unclear result is recorded `blocked`. Never file a site twice. | `DIRSUB_MAKER_NAME`, `DIRSUB_COMPANY`. |

Each driver sets `TARGET` to the board's name in the registry
(`website-directory-submission/directories.csv` in itsryanarmani/skills). Keep the
two the same, so the ledger and the registry match.

The selectors came from the round 3 run on 2026-10-22. Boards change their
forms. Run `--dry-run` on one site first. It fills the form and files nothing.
Fix a selector in the driver, never in `lib.py`.
