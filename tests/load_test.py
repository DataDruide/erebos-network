#!/usr/bin/env python3
"""Lasttest: 100 Requests ueber SOCKS5, Erfolgsrate + Latenz messen."""
import socket, time, statistics, sys

ONION = "pkzhbyj6ckvg6kf4bdkhihutsuibruezlkbpisgbwebbcqgqvfra.erebos"
PROXY = ("127.0.0.1", 4448)
N = 100


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Verbindung geschlossen")
        buf += chunk
    return buf


def one_request():
    t0 = time.monotonic()
    try:
        s = socket.create_connection(PROXY, timeout=15)
        s.sendall(b"\x05\x01\x00")
        if recv_exact(s, 2) != b"\x05\x00":
            s.close()
            return False, time.monotonic() - t0
        h = ONION.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(h)]) + h + (80).to_bytes(2, "big"))
        head = recv_exact(s, 4)
        if head[1] != 0x00:
            s.close()
            return False, time.monotonic() - t0
        atyp = head[3]
        if atyp == 0x01:
            recv_exact(s, 4 + 2)
        elif atyp == 0x03:
            ln = recv_exact(s, 1)[0]
            recv_exact(s, ln + 2)
        elif atyp == 0x04:
            recv_exact(s, 16 + 2)
        s.sendall(f"GET / HTTP/1.1\r\nHost: {ONION}\r\nConnection: close\r\n\r\n".encode())
        data = b""
        while True:
            c = s.recv(4096)
            if not c:
                break
            data += c
        s.close()
        ok = b"200" in data or b"302" in data
        return ok, time.monotonic() - t0
    except Exception:
        return False, time.monotonic() - t0


if __name__ == "__main__":
    results = []
    for i in range(N):
        ok, dt = one_request()
        results.append((ok, dt))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{N} ...")

    oks = [r for r in results if r[0]]
    fails = len(results) - len(oks)
    lat = [r[1] for r in oks]

    print(f"")
    print(f"Erfolg: {len(oks)}/{N} ({100 * len(oks) / N:.1f}%)")
    print(f"Fehler: {fails}")
    if lat:
        print("Latenz (nur Erfolge):")
        print(f"  min: {min(lat) * 1000:.1f} ms")
        print(f"  p50: {statistics.median(lat) * 1000:.1f} ms")
        print(f"  p95: {statistics.quantiles(lat, n=20)[18] * 1000:.1f} ms")
        print(f"  max: {max(lat) * 1000:.1f} ms")
