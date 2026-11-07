# paper-venues failure modes

`paper-venues` turns the venue tables in `itsryanarmani/skills` (`paper-submission/references/venues*.md` and `free-venues.md`) into one JSON file, and answers questions about it: which venues are free, which to avoid, which row mentions a word. It reads only Markdown tables. It never calls the network and never submits anything.

The tests in `paper-venues.test.sh` cover each row marked "tested".

| # | Failure | Wanted behavior | Tested |
|---|---|---|---|
| 1 | The references directory does not exist or holds no venue files. | Exit 2 with a message that names the directory. Write no JSON. | yes |
| 2 | A table row has a different number of cells than its header, for example an unescaped pipe in a cell. | Skip the row, count it, and print the count to stderr. Do not guess. | yes |
| 3 | A row has no name cell. | Skip it and count it. A record without a name cannot be found. | yes |
| 4 | A venue is both in a listed table and in an "avoid" table. | Keep both records. `list --kind avoid` still shows the warning. | yes |
| 5 | The JSON on disk is older than the Markdown. | `paper-venues check <dir>` rebuilds in memory and exits 1 when the JSON differs. | yes |
| 6 | A cell says `UNVERIFIED`. | Keep the word. `stats` counts rows with at least one `UNVERIFIED` cell. Never replace it with a guess. | yes |
| 7 | `show` matches two venues. | Print all matches. Exit 0. | yes |
| 8 | `show` matches nothing. | Exit 1 with `no venue matches`. | yes |
| 9 | A query contains regex characters. | Treat it as plain text. | yes |
| 10 | Someone reads a deadline from the JSON as current. | Every record keeps `checked`, the date written in its file header, and `source_file`. The tool prints both. A person re-opens the venue page before acting. | no, a human rule |
| 11 | The tool is used to submit or to register. | There is no such command. Dual submission to two peer-reviewed venues is a person's decision. | no, absent by design |
