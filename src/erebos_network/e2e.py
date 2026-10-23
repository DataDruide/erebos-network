"""Ende-zu-Ende-Verschluesselung fuer Erebos Hidden Services.

Der Client und der Hidden-Service handeln einen gemeinsamen E2E-Schluessel
aus (X25519 + ML-KEM-1024), der NICHT vom Rendezvous-Punkt (peer1)
eingesehen werden kann. peer1 leitet die E2E-verschluesselten Frames
roh weiter.

Ablauf:
    1. Client -> Hidden: E2E_KEY_INIT (X25519_pub + ML-KEM_pub)
    2. Hidden -> Client: E2E_KEY_RESP (X25519_pub + ML-KEM_ct)
    3. Beide: E2E_KEY = HKDF(X25519_shared || ML-KEM_shared, info=E2E_INFO)
    4. Ab jetzt: FRAME_DATA mit e2e_flag=0x01 (ChaCha20-Poly1305)

Frame-Format fuer E2E_KEY_INIT:
    [stream_id:2B][e2e_flag=0x02][X25519_pub:32B][ML-KEM_pub:1568B]

Frame-Format fuer E2E_KEY_RESP:
    [stream_id:2B][e2e_flag=0x03][X25519_pub:32B][ML-KEM_ct:1568B]
"""

import hashlib
import os
import struct
from typing import Optional, Tuple

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .crypto.hybrid_kem import derive_hybrid_key

try:
    import oqs
except ImportError:
    oqs = None


# e2e_flag-Werte
E2E_FLAG_CLEARTEXT = 0x00
E2E_FLAG_ENCRYPTED = 0x01
E2E_FLAG_KEY_INIT = 0x02
E2E_FLAG_KEY_RESP = 0x03

# Domain-Separation fuer den E2E-Schluessel (unabhaengig vom Tunnel)
E2E_INFO = b"erebos-e2e-key-v1"

# ML-KEM-1024 Parameter
MLKEM_ALG = "ML-KEM-1024"
MLKEM_PUB_SIZE = 1568
MLKEM_CT_SIZE = 1568
MLKEM_SHARED_SIZE = 32

X25519_KEY_SIZE = 32


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _require_oqs():
    if oqs is None:
        raise RuntimeError("liboqs-python (oqs) ist nicht installiert")
    return oqs


def _apply_padding(data: bytes) -> bytes:
    """Padding auf 256-Byte-Bloecke (analog zum Tunnel-Pfad)."""
    pad_len = (256 - (len(data) % 256)) % 256
    if pad_len == 0:
        pad_len = 256
    return data + bytes([pad_len - 1]) * pad_len


def _strip_padding(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1] + 1
    if pad_len > len(data):
        return data
    return data[:-pad_len]


# ---------------------------------------------------------------------------
# Client-Seite: Initiiert den E2E-Schluesselaustausch
# ---------------------------------------------------------------------------

