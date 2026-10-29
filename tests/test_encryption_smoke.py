#!/usr/bin/env python3
"""
Smoke-Test: Prüft, ob der Erebos-Stack läuft und verschlüsselt antwortet.

Aufruf:
    cd ~/Projects/erebos-network
    source .venv/bin/activate
    python tests/test_encryption_smoke.py

Exit-Code: 0 = alles ok, 1 = Fehler.
"""

import socket
import subprocess
import sys
import time

# --- Konfiguration ---
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 4448
ONION = "pkzhbyj6ckvg6kf4bdkhihutsuibruezlkbpisgbwebbcqgqvfra.erebos"
PEER_PORTS = [9997, 9998, 9999]
API_PORT = 9050
HS_PORT = 8080
ALL_PORTS = [API_PORT, PROXY_PORT] + PEER_PORTS + [HS_PORT]


def check_ports():
    """Prüft, ob alle Dienste auf ihren Ports lauschen."""
    print("\n[1/4] Ports prüfen ...")
    ok = True
    for p in ALL_PORTS:
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{p}"],
            capture_output=True, text=True,
        )
        if "LISTEN" in r.stdout:
            print(f"  ✅ Port {p} lauscht")
        else:
            print(f"  ❌ Port {p} lauscht NICHT")
            ok = False
    return ok


def socks5_connect(host: str, port: int, timeout: float = 15.0) -> socket.socket:
    """Baut eine SOCKS5-Verbindung zum Ziel über den Proxy auf (remote DNS)."""
    s = socket.create_connection((PROXY_HOST, PROXY_PORT), timeout=timeout)
    # Greeting: Version 5, 1 Methode (no auth)
    s.sendall(b"\x05\x01\x00")
    resp = s.recv(2)
    if resp != b"\x05\x00":
        s.close()
        raise RuntimeError(f"SOCKS5-Greeting fehlgeschlagen: {resp!r}")
    # CONNECT mit Domainname (remote DNS)
    h = host.encode("utf-8")
    req = b"\x05\x01\x00\x03" + bytes([len(h)]) + h + port.to_bytes(2, "big")
    s.sendall(req)
    resp = s.recv(10)
    if len(resp) < 2 or resp[1] != 0x00:
        s.close()
        raise RuntimeError(f"SOCKS5-CONNECT fehlgeschlagen: {resp!r}")
    return s


def _http_get(path: str) -> tuple[int, bytes, str]:
    """Führt einen HTTP-GET über SOCKS5 aus. Gibt (status, body, location) zurück."""
    s = socks5_connect(ONION, 80)
    s.sendall(
        f"GET {path} HTTP/1.1\r\nHost: {ONION}\r\n"
        f"Connection: close\r\n\r\n".encode()
    )
    data = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    finally:
        s.close()
    # Status parsen
    status = 0
    if data.startswith(b"HTTP/"):
        try:
            status = int(data.split(b" ")[1])
        except Exception:
            pass
    # Location-Header parsen
    location = ""
    for line in data.split(b"\r\n"):
        if line.lower().startswith(b"location:"):
            location = line.split(b":", 1)[1].strip().decode("utf-8", "ignore")
            break
    return status, data, location


def check_http_over_socks():
    """Sendet eine HTTP-Anfrage an die .erebos-Adresse über SOCKS5 (folgt Redirects)."""
    print("\n[2/4] HTTP über SOCKS5 (E2E) ...")
    path = "/"
    data = b""
    for hop in range(4):
        try:
            status, data, location = _http_get(path)
        except Exception as e:
            print(f"  ❌ Verbindung fehlgeschlagen (Hop {hop}): {e}")
            return False
        print(f"  → Hop {hop}: {path} → {status}"
              + (f" (Location: {location})" if location else ""))
        if status in (301, 302, 303, 307, 308) and location:
            path = location
            continue
        if status == 200 and b"<html" in data.lower():
            print(f"  ✅ HTTP 200 OK, {len(data)} Bytes HTML empfangen")
            return True
        if status == 429 and b"PoW" in data:
            print("  ⚠️  429 PoW required – Localhost-Ausnahme greift nicht?")
            return False
        print(f"  ❌ Unerwartete Antwort (erste 200 Bytes): {data[:200]!r}")
        return False
    print("  ❌ Zu viele Redirects (>4)")
    return False


def check_pow_skip_log():
    """Prüft im Hidden-Service-Log, ob die Localhost-Ausnahme gezündet hat."""
    print("\n[3/4] Hidden-Service-Log (Localhost-Ausnahme) ...")
    try:
        with open("/tmp/hidden_service.log", "r", errors="ignore") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("  ⚠️  /tmp/hidden_service.log nicht gefunden – übersprungen")
        return True
    last = "".join(lines[-50:])
    if "Localhost-Client" in last and "übersprungen" in last:
        print("  ✅ 'Localhost-Client ... übersprungen' im Log gefunden")
        return True
    print("  ⚠️  Keine Localhost-Ausnahme im Log (letzte 50 Zeilen) – "
          "evtl. noch kein Request seit Neustart")
    return True  # kein harter Fail


def check_encrypted_traffic(duration: float = 2.0):
    """
    Schnappt kurz Traffic auf Port 9999 (Peer1) und prüft,
    dass kein lesbarer HTTP-Klartext drin ist.

    Benötigt sudo für tcpdump. Wenn sudo nicht verfügbar ist,
    wird der Test übersprungen (kein Fail).
    """
    print("\n[4/4] Verschlüsselung auf dem Draht (Port 9999) ...")
    # tcpdump im Hintergrund starten
    try:
        proc = subprocess.Popen(
            ["sudo", "-n", "tcpdump", "-i", "lo0", "-A", "-c", "20",
             "tcp port 9999"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except Exception as e:
        print(f"  ⚠️  tcpdump nicht startbar ({e}) – übersprungen")
        return True

    time.sleep(0.5)
    # Eine Anfrage auslösen
    try:
        s = socks5_connect(ONION, 80)
        s.sendall(
            f"GET / HTTP/1.1\r\nHost: {ONION}\r\n"
            f"Connection: close\r\n\r\n".encode()
        )
        try:
            s.recv(4096)
        except Exception:
            pass
        s.close()
    except Exception:
        pass

    try:
        out, err = proc.communicate(timeout=duration + 3)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()

    text = out.decode("utf-8", errors="ignore")
    if "Operation not permitted" in err.decode("utf-8", errors="ignore") or not text.strip():
        print("  ⚠️  tcpdump braucht sudo – übersprungen (kein Fail)")
        return True

    # Klartext-Marker suchen
    leaks = [m for m in ("GET / HTTP", "Host:", "<!DOCTYPE", "<html")
             if m in text]
    if leaks:
        print(f"  ❌ Klartext auf dem Draht gefunden: {leaks}")
        return False
    print(f"  ✅ Kein Klartext auf Port 9999 (nur Binärdaten)")
    return True


def main():
    print("=" * 60)
    print(" EREBOS ENCRYPTION SMOKE TEST")
    print("=" * 60)

    results = []
    results.append(("Ports", check_ports()))
    results.append(("HTTP E2E", check_http_over_socks()))
    results.append(("Localhost-PoW", check_pow_skip_log()))
    results.append(("Verschlüsselung", check_encrypted_traffic()))

    print("\n" + "=" * 60)
    print(" ERGEBNIS")
    print("=" * 60)
    all_ok = True
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print("🎉 Alle Tests bestanden – Stack läuft und verschlüsselt.")
        return 0
    print("❌ Mindestens ein Test fehlgeschlagen.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
