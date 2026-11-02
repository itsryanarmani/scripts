#!/usr/bin/env python3
"""Filter reviewer-venues.csv by region, field, type and application route.

Run:  python3 filter_venues.py --region "EU/UK" --field ai --no-phd --format table

Every flag is optional and flags combine with AND. --region, --field, --type
and --apply match case-insensitive substrings. --field checks both `field` and
`field_group`. --no-phd keeps rows where phd_required is not "yes".
"""

import argparse
import csv
import json
from pathlib import Path
import sys

DATA = Path(__file__).resolve().parent / "reviewer-venues.csv"
TABLE_COLUMNS = ["name", "region", "venue_type", "application_type", "phd_required", "signup_url"]


def has(needle, *values):
    needle = needle.lower()
    return any(needle in v.lower() for v in values)


def select(rows, args):
    out = []
    for r in rows:
        if args.region and not has(args.region, r["region"]):
            continue
        if args.field and not has(args.field, r["field"], r["field_group"]):
            continue
        if args.type and not has(args.type, r["venue_type"]):
            continue
        if args.apply and not has(args.apply, r["application_type"]):
            continue
        if args.no_phd and r["phd_required"].strip().lower() == "yes":
            continue
        out.append(r)
    return out


def render_table(rows):
    widths = [max([len(c)] + [len(r[c]) for r in rows]) for c in TABLE_COLUMNS]
    lines = ["  ".join(c.ljust(w) for c, w in zip(TABLE_COLUMNS, widths)).rstrip()]
    for r in rows:
        lines.append("  ".join(r[c].ljust(w) for c, w in zip(TABLE_COLUMNS, widths)).rstrip())
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--region", help="e.g. 'EU/UK', 'Asia', 'Global'")
    p.add_argument("--field", help="substring of field or field_group")
    p.add_argument("--type", help="venue_type, e.g. journal, 'conference PC'")
    p.add_argument("--apply", help="application_type, e.g. 'email editor'")
    p.add_argument("--no-phd", action="store_true", help="drop venues that require a PhD")
    p.add_argument("--format", choices=["csv", "json", "table"], default="csv")
    p.add_argument("--data", default=str(DATA), help="path to reviewer-venues.csv")
    args = p.parse_args(argv)

    with open(args.data, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = select(list(reader), args)

    if args.format == "json":
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        print()
    elif args.format == "table":
        print(render_table(rows))
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} venues", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