class E2EClient:
    """Client-Seite des E2E-Schluesselaustauschs."""

    def __init__(self):
        self._x25519_priv: Optional[X25519PrivateKey] = None
        self._x25519_pub: Optional[bytes] = None
        self._mlkem_pub: Optional[bytes] = None
        self._mlkem_priv: Optional[bytes] = None
        self._key: Optional[bytes] = None

    def build_key_init(self) -> bytes:
        """Erzeugt die E2E_KEY_INIT-Payload (X25519_pub + ML-KEM_pub).

        Returns:
            [X25519_pub:32B][ML-KEM_pub:1568B]
        """
        self._x25519_priv = X25519PrivateKey.generate()
        self._x25519_pub = self._x25519_priv.public_key().public_bytes_raw()

        oqs = _require_oqs()
        with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
            self._mlkem_pub = kem.generate_keypair()
            self._mlkem_priv = kem.export_secret_key()

        return self._x25519_pub + self._mlkem_pub

    def process_key_response(self, payload: bytes) -> bytes:
        """Verarbeitet die E2E_KEY_RESP-Payload und leitet den E2E-Schluessel ab.

        Args:
            payload: [X25519_pub:32B][ML-KEM_ct:1568B]

        Returns:
            32-Byte E2E-Schluessel
        """
        if len(payload) != X25519_KEY_SIZE + MLKEM_CT_SIZE:
            raise ValueError(
                f"E2E_KEY_RESP muss {X25519_KEY_SIZE + MLKEM_CT_SIZE} Byte sein, "
                f"ist {len(payload)}"
            )
        peer_x25519_pub = payload[:X25519_KEY_SIZE]
        mlkem_ct = payload[X25519_KEY_SIZE:]

        # X25519-Shared
        peer_pub = X25519PublicKey.from_public_bytes(peer_x25519_pub)
        x25519_shared = self._x25519_priv.exchange(peer_pub)

        # ML-KEM-Shared
        oqs = _require_oqs()
        with oqs.KeyEncapsulation(MLKEM_ALG, secret_key=self._mlkem_priv) as kem:
            mlkem_shared = kem.decap_secret(mlkem_ct)

        # HKDF
        self._key = derive_hybrid_key(x25519_shared, mlkem_shared, info=E2E_INFO)
        return self._key

    @property
    def key(self) -> Optional[bytes]:
        return self._key

    def encrypt(self, plaintext: bytes) -> bytes:
        """Verschluesselt mit dem E2E-Schluessel (ChaCha20-Poly1305)."""
        if self._key is None:
            raise RuntimeError("E2E-Schluessel noch nicht abgeleitet")
        nonce = os.urandom(12)
        ciphertext = ChaCha20Poly1305(self._key).encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        """Entschluesselt mit dem E2E-Schluessel."""
        if self._key is None:
            raise RuntimeError("E2E-Schluessel noch nicht abgeleitet")
        nonce = data[:12]
        ciphertext = data[12:]
        return ChaCha20Poly1305(self._key).decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# Server-Seite: Antwortet auf den E2E-Schluesselaustausch
# ---------------------------------------------------------------------------

class E2EServer:
    """Server-Seite des E2E-Schluesselaustauschs."""

    def __init__(self):
        self._x25519_priv: Optional[X25519PrivateKey] = None
        self._x25519_pub: Optional[bytes] = None
        self._mlkem_ct: Optional[bytes] = None
        self._key: Optional[bytes] = None

    def process_key_init(self, payload: bytes) -> bytes:
        """Verarbeitet die E2E_KEY_INIT-Payload und baut die Antwort.

        Args:
            payload: [X25519_pub:32B][ML-KEM_pub:1568B]

        Returns:
            E2E_KEY_RESP-Payload: [X25519_pub:32B][ML-KEM_ct:1568B]
        """
        if len(payload) != X25519_KEY_SIZE + MLKEM_PUB_SIZE:
            raise ValueError(
                f"E2E_KEY_INIT muss {X25519_KEY_SIZE + MLKEM_PUB_SIZE} Byte sein, "
                f"ist {len(payload)}"
            )
        client_x25519_pub = payload[:X25519_KEY_SIZE]
        client_mlkem_pub = payload[X25519_KEY_SIZE:]

        # Eigenes X25519-Keypair
        self._x25519_priv = X25519PrivateKey.generate()
        self._x25519_pub = self._x25519_priv.public_key().public_bytes_raw()

        # X25519-Shared
        peer_pub = X25519PublicKey.from_public_bytes(client_x25519_pub)
        x25519_shared = self._x25519_priv.exchange(peer_pub)

        # ML-KEM-Encapsulation
        oqs = _require_oqs()
        with oqs.KeyEncapsulation(MLKEM_ALG) as kem:
            mlkem_ct, mlkem_shared = kem.encap_secret(client_mlkem_pub)

        self._mlkem_ct = mlkem_ct

        # HKDF
        self._key = derive_hybrid_key(x25519_shared, mlkem_shared, info=E2E_INFO)

        return self._x25519_pub + mlkem_ct

    @property
    def key(self) -> Optional[bytes]:
        return self._key

    def encrypt(self, plaintext: bytes) -> bytes:
        if self._key is None:
            raise RuntimeError("E2E-Schluessel noch nicht abgeleitet")
        nonce = os.urandom(12)
        ciphertext = ChaCha20Poly1305(self._key).encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        if self._key is None:
            raise RuntimeError("E2E-Schluessel noch nicht abgeleitet")
        nonce = data[:12]
        ciphertext = data[12:]
        return ChaCha20Poly1305(self._key).decrypt(nonce, ciphertext, None)
