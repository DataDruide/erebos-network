#!/usr/bin/env python3
"""Legt den Vorstellungs-Thread idempotent in forum.db an.

Kategorie: allgemein
Autor: DataDruide
Sticky: ja
Idempotent: prueft vor INSERT, ob Titel existiert.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

# .env laden
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from erebos_network.forum_db import get_db


TITLE = "Wer seid ihr? Stellt euch vor"

BODY = """## Willkommen bei Erebos Network

Ich bin **DataDruide**, der Hauptentwickler von Erebos Network.

**Was ich mache:**
Ich baue ein anonymes P2P-Netzwerk mit Post-Quanten-Krypto
(ML-KEM-1024), Onion-Routing und SQLCipher. Schwerpunkte:
Kryptographie, Onion-Routing, Rendezvous-Protokoll.

**Warum:**
Erebos ist ein Forschungsprototyp - ich will zeigen, dass
anonyme Kommunikation mit moderner PQ-Krypto heute schon
moeglich ist, ohne auf Tor-Infrastruktur angewiesen zu sein.

**Was hier rein gehoert:**
Stell dich kurz vor - Handle, Rolle, Interesse. Keine persoenlichen
Daten (echter Name, Adresse, etc.).

**Template:**
- **Handle:** (Pseudonym, frei waehlbar)
- **Rolle:** (Nutzer / Entwickler / Tester / Interessiert)
- **Interesse:** (was willst du hier machen?)
- **Erfahrung:** (optional: Krypto, Netzwerke, Python, ...)

Ich freue mich auf euch."""


def main() -> int:
    conn = get_db()
    now = time.time()

    existing = conn.execute(
        "SELECT id FROM threads WHERE title = ?", (TITLE,)
    ).fetchone()
    if existing:
        print(f"SKIP: '{TITLE}' existiert schon (id={existing[0]})")
        return 0

    thread_id = uuid.uuid4().hex
    posts_json = json.dumps([{
        "author": "DataDruide",
        "body": BODY,
        "created_at": now,
    }])

    with conn:
        conn.execute(
            "INSERT INTO threads (id, category_id, title, author, "
            "created_at, last_activity, sticky, locked, posts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                thread_id,
                "allgemein",
                TITLE,
                "DataDruide",
                now,
                now,
                1,  # sticky
                0,  # locked
                posts_json,
            ),
        )

    print(f"OK: Thread '{TITLE}' angelegt (id={thread_id}, sticky)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
