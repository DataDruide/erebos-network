#!/usr/bin/env python3
"""Manueller Auto-Rotation-Lauf.

Aufruf:
    docker-compose exec -T hidden-service python3 scripts/auto_rotate.py
    docker-compose exec -T hidden-service python3 scripts/auto_rotate.py --dry-run
    docker-compose exec -T hidden-service python3 scripts/auto_rotate.py --days 3
"""
import argparse
import sys

sys.path.insert(0, "/app/src")

from erebos_network.forum_db import auto_rotate_expiring_keys


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Rotation ablaufender Mail-Keys")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur auflisten, nicht rotieren")
    parser.add_argument("--days", type=float, default=None,
                        help="Schwellwert in Tagen (Default aus config)")
    args = parser.parse_args()

    result = auto_rotate_expiring_keys(
        days_before=args.days,
        dry_run=args.dry_run,
    )

    print()
    print(f"Rotiert:  {len(result['rotated'])}")
    print(f"Fehler:   {len(result['failed'])}")
    print(f"Skip:     {len(result['skipped'])}")
    if result["failed"]:
        for uuid, err in result["failed"]:
            print(f"  FEHLER {uuid[:8]}: {err}")
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
