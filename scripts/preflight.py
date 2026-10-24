"""Check a new building in seconds, before running the agent on it.

  uv run python scripts/preflight.py <building_dir> [--json] [--data data]

Prints OK / WARN / FAIL per check (loads, ids, references, geometry, openings, floors, frame, entrances,
reachability, connectors, vocabulary vs. training data, every question kind once, a route, the questions file
next to the building). Exit code 1 if any FAIL."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from building_agent import preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("building_dir", type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--data", type=Path, default=None, help="training data root for the vocabulary check")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    findings = preflight.run(args.building_dir, args.data)
    if args.json:
        print(preflight.to_json(findings))
    else:
        print(f"preflight {args.building_dir}")
        print(preflight.render(findings))
        print(f"({time.perf_counter() - start:.1f}s)")
    return 1 if any(f.level == preflight.FAIL for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
