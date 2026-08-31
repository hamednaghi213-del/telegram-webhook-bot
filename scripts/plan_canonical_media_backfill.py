"""Offline-only JSON planner. It intentionally has no database connection."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.canonical_media_backfill import build_backfill_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run canonical media backfill")
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--mappings", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    mappings = json.loads(args.mappings.read_text(encoding="utf-8"))
    plan = build_backfill_plan(snapshot, mappings)
    rendered = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if plan["safe_to_apply"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
