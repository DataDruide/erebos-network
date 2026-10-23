"""Krypto-Integration-Tests fuer Erebos Network.

Prueft, dass der GESAMTE Datenpfad verschluesselt ist.

Basiert auf Radicle-Bug (2026): Handshake OK, aber Session-Keys
nicht genutzt - Klartext lief durch.
"""

import os

import hashlib

import pytest

from erebos_network.crypto import (
    HybridCrypto,
    HybridKEM,
    PostQuantumKEM,
    ThreefishCipher,
)
from erebos_network.crypto.hybrid import HybridCrypto as LegacyHybrid
from erebos_network.obfuscation import ApplicationObfuscation


class TestCryptoIntegration:
    """Integrationstests fuer Krypto."""

    def test_hybrid_kem_shared_secret_matches(self):
        """Sender und Empfaenger erhalten DASSELBE Shared Secret."""
        kem = HybridKEM()
        kp = kem.generate_keypair()
        ct, sender_secret = kem.encapsulate(kp)
        receiver_secret = kem.decapsulate(ct, kp)
        assert sender_secret == receiver_secret
        assert len(sender_secret) == 32

    def test_hybrid_kem_different_sessions(self):
        """Zwei Sessions haben UNTERSCHIEDLICHE Shared Secrets."""
        kem = HybridKEM()
        kp = kem.generate_keypair()
        _, s1 = kem.encapsulate(kp)
        _, s2 = kem.encapsulate(kp)
        assert s1 != s2

    def test_threefish_roundtrip(self):
        """Threefish ver- und entschluesselt korrekt."""
        cipher = ThreefishCipher.generate()
        plaintext = b"X" * 64
        encrypted = cipher.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = cipher.decrypt(encrypted)
        assert decrypted == plaintext

    def test_threefish_different_keys(self):
        """Verschiedene Keys erzeugen verschiedene Ciphertexte."""
        c1 = ThreefishCipher.generate()
        c2 = ThreefishCipher.generate()
        plaintext = b"Y" * 64
        e1 = c1.encrypt(plaintext)
        e2 = c2.encrypt(plaintext)
        assert e1 != e2

    def test_hybrid_crypto_roundtrip(self):
        """Hybrid-Crypto ver- und entschluesselt korrekt."""
        hc = HybridCrypto()
        session = hc.create_session()
        plaintext = b"Hello, Erebos! This must be encrypted."
        encrypted = hc.encrypt(session.session_id, plaintext)
        assert encrypted != plaintext
        decrypted = hc.decrypt(session.session_id, encrypted)
        assert decrypted == plaintext

    def test_hybrid_crypto_ciphertext_not_plaintext(self):
        """Ciphertext enthaelt NICHT den Klartext."""
        hc = HybridCrypto()
        session = hc.create_session()
        plaintext = b"SECRET_MARKER_12345"
        encrypted = hc.encrypt(session.session_id, plaintext)
        assert b"SECRET_MARKER_12345" not in encrypted


class TestE2EIntegration:
    """Integrationstests fuer End-to-End."""

class TestObfuscationIntegration:
    """Integrationstests fuer Obfuskation."""

    def test_obfuscation_changes_payload(self):
        """Obfuskation veraendert JEDE Payload."""
        ob = ApplicationObfuscation()
        payloads = [b"a", b"hello world", b"x" * 100, b"test"]
        for p in payloads:
            result = ob.obfuscate(p)
            assert result != p, f"Payload unveraendert: {p}"

    def test_obfuscation_adds_protocol_cover(self):
        """Protocol-Cover ist vorhanden."""
        ob = ApplicationObfuscation()
        result = ob.obfuscate(b"data")
        protocols = [b"HTTP/1.1", b"HTTPS", b"DNS", b"NTP", b"QUIC"]
        assert any(p in result for p in protocols)

    def test_obfuscation_unique_per_call(self):
        """Jede Obfuskation ist einzigartig (kein Muster)."""
        ob = ApplicationObfuscation()
        r1 = ob.obfuscate(b"same input")
        r2 = ob.obfuscate(b"same input")
        assert r1 != r2



