#!/usr/bin/env python3
"""Interaktiver E2E-Chat-Client fuer Erebos Network.

Nutzt X25519 + ML-KEM-1024 (hybrid) fuer den Schluesselaustausch
und ChaCha20-Poly1305 fuer Nachrichten.

Der Hidden Service speichert nur Public Keys + Ciphertext.

Aufruf:
    # Terminal 1 (Initiator)
    python scripts/chat_e2e_client.py --room <room-id> --addr <hs-addr> --role initiator

    # Terminal 2 (Responder)
    python scripts/chat_e2e_client.py --room <room-id> --addr <hs-addr> --role responder
"""

import argparse
import json
import sys
import time
from pathlib import Path

# .env laden
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    import os
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from erebos_network.chat_e2e import E2ESession
import urllib.request
import urllib.error
import socket


class Socks5HTTPClient:
    """Minimaler HTTP-Client ueber SOCKS5 (ohne externe Abhaengigkeiten)."""

    def __init__(self, socks_host="127.0.0.1", socks_port=4448):
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.cookie = ""

    def _socks5_connect(self, target_host: str, target_port: int) -> socket.socket:
        """Stellt SOCKS5-Verbindung zu target her."""
        sock = socket.create_connection((self.socks_host, self.socks_port), timeout=15)
        # Greeting
        sock.sendall(b"\x05\x01\x00")
        resp = sock.recv(2)
        if resp != b"\x05\x00":
            raise RuntimeError(f"SOCKS5-Greeting fehlgeschlagen: {resp!r}")
        # Request (Domain-Name)
        host_bytes = target_host.encode()
        req = b"\x05\x01\x00\x03" + bytes([len(host_bytes)]) + host_bytes + target_port.to_bytes(2, "big")
        sock.sendall(req)
        resp = sock.recv(10)
        if len(resp) < 2 or resp[1] != 0:
            raise RuntimeError(f"SOCKS5-Connect fehlgeschlagen: {resp!r}")
        return sock

    def request(self, method: str, host: str, port: int, path: str,
                body: bytes = b"", headers: dict | None = None) -> tuple[int, bytes]:
        """Fuehrt HTTP-Request ueber SOCKS5 aus. Gibt (status, body) zurueck."""
        sock = self._socks5_connect(host, port)
        try:
            hdrs = {
                "Host": host,
                "Connection": "close",
                "User-Agent": "erebos-chat-e2e/1.0",
            }
            if self.cookie:
                hdrs["Cookie"] = self.cookie
            if headers:
                hdrs.update(headers)
            if body:
                hdrs["Content-Type"] = "application/json"
                hdrs["Content-Length"] = str(len(body))
            req = f"{method} {path} HTTP/1.1\r\n"
            for k, v in hdrs.items():
                req += f"{k}: {v}\r\n"
            req += "\r\n"
            sock.sendall(req.encode() + body)

            # Response lesen
            data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        finally:
            sock.close()

        # Parse HTTP-Response
        if b"\r\n\r\n" not in data:
            raise RuntimeError(f"Ungueltige HTTP-Antwort: {data[:100]!r}")
        header_block, resp_body = data.split(b"\r\n\r\n", 1)
        lines = header_block.split(b"\r\n")
        status_line = lines[0].decode()
        status = int(status_line.split()[1])
        for line in lines[1:]:
            if line.lower().startswith(b"set-cookie:"):
                cookie_val = line.split(b":", 1)[1].strip()
                if b";" in cookie_val:
                    cookie_val = cookie_val.split(b";", 1)[0]
                self.cookie = cookie_val.decode()
                break
        return status, resp_body


def _json_post(client, addr, path, data):
    body = json.dumps(data).encode()
    status, resp = client.request("POST", addr, 80, path, body=body)
    if status != 200:
        raise RuntimeError(f"POST {path} -> HTTP {status}: {resp[:200]!r}")
    return json.loads(resp)


