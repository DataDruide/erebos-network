#!/usr/bin/env python3
"""Einmalige Migration: ergaenzt unvollstaendige mail_keys-Eintraege.

Aufruf im Container:
    docker-compose exec -T hidden-service python3 scripts/migrate_incomplete_mail_keys.py

Idempotent.
"""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))
from erebos_network.forum_db import get_db, get_or_create_mail_keys


def main() -> int:
    conn = get_db()
    rows = conn.execute(
        "SELECT uuid FROM mail_keys "
        "WHERE ed25519_pub IS NULL OR mldsa_pub IS NULL "
        "   OR ed25519_priv IS NULL OR mldsa_priv IS NULL"
    ).fetchall()
    print(f"Unvollstaendige UUIDs: {len(rows)}")
    if not rows:
        print("Nichts zu tun.")
        return 0
    ok = fail = 0
    for (uuid,) in rows:
        print(f"  migriere {uuid[:8]}...")
        try:
            keys = get_or_create_mail_keys(uuid)
            print(f"    OK: ed25519_pub len={len(keys['ed25519_pub'])}, "
                  f"mldsa_pub len={len(keys['mldsa_pub'])}")
            ok += 1
        except Exception as e:
            print(f"    FEHLER: {e}")
            fail += 1
    print("")
    print(f"Fertig: {ok} erfolgreich, {fail} fehlgeschlagen")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