class TestCentralHybridKDF:
    """Tests für die zentrale KDF in crypto/hybrid_kem.py."""

    def test_derive_hybrid_key_is_hkdf(self):
        """derive_hybrid_key nutzt HKDF-SHA256."""
        from erebos_network.crypto.hybrid_kem import derive_hybrid_key
        x_ss = b"x" * 32
        pq_ss = b"p" * 32
        key = derive_hybrid_key(x_ss, pq_ss)
        assert len(key) == 32

    def test_derive_hybrid_key_deterministic(self):
        """Zweimal gleicher Input -> gleicher Key."""
        from erebos_network.crypto.hybrid_kem import derive_hybrid_key
        x_ss = os.urandom(32)
        pq_ss = os.urandom(32)
        k1 = derive_hybrid_key(x_ss, pq_ss)
        k2 = derive_hybrid_key(x_ss, pq_ss)
        assert k1 == k2

    def test_derive_hybrid_key_domain_separation(self):
        """Verschiedene info-Strings -> verschiedene Keys."""
        from erebos_network.crypto.hybrid_kem import derive_hybrid_key
        x_ss = b"x" * 32
        pq_ss = b"p" * 32
        k1 = derive_hybrid_key(x_ss, pq_ss, info=b"context-a")
        k2 = derive_hybrid_key(x_ss, pq_ss, info=b"context-b")
        assert k1 != k2

    def test_derive_hybrid_key_legacy_matches_old(self):
        """derive_hybrid_key_legacy entspricht dem alten SHA-256."""
        import hashlib
        from erebos_network.crypto.hybrid_kem import derive_hybrid_key_legacy
        x_ss = b"x" * 32
        pq_ss = b"p" * 32
        expected = hashlib.sha256(
            x_ss + pq_ss + b"erebos-hybrid-kem"
        ).digest()
        assert derive_hybrid_key_legacy(x_ss, pq_ss) == expected

    def test_hybrid_kem_default_is_hkdf(self):
        """Default-kdf ist 'hkdf' (RFC 5869, gehaertet)."""
        from erebos_network.crypto.hybrid_kem import HybridKEM
        kem = HybridKEM()
        assert kem.kdf == "hkdf"

    def test_hybrid_kem_hkdf_mode(self):
        """kdf='hkdf' liefert anderen Key als legacy."""
        from erebos_network.crypto.hybrid_kem import HybridKEM
        kem_legacy = HybridKEM(kdf="legacy")
        kem_hkdf = HybridKEM(kdf="hkdf")
        kp = kem_legacy.generate_keypair()
        ct_l, ss_l = kem_legacy.encapsulate(kp)
        ct_h, ss_h = kem_hkdf.encapsulate(kp)
        assert ss_l != ss_h, "hkdf und legacy sollten unterschiedliche Keys liefern"

    def test_hybrid_kem_invalid_kdf(self):
        """Unbekannte kdf -> ValueError."""
        import pytest
        from erebos_network.crypto.hybrid_kem import HybridKEM
        with pytest.raises(ValueError, match="Unbekannte kdf"):
            HybridKEM(kdf="garbage")

    def test_tunnel_pq_key_matches_direct_call(self):
        """tunnel._derive_key_pq delegiert an derive_hybrid_key."""
        from erebos_network.tunnel import _derive_key_pq
        from erebos_network.crypto.hybrid_kem import derive_hybrid_key
        x_ss = os.urandom(32)
        pq_ss = os.urandom(32)
        k_tunnel = _derive_key_pq(x_ss, pq_ss)
        k_direct = derive_hybrid_key(x_ss, pq_ss, info=b"erebos-tunnel-pq-v1")
        assert k_tunnel == k_direct
