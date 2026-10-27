"""Contract-Tests fuer die liboqs-python-API.

Diese Tests pruefen die API-Oberflaeche, die Erebos Network nutzt.
Wenn ein liboqs-python-Update die API bricht, schlagen diese Tests
SOFORT fehl — nicht erst beim ersten Mail-Versand.

Getestete APIs:
- oqs.Signature("ML-DSA-65"):
  - generate_keypair() -> bytes (Pubkey, 1952 Bytes)
  - export_secret_key() -> bytes (Privkey, 4032 Bytes)
  - sign(msg) -> bytes (Signatur, 3309 Bytes)
  - verify(msg, sig, pub) -> bool
- oqs.KeyEncapsulation("ML-KEM-1024"):
  - generate_keypair() -> bytes (Pubkey, 1568 Bytes)
  - export_secret_key() -> bytes (Privkey, 3168 Bytes)
"""

import oqs
import pytest


# ============================================================
# ML-DSA-65 (Signature)
# ============================================================

def test_mldsa65_sizes():
    """ML-DSA-65: NIST Level 3, 1952B Pubkey, 4032B Privkey, 3309B Sig."""
    sig = oqs.Signature("ML-DSA-65")
    pub = sig.generate_keypair()
    assert isinstance(pub, bytes), f"generate_keypair() muss bytes sein, ist {type(pub)}"
    assert len(pub) == 1952, f"Pubkey muss 1952B sein, ist {len(pub)}"
    sk = sig.export_secret_key()
    assert isinstance(sk, bytes), f"export_secret_key() muss bytes sein, ist {type(sk)}"
    assert len(sk) == 4032, f"Privkey muss 4032B sein, ist {len(sk)}"


def test_mldsa65_sign_verify():
    """ML-DSA-65: sign() + verify() Roundtrip."""
    sig = oqs.Signature("ML-DSA-65")
    pub = sig.generate_keypair()
    msg = b"erebos-contract-test"
    signature = sig.sign(msg)
    assert isinstance(signature, bytes), f"sign() muss bytes sein, ist {type(signature)}"
    assert len(signature) == 3309, f"Signatur muss 3309B sein, ist {len(signature)}"

    # verify(msg, sig, pub) -> bool
    verifier = oqs.Signature("ML-DSA-65")
    ok = verifier.verify(msg, signature, pub)
    assert ok is True, "verify() muss True zurueckgeben"


def test_mldsa65_verify_wrong_msg():
    """ML-DSA-65: verify() mit falscher Message -> False."""
    sig = oqs.Signature("ML-DSA-65")
    pub = sig.generate_keypair()
    signature = sig.sign(b"original")
    verifier = oqs.Signature("ML-DSA-65")
    assert verifier.verify(b"manipulated", signature, pub) is False


def test_mldsa65_verify_with_sk_import():
    """ML-DSA-65: Signature(secret_key=sk) importierbar."""
    sig = oqs.Signature("ML-DSA-65")
    pub = sig.generate_keypair()
    sk = sig.export_secret_key()
    # Neu importieren
    sig2 = oqs.Signature("ML-DSA-65", secret_key=sk)
    signature = sig2.sign(b"imported-sk")
    assert len(signature) == 3309
    # Verify mit pub
    assert oqs.Signature("ML-DSA-65").verify(b"imported-sk", signature, pub) is True


# ============================================================
# ML-KEM-1024 (Key Encapsulation)
# ============================================================

def test_mlkem1024_sizes():
    """ML-KEM-1024: NIST Level 5, 1568B Pubkey, 3168B Privkey."""
    kem = oqs.KeyEncapsulation("ML-KEM-1024")
    pub = kem.generate_keypair()
    assert isinstance(pub, bytes), f"generate_keypair() muss bytes sein, ist {type(pub)}"
    assert len(pub) == 1568, f"Pubkey muss 1568B sein, ist {len(pub)}"
    sk = kem.export_secret_key()
    assert isinstance(sk, bytes), f"export_secret_key() muss bytes sein, ist {type(sk)}"
    assert len(sk) == 3168, f"Privkey muss 3168B sein, ist {len(sk)}"


def test_mlkem1024_encaps_decaps():
    """ML-KEM-1024: encaps + decaps Roundtrip."""
    kem = oqs.KeyEncapsulation("ML-KEM-1024")
    pub = kem.generate_keypair()
    sk = kem.export_secret_key()

    # Encaps mit pub
    ct, ss_enc = kem.encap_secret(pub)
    assert isinstance(ct, bytes)
    assert isinstance(ss_enc, bytes) and len(ss_enc) == 32

    # Decaps mit sk
    kem2 = oqs.KeyEncapsulation("ML-KEM-1024", secret_key=sk)
    ss_dec = kem2.decap_secret(ct)
    assert ss_dec == ss_enc, "Shared Secret muss identisch sein"


def test_oqs_lists_mldsa65():
    """ML-DSA-65 ist in der liboqs-Installation verfuegbar."""
    sigs = oqs.get_enabled_sig_mechanisms()
    assert "ML-DSA-65" in sigs, f"ML-DSA-65 fehlt. Verfuegbar: {sigs}"


def test_oqs_lists_mlkem1024():
    """ML-KEM-1024 ist in der liboqs-Installation verfuegbar."""
    kems = oqs.get_enabled_kem_mechanisms()
    assert "ML-KEM-1024" in kems, f"ML-KEM-1024 fehlt. Verfuegbar: {kems}"
