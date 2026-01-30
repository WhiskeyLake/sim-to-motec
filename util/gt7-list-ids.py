#!/usr/bin/env python3
"""
util/gt7-list-ids.py
Scan GT7 dumper SQLite DB(s) for distinct CAR_CODE values and optionally map them to names
from `stm.gt7.db.cars`.

Usage examples:
  # scan a single DB
  python util/gt7-list-ids.py logs/raw/gt7-samples-20250101T120000.db

  # scan a directory of DBs, map names and write CSV template
  python util/gt7-list-ids.py logs/raw --map-names --csv out.csv

This script intentionally has no external dependencies.
"""

from collections import Counter
import argparse
import sqlite3
import os
import glob
import json
import sys
from pathlib import Path

# Ensure repository root is on sys.path so `import stm` works when this script
# is executed directly from the `util` directory (or from anywhere).
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stm.gt7.packet import GT7DataPacket

try:
    # lookup_car_name will return a friendly name if cars.csv is present
    from stm.gt7.db.cars import lookup_car_name
except Exception:
    def lookup_car_name(id):
        return f"CAR-{id}"


def find_dbs(path):
    """Return a list of DB files for a given path (file or directory)."""
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "gt7-samples-*.db")))
    return [path]


def scan_db(db_path, counter=None):
    """Scan a single sqlite DB and count car_code occurrences."""
    if counter is None:
        counter = Counter()

    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT data FROM samples")
    except Exception as exc:
        print(f"Error opening {db_path}: {exc}", file=sys.stderr)
        return counter

    for row in cur:
        try:
            data = row[0]
            pkt = GT7DataPacket(data)
            try:
                idval = int(pkt.car_code)
            except Exception:
                idval = pkt.car_code
            counter[idval] += 1
        except Exception:
            # ignore malformed packets
            continue

    con.close()
    return counter


def write_csv(path, counts, map_names=False):
    header = "ID,ShortName,Maker\n"
    lines = [header]
    # Sort by numeric ID when possible, otherwise fallback to original key
    def _sort_key(kv):
        k = kv[0]
        try:
            return int(k)
        except Exception:
            return k
    for id, cnt in sorted(counts.items(), key=_sort_key):
        name = lookup_car_name(id) if map_names else ""
        lines.append(f"{id},{name},\n")

    p = Path(path)
    # ensure the parent directory exists (mkdir -p behavior)
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.writelines(lines)
    print(f"Wrote CSV template to {p}")


def main():
    p = argparse.ArgumentParser(description="List distinct GT7 car IDs from dumper DB(s)")
    p.add_argument("paths", nargs="+", help="DB file(s) or directory(ies) to scan")
    p.add_argument("--top", type=int, default=0, help="Show only top N results")
    p.add_argument("--map-names", action="store_true", help="Resolve IDs to names using stm.gt7.db.cars")
    p.add_argument("--json", help="Write JSON summary to file")
    p.add_argument("--csv", help="Write a CSV template (ID,ShortName,Maker) to the given path")

    args = p.parse_args()

    counts = Counter()
    for pth in args.paths:
        for db in find_dbs(pth):
            print(f"Scanning {db}...")
            scan_db(db, counts)

    if not counts:
        print("No car codes found.")
        return

    common = counts.most_common()
    if args.top:
        common = common[: args.top]

    print("\nID      occurrences   name")
    print("------  -----------   ----")
    for id, cnt in common:
        name = lookup_car_name(id) if args.map_names else ""
        id_str = str(id)
        print(f"{id_str:>6}  {cnt:11d}   {name}")

    if args.json:
        out = {str(k): {"count": v, "name": (lookup_car_name(k) if args.map_names else None)} for k, v in counts.items()}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        print(f"Wrote JSON to {args.json}")

    if args.csv:
        write_csv(args.csv, counts, map_names=args.map_names)
        print(f"Wrote CSV template to {args.csv}")


if __name__ == "__main__":
    main()
