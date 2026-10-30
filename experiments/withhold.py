"""Withhold named files from a published model run, keeping them under out/ only, and say so in PUBLISHED.json.

    uv run experiments/withhold.py docs/reports/<dir> --reason "<why>" <relative path> ...

For records that scripts/leakcheck.sh flags for a reason that is not a leak (a measured number that equals
a sealed site's published coordinate). The numbers are never edited; the file is left out of the commit,
its source copy stays in the run's out/ directory, and PUBLISHED.json lists it under "withheld".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("published")
    ap.add_argument("--reason", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    pub = Path(a.published)
    record = json.loads((pub / "PUBLISHED.json").read_text())
    withheld = record.setdefault("withheld", {})
    for rel in a.files:
        if rel not in record["files"]:
            print(f"{rel}: not a published file", file=sys.stderr)
            return 2
        (pub / rel).unlink(missing_ok=True)
        record["files"].pop(rel)
        withheld[rel] = {"reason": a.reason, "source": f"{record['source']}/{rel}"}
    (pub / "PUBLISHED.json").write_text(json.dumps(record, indent=1) + "\n")
    print(f"withheld {len(a.files)} files; {len(withheld)} in total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
