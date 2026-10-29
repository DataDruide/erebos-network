#!/usr/bin/env python3
"""Fehlerfall-Test: Peer killen, Request senden, Verhalten pruefen."""
import subprocess, time, socket, sys

ONION = "pkzhbyj6ckvg6kf4bdkhihutsuibruezlkbpisgbwebbcqgqvfra.erebos"
PROXY = ("127.0.0.1", 4448)

def kill_peer(port):
    out = subprocess.check_output(["lsof", "-nP", f"-iTCP:{port}"]).decode()
    for line in out.splitlines():
        if "LISTEN" in line:
            pid = line.split()[1]
            subprocess.run(["kill", "-9", pid])
            return True
    return False

def http_via_socks(timeout=10):
    s = socket.create_connection(PROXY, timeout=timeout)
    s.sendall(b"\x05\x01\x00")
    assert s.recv(2) == b"\x05\x00", "SOCKS5-Greeting fehlgeschlagen"
    h = ONION.encode()
    s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + (80).to_bytes(2, "big"))
    resp = s.recv(10)
    assert len(resp) >= 2 and resp[1] == 0x00, "SOCKS5-CONNECT fehlgeschlagen"
    s.sendall(f"GET / HTTP/1.1\r\nHost: {ONION}\r\nConnection: close\r\n\r\n".encode())
    data = b""
    while True:
        c = s.recv(4096)
        if not c:
            break
        data += c
    s.close()
    return data

if __name__ == "__main__":
    print("[1/3] Normaler Request ...")
    try:
        data = http_via_socks()
        assert b"200" in data or b"302" in data, "Normaler Request fehlgeschlagen"
        print("      OK")
    except Exception as e:
        print(f"      FEHLER: {e}")
        sys.exit(1)

    print("[2/3] Peer1 (9999) killen ...")
    if not kill_peer(9999):
        print("      Peer1 nicht gefunden")
        sys.exit(1)
    print("      Peer1 gekillt")
    time.sleep(2)

    print("[3/3] Request nach Peer-Ausfall ...")
    try:
        data = http_via_socks(timeout=8)
        if b"200" in data or b"302" in data:
            print("      Fallback funktioniert (oder Peer schnell neu gestartet)")
        else:
            print(f"      Unerwartete Antwort: {data[:100]!r}")
    except Exception as e:
        print(f"      Erwarteter Fehler: {type(e).__name__}: {e}")

    print("")
    print("Test beendet. Peer1 manuell neu starten:")
    print("  cd ~/Projects/erebos-network && source .venv/bin/activate")
    print("  export EREBOS_PEER_HOST=0.0.0.0")
    print("  nohup python -m erebos_network --peer --peer-port 9999 --ack-cover -v > /tmp/peer1.log 2>&1 &")
