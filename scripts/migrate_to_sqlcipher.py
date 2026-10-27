#!/usr/bin/env python3
"""Migriert eine unverschluesselte SQLite-DB nach SQLCipher.

Aufruf:
    python3 scripts/migrate_to_sqlcipher.py

Voraussetzungen:
- EREBOS_DB_KEY gesetzt (sonst Fehler)
- forum.db existiert (unverschluesselt)
- sqlcipher3 installiert (im Container)
"""
import os
import sys
import sqlite3
from pathlib import Path

# Pfade
DB_PATH = Path("/app/forum.db")
BACKUP_PATH = Path("/app/forum.db.unencrypted.bak")
TEMP_PATH = Path("/app/forum.db.encrypted")


def main() -> int:
    key = os.environ.get("EREBOS_DB_KEY", "")
    if not key:
        print("FEHLER: EREBOS_DB_KEY nicht gesetzt")
        return 1

    if not DB_PATH.exists():
        print(f"FEHLER: {DB_PATH} existiert nicht")
        return 1

    # 1. Pruefen, ob DB schon verschluesselt ist
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("SELECT COUNT(*) FROM users")
        conn.close()
        print("DB ist unverschluesselt — starte Migration")
    except Exception:
        print("DB ist bereits verschluesselt (oder korrupt) — nichts zu tun")
        return 0

    # 2. Backup der unverschluesselten DB
    import shutil
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup: {BACKUP_PATH}")

    # 3. SQLCipher-Export
    try:
        from sqlcipher3 import dbapi2 as sqlcipher
    except ImportError:
        print("FEHLER: sqlcipher3 nicht installiert")
        return 1

    # 3a. Alte DB oeffnen (unverschluesselt)
    old = sqlite3.connect(str(DB_PATH))

    # 3b. Neue DB mit SQLCipher anlegen
    new = sqlcipher.connect(str(TEMP_PATH))
    new.execute(f"PRAGMA key='{key}'")
    new.execute("PRAGMA cipher_compatibility = 4")

    # 3c. Export via ATTACH + sqlcipher_export
    new.execute(f"ATTACH DATABASE '{DB_PATH}' AS plaintext KEY ''")
    new.execute("SELECT sqlcipher_export('plaintext')")
    new.execute("DETACH DATABASE plaintext")
    new.close()

    # 3d. Alte DB ersetzen
    shutil.move(str(TEMP_PATH), str(DB_PATH))
    print(f"OK: Migration abgeschlossen — {DB_PATH} ist jetzt verschluesselt")
    print(f"     Backup: {BACKUP_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
