"""Copy a model run's results from out/ into a committed directory, with sealed-site names redacted and the
manifests left behind.

    uv run scripts/models_publish.py out/models docs/reports/<date>-<name>

Writes the ledger, probe, votes, SAM and review records and the recordings into the destination, plus
PUBLISHED.json listing the files and the number of redactions in each. See landers/models/publish.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landers.models.publish import publish  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    a = ap.parse_args(argv)
    rec = publish(Path(a.src), Path(a.dst))
    print(f"{len(rec['files'])} files to {a.dst}; {rec['total_redactions']} redactions")
    for name, f in rec["files"].items():
        if f["redactions"]:
            print(f"  {name}: {f['redactions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
