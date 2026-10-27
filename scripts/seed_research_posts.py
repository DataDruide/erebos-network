#!/usr/bin/env python3
"""Legt Forschungs-Beitraege idempotent in forum.db an.

Idempotent: prueft vor jedem INSERT, ob ein Thread mit dem Titel
schon existiert. Kein DELETE, kein Full-Rewrite.

Autor: "system" (kein User-Login noetig - author ist ein freier String).
Kategorie: "technik" (existiert bereits).
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


POSTS = [
    {
        "title": "E2E-Verschluesselung: HKDF-Domain-Separation",
        "body": "## Zusammenfassung\n\nErebos Network nutzt HKDF-SHA256 mit domain-separierten `info`-Strings fuer jede Verschluesselungsdomaene:\n\n| Domaene | info |\n|---------|------|\n| Onion-Layer | `b\"erebos-onion-v1\"` |\n| Tunnel (klassisch) | `b\"erebos-tunnel-v1\"` |\n| Tunnel (PQ-Hybrid) | `b\"erebos-tunnel-pq-v1\"` |\n| E2E-Stream | `b\"erebos-e2e-key-v1\"` |\n| Hybrid-AEAD | `b\"erebos-hybrid-aead-v1\"` |\n| Mail | `b\"erebos-mail-v1\"` |\n| PQ-Sphinx | `b\"erebos-pq-sphinx-key-v1\"` |\n\n## Warum das wichtig ist\n\nOhne Domain-Separation koennte dasselbe X25519-Shared-Secret in zwei verschiedenen Kontexten denselben Schluessel ableiten - Cross-Protocol-Key-Reuse. Ein Angreifer, der einen Schluessel kompromittiert, haette dann Zugriff auf beide Domaenen.\n\n## Review-Ergebnis\n\nAlle Domaenen sind getrennt. Kein Handlungsbedarf. Die Konvention ist `b\"erebos-<domaene>-v<version>\"`, damit spaetere Upgrades sauber getrennt werden koennen.\n\n## Referenz\n\n- `src/erebos_network/onion.py:37` - `HKDF_INFO = b\"erebos-onion-v1\"`\n- `src/erebos_network/tunnel.py:143` - `info=b\"erebos-tunnel-v1\"`\n- `src/erebos_network/e2e.py:47` - `E2E_INFO = b\"erebos-e2e-key-v1\"`\n"
    },
    {
        "title": "Onion-Routing: 3-Hop-Rendezvous mit ML-KEM-1024",
        "body": "## Aufbau\n\nErebos baut eine 3-Hop-Onion:\n\n```\nClient -> peer2 -> peer3 -> peer1 -> Hidden Service\n         (Hop1)   (Hop2)   (Hop3)\n```\n\nJede Schicht ist ein `seal_for(pubkey, plaintext)` mit X25519 ephemer + HKDF + ChaCha20-Poly1305. Die aeusserste Schicht enthaelt den Relay-Header (`FRAME_RELAY`, `next_port`), die naechste Schicht den naechsten Header, die innerste den Payload.\n\n## Rendezvous\n\n1. Client baut Onion und schickt sie an peer2\n2. peer2 entschluesselt seine Schicht, sendet Rest an peer3\n3. peer3 entschluesselt, sendet Rest an peer1\n4. peer1 entschluesselt die innerste Schicht, registriert den Client beim Rendezvous-Punkt\n5. Hidden Service registriert sich ebenfalls\n6. Rendezvous-Punkt sendet `ready` an beide\n7. E2E-Schluessel wird abgeleitet (`E2E_INFO`)\n8. HTTP-Traffic fliesst durch den Tunnel\n\n## Krypto\n\n- **X25519** fuer ECDH (ephemer, pro Layer)\n- **ML-KEM-1024** fuer PQ-Hybrid (NIST Level 5)\n- **HKDF-SHA256** fuer Key-Derivation\n- **ChaCha20-Poly1305** fuer AEAD\n\n## Anonymitaet\n\nJeder Hop sieht nur:\n- Seine eigene Schicht (Header + naechste Schicht)\n- Den Relay-Header (Frame-Typ, naechster Port)\n- NICHT die naechste Schicht im Klartext\n\nDie Anonymitaetsgarantie setzt **paarweise verschiedene Hop-Keys** voraus. Bei degenerierten Onions (identische Keys) ist die Entschluesselung der Mitte-Schicht korrekt - das ist in `docs/known-limitations.md` dokumentiert.\n\n## Referenz\n\n- `src/erebos_network/onion.py` - `pack_onion_3hop`, `open_layer`, `seal_for`\n- `src/erebos_network/proxy.py` - Rendezvous-Loop + Banner\n"
    },
    {
        "title": "SQLCipher: KDF-Parameter und Key-Validierung",
        "body": "## KDF\n\nSQLCipher v4 nutzt standardmaessig **PBKDF2-HMAC-SHA-512 mit 256.000 Iterationen** zur Schluesselableitung.\n\nErebos Network setzt `EREBOS_DB_KEY` als **rohen 32-Byte-Hex-Key** (256 Bit Entropie). Die KDF ist dann **nicht** sicherheitsrelevant, weil der Key bereits maximale Entropie hat.\n\n## Validierung\n\n`forum_db.get_db()` prueft:\n- Laenge: **64 Hex-Zeichen** (32 Bytes)\n- Format: `bytes.fromhex(db_key)` muss erfolgreich sein\n\nBei Fehler: `ValueError` mit klarer Meldung.\n\n**Wichtig:** Ein schwaches Passwort wuerde die KDF nicht retten. Deshalb ist die Laengen-/Format-Validierung Pflicht.\n\n## `.env`-Loading\n\n`restart_all.sh` und `create_test_hidden_service.py` laden `.env` **vor** dem Python-Import:\n\n```bash\nset -a\n. ./.env\nset +a\n```\n\nDamit ist `EREBOS_DB_KEY` in der Umgebung, bevor `get_db()` aufgerufen wird. Ohne das: `DatabaseError: file is not a database`.\n\n## Referenz\n\n- `src/erebos_network/forum_db.py:213` - Key-Validierung\n- `scripts/restart_all.sh` - `.env`-Loading\n- `src/erebos_network/paths.py` - `app_dir()`/`app_file()`\n"
    },
    {
        "title": "Property-Tests fuer Onion-Anonymitaet",
        "body": "## Was wird getestet?\n\nProperty-Test `test_peer2_cannot_decrypt_next_layer` in `tests/test_onion_properties.py`:\n\n> Peer2 kann die naechste Layer NICHT entschluesseln - unter der Voraussetzung, dass die drei Hop-Keys paarweise verschieden sind.\n\n## Implementierung\n\n```python\n@given(\n    peer2_priv=x25519_keys,\n    peer3_priv=x25519_keys,\n    peer1_priv=x25519_keys,\n    payload=messages,\n)\n@settings(max_examples=30, deadline=None)\ndef test_peer2_cannot_decrypt_next_layer(...):\n    assume(len({peer2_priv, peer3_priv, peer1_priv}) == 3)\n    onion = pack_onion_3hop(peer2_pub, peer3_pub, peer1_pub, payload)\n    layer2 = open_layer(peer2_priv, onion)\n    next_layer = layer2[3:]\n    with pytest.raises(Exception):\n        open_layer(peer2_priv, next_layer)\n```\n\n## Warum `assume()`?\n\n`hypothesis` generiert manchmal degenerierte Inputs (z.B. alle drei Keys = `b\"\\x00\"*32`). In dem Fall ist Peer2 == Peer3, und die Entschluesselung der Mitte-Schicht ist **korrekt**. `assume()` filtert diese Faelle heraus - der Test prueft nur realistische Onions.\n\n## Befund aus der Session\n\nDer Test hat **keinen Bug** in `open_layer` gefunden (ChaCha20-Poly1305 wirft korrekt `InvalidTag`). Aber er hat die Anonymitaetsannahme praezisiert: paarweise verschiedene Keys sind Voraussetzung.\n\n## Referenz\n\n- `tests/test_onion_properties.py` - Property-Test\n- `docs/known-limitations.md` - Onion-Anonymitaets-Voraussetzung\n"
    },
    {
        "title": "Chat-Hidden-Service: Random-Matchmaking-Architektur",
        "body": "## Ueberblick\n\nDer Chat ist ein **eigener Hidden Service** auf Port 8081 mit eigener `.erebos`-Adresse. Er nutzt dieselbe `HiddenServiceRuntime` wie das Forum, aber eigene Pages (`pages_chat.py`).\n\n## Features\n\n1. **Random-Chat** - In-Memory-Warteschlange\n2. **Raum erstellen** - 8-Hex-Raum-ID, Link teilbar\n3. **Raum beitreten** - per ID-Eingabe\n4. **Nachrichten** - Polling alle 1,5 s (kein WebSocket)\n\n## Matchmaking\n\n```python\ndef random_match(cookie):\n    existing = _CLIENT_ROOM.get(cookie)\n    if existing and _ROOMS[existing].get(\"random\"):\n        return {\"matched\": existing}\n    while _RANDOM_QUEUE:\n        partner = _RANDOM_QUEUE.pop(0)\n        if partner == cookie or partner in _CLIENT_ROOM:\n            continue\n        room_id = create_room(random=True)\n        join_room(room_id, cookie)\n        join_room(room_id, partner)\n        return {\"matched\": room_id}\n    _RANDOM_QUEUE.append(cookie)\n    return {\"waiting\": True}\n```\n\n## Persistenz\n\n**In-Memory** (`chat.py`). Bei Neustart des Hidden-Service sind alle Chats weg. Fuer einen Prototyp akzeptabel - fuer Produktion muesste man auf SQLite umstellen.\n\n## Routing\n\nIn `landing_pages.py`:\n- `/chat` -> Startseite\n- `/chat/random` -> Warteschlange\n- `/chat/random/status` -> JSON (`{\"waiting\": true}` / `{\"matched\": \"<id>\"}`)\n- `/chat/create` -> POST, redirect zu `/chat/room/<id>`\n- `/chat/join` -> POST, redirect zu `/chat/room/<id>`\n- `/chat/room/<id>` -> Chat-Raum\n- `/chat/room/<id>/messages?since=<ts>` -> JSON\n- `/chat/room/<id>/send` -> POST\n\n## Referenz\n\n- `src/erebos_network/chat.py` - Matchmaking, Rooms\n- `src/erebos_network/pages_chat.py` - HTML-Renderer\n- `scripts/create_chat_hidden_service.py` - eigener HS auf Port 8081\n"
    },
    {
        "title": "UX: Rendezvous-Banner und Phasen-Marker",
        "body": "## Problem\n\nDer Verbindungsaufbau in Erebos war schnell und unsichtbar. Der Nutzer sah nur `SOCKS5 -> ...` ohne Zwischenschritte.\n\n## Loesung\n\n**Phasen-Marker** im Log:\n\n```\n[1/4] Intro-Point-Tunnel ... OK (127.0.0.1:9999)\n[2/4] Rendezvous-Request ... OK\n[3/4] Onion-Build (3 Hops) ... OK (828B)\n[3/4] Onion an peer2 gesendet ... OK\n[4/4] Rendezvous-Paar vollstaendig!\n```\n\n**Banner** nach erfolgreichem Rendezvous:\n\n```\n+=====================================================+\n|  OK  RENDEZVOUS HERGESTELLT                       |\n+=====================================================+\n|  Ziel:     pkzhbyj6...erebos                      |\n|  Hops:     peer2 -> peer3 -> peer1               |\n|  Onion:    828 B, 3 Layer                        |\n|  conn_id:  #1                                    |\n+=====================================================+\n```\n\n## Design-Entscheidungen\n\n- **ASCII statt Unicode-Boxen** (`+---+` statt `\u2554\u2550\u2550\u2550\u2557`) - funktioniert in jedem Terminal, unabhaengig von Locale.\n- **Ein `logger.info`-Aufruf** mit `\\n` - erscheint in `docker logs` und `/tmp/proxy.log` als zusammenhaengender Block.\n- **Kein `time.sleep`** - die Marker erscheinen, wenn der Schritt wirklich fertig ist.\n- **`-v` = DEBUG** - Banner bleibt zwischen DEBUG-Zeilen sichtbar.\n\n## Ort\n\n`src/erebos_network/proxy.py`:\n- `_log_rendezvous_banner()` - Helper\n- Phasen-Marker in den `logger.info`-Zeilen des `.erebos`-Blocks\n\n## Referenz\n\n- `src/erebos_network/proxy.py:24` - `_log_rendezvous_banner`\n- `docs/known-limitations.md` - Design-Entscheidungen\n"
    },
]


def main() -> int:
    conn = get_db()
    now = time.time()
    inserted = 0
    skipped = 0

    for post in POSTS:
        existing = conn.execute(
            "SELECT id FROM threads WHERE title = ?", (post["title"],)
        ).fetchone()
        if existing:
            print(f"SKIP: {post['title']} (existiert schon)")
            skipped += 1
            continue

        thread_id = uuid.uuid4().hex
        posts_json = json.dumps([{
            "author": "system",
            "body": post["body"],
            "created_at": now,
        }])
        try:
            with conn:
                conn.execute(
                    "INSERT INTO threads (id, category_id, title, author, "
                    "created_at, last_activity, sticky, locked, posts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        thread_id,
                        "technik",
                        post["title"],
                        "system",
                        now,
                        now,
                        0,
                        0,
                        posts_json,
                    ),
                )
            print(f"OK: {post['title']}")
            inserted += 1
        except Exception as e:
            print(f"FEHLER bei {post['title']}: {e}")

    print()
    print(f"Fertig: {inserted} neu, {skipped} uebersprungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