def _json_get(client, addr, path):
    status, resp = client.request("GET", addr, 80, path)
    if status != 200:
        raise RuntimeError(f"GET {path} -> HTTP {status}: {resp[:200]!r}")
    return json.loads(resp)


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E-Chat-Client")
    parser.add_argument("--room", required=True, help="Raum-ID")
    parser.add_argument("--addr", required=True, help="Hidden-Service-Adresse (.erebos)")
    parser.add_argument("--role", required=True, choices=["initiator", "responder"])
    parser.add_argument("--socks-host", default="127.0.0.1")
    parser.add_argument("--socks-port", type=int, default=4448)
    parser.add_argument("--poll-interval", type=float, default=1.5)
    parser.add_argument(
        "--key-file",
        default=None,
        help="Pfad zur Session-Datei (Default: ~/.erebos/chat_e2e_keys/<room>.json)",
    )
    args = parser.parse_args()

    client = Socks5HTTPClient(args.socks_host, args.socks_port)

    # 1. E2E-Session laden oder erstellen
    if args.key_file:
        key_file = Path(args.key_file)
    else:
        key_file = Path.home() / ".erebos" / "chat_e2e_keys" / f"{args.room}-{args.role}.json"

    if key_file.exists():
        session = E2ESession.load(str(key_file))
        print(f"[*] Session geladen: {key_file}")
        print(f"[*] Rolle: {session.role}")
        if session.role != args.role:
            print(f"[!] FEHLER: Session-Rolle ({session.role}) != --role ({args.role})")
            print(f"[!] Loesche die Datei {key_file} oder nutze --role {session.role}")
            return 1
    else:
        session = E2ESession(role=args.role)
        session.save(str(key_file))
        print(f"[*] Neue Session gespeichert: {key_file}")
        print(f"[*] Rolle: {args.role}")
    print(f"[*] Raum: {args.room}")
    print(f"[*] X25519-Pub: {session.x25519_pub.hex()[:16]}...")
    print(f"[*] ML-KEM-Pub: {session.mlkem_pub.hex()[:16]}...")

    # 2. Key-Exchange
    if args.role == "initiator":
        payload = session.initiator_payload()
        print("[*] Sende Initiator-Key...")
        resp = _json_post(client, args.addr, f"/chat/room/{args.room}/e2e/key", {
            "role": payload.role,
            "x25519_pub": payload.x25519_pub.hex(),
            "mlkem_pub": payload.mlkem_pub.hex(),
        })
        print(f"[*] Server: {resp}")

        # Warte auf Responder-Key
        print("[*] Warte auf Responder-Key...")
        while True:
            partner = _json_get(client, args.addr, f"/chat/room/{args.room}/e2e/key")
            if partner.get("waiting"):
                time.sleep(2)
                continue
            break
        print(f"[*] Partner-Rolle: {partner['role']}")

        # Decapsulieren
        session.finalize_initiator(
            bytes.fromhex(partner["x25519_pub"]),
            bytes.fromhex(partner["mlkem_ct"]),
        )
        print(f"[*] Shared Secret abgeleitet")
        print(f"[*] Fingerprint: {session.fingerprint}")

    else:  # responder
        # 1. Zuerst eigenen Key registrieren (ohne mlkem_ct)
        print("[*] Registriere Responder-Key (ohne mlkem_ct)...")
        resp = _json_post(client, args.addr, f"/chat/room/{args.room}/e2e/key", {
            "role": "responder",
            "x25519_pub": session.x25519_pub.hex(),
            "mlkem_pub": session.mlkem_pub.hex(),
        })
        print(f"[*] Server: {resp}")

        # 2. Warte auf Initiator-Key
        print("[*] Warte auf Initiator-Key...")
        while True:
            partner = _json_get(client, args.addr, f"/chat/room/{args.room}/e2e/key")
            if partner.get("waiting") or partner.get("error"):
                time.sleep(2)
                continue
            if partner.get("role") != "initiator":
                time.sleep(2)
                continue
            break
        print(f"[*] Initiator-Pub empfangen")

        # 3. Encapsulieren
        payload = session.responder_payload(
            bytes.fromhex(partner["x25519_pub"]),
            bytes.fromhex(partner["mlkem_pub"]),
        )
        print("[*] Sende Responder-Key + mlkem_ct...")
        resp = _json_post(client, args.addr, f"/chat/room/{args.room}/e2e/key", {
            "role": payload.role,
            "x25519_pub": payload.x25519_pub.hex(),
            "mlkem_pub": payload.mlkem_pub.hex(),
            "mlkem_ct": payload.mlkem_ct.hex(),
        })
        print(f"[*] Server: {resp}")
        print(f"[*] Shared Secret abgeleitet")
        print(f"[*] Fingerprint: {session.fingerprint}")

    # 3. REPL
    print()
    print("=" * 60)
    print(f"  E2E-Chat bereit. Fingerprint: {session.fingerprint}")
    print("  Vergleiche diesen Fingerprint mit deinem Partner")
    print("  (ausserhalb des Kanals: Telefon, persoenlich).")
    print("  Wenn er uebereinstimmt, ist der Kanal frei von MITM.")
    print("=" * 60)
    print()
    print("Tippe Nachrichten. /quit zum Beenden.")
    print()

    since = 0.0
    last_poll = 0.0
    own_ids = set()

    try:
        while True:
            # Polling: neue Nachrichten
            now = time.time()
            if now - last_poll > args.poll_interval:
                last_poll = now
                try:
                    msgs = _json_get(
                        client, args.addr,
                        f"/chat/room/{args.room}/e2e/messages?since={since}"
                    )
                    for m in msgs:
                        if m.get("id") in own_ids:
                            since = max(since, m["ts"])
                            continue
                        try:
                            plaintext = session.decrypt(
                                bytes.fromhex(m["nonce"]),
                                bytes.fromhex(m["ciphertext"]),
                            )
                            print(f"\n[Partner] {plaintext.decode('utf-8', 'replace')}")
                        except Exception as e:
                            print(f"\n[!] Entschluesselung fehlgeschlagen: {e}")
                        since = max(since, m["ts"])
                except Exception as e:
                    pass  # Netzwerkfehler ignorieren

            # Eingabe (mit Timeout, damit Polling weiterlaeuft)
            import select
            if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.rstrip("\n")
                if line == "/quit":
                    break
                if not line:
                    continue
                # Verschluesseln + senden
                nonce, ct = session.encrypt(line.encode("utf-8"))
                resp = _json_post(
                    client, args.addr,
                    f"/chat/room/{args.room}/e2e/send",
                    {"nonce": nonce.hex(), "ciphertext": ct.hex()},
                )
                if resp.get("ok"):
                    print(f"[Du] {line}")
                    # Eigene Nachricht merken (wird beim Polling uebersprungen)
                    own_ids.add(resp.get("id", -1))
                else:
                    print(f"[!] Senden fehlgeschlagen: {resp}")
    except KeyboardInterrupt:
        pass

    print("\n[*] Beende.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
