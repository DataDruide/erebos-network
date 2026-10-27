#!/usr/bin/env python3
"""Benchmark: wie lange dauern die Keygens fuer Mail-Keys?

Misst X25519, ML-KEM-1024, Ed25519, ML-DSA-65 und die Gesamt-Rotation.
"""
import statistics
import sys
import time

sys.path.insert(0, "/app/src")

import oqs
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def bench(name, fn, n=10):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    mean = statistics.mean(times)
    med = statistics.median(times)
    print(f"  {name:25s} mean={mean*1000:7.2f}ms  median={med*1000:7.2f}ms  max={max(times)*1000:7.2f}ms")
    return mean


def gen_x25519():
    priv = X25519PrivateKey.generate()
    priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def gen_mlkem():
    kem = oqs.KeyEncapsulation("ML-KEM-1024")
    kem.generate_keypair()
    kem.export_secret_key()


def gen_ed25519():
    priv = Ed25519PrivateKey.generate()
    priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def gen_mldsa():
    sig = oqs.Signature("ML-DSA-65")
    sig.generate_keypair()
    sig.export_secret_key()


def gen_all():
    gen_x25519()
    gen_mlkem()
    gen_ed25519()
    gen_mldsa()


def main():
    print("=== Keygen-Benchmark (10 Durchlaeufe) ===")
    print()
    m_x = bench("X25519", gen_x25519)
    m_k = bench("ML-KEM-1024", gen_mlkem)
    m_e = bench("Ed25519", gen_ed25519)
    m_d = bench("ML-DSA-65", gen_mldsa)
    print()
    m_all = bench("Alle vier (Rotation)", gen_all)
    print()
    print(f"Summe einzeln: {(m_x + m_k + m_e + m_d)*1000:.2f}ms")
    print(f"Rotation gesamt: {m_all*1000:.2f}ms")
    print()
    if m_all < 0.2:
        print("=> Schnell genug (<200ms). Keine Optimierung noetig.")
    else:
        print("=> Langsam (>200ms). Threading-Optimierung empfohlen.")


if __name__ == "__main__":
    main()
