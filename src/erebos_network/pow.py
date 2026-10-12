"""Proof-of-Work für Erebos Network.

Sybil-Schutz durch rechenintensive Peer-IDs.
"""

import hashlib
import time
from dataclasses import dataclass


@dataclass
class ProofOfWork:
    """Ein Proof-of-Work-Ergebnis."""

    peer_id: str
    nonce: int
    difficulty: int
    computed_at: float

    @property
    def hex_difficulty(self) -> str:
        """Difficulty als Hex-Präfix."""
        return "0" * self.difficulty


@dataclass
class PoWConfig:
    """Konfiguration für Proof-of-Work."""

    difficulty: int = 4  # Anzahl führender Nullen
    max_attempts: int = 10_000_000


def compute_pow(
    seed: str,
    difficulty: int = 4,
    max_attempts: int = 10_000_000,
) -> ProofOfWork:
    """Berechnet Proof-of-Work.

    Args:
        seed: Basis-String (z.B. Adresse)
        difficulty: Anzahl führender Nullen
        max_attempts: Maximale Versuche

    Returns:
        ProofOfWork

    Raises:
        RuntimeError: Wenn max_attempts erreicht
    """
    target_prefix = "0" * difficulty
    nonce = 0

    while nonce < max_attempts:
        candidate = f"{seed}:{nonce}"
        hash_hex = hashlib.sha256(candidate.encode()).hexdigest()

        if hash_hex.startswith(target_prefix):
            return ProofOfWork(
                peer_id=hash_hex,
                nonce=nonce,
                difficulty=difficulty,
                computed_at=time.time(),
            )

        nonce += 1

    raise RuntimeError(
        f"PoW fehlgeschlagen nach {max_attempts} Versuchen"
    )


def verify_pow(peer_id: str, seed: str, nonce: int, difficulty: int) -> bool:
    """Verifiziert Proof-of-Work.

    Args:
        peer_id: Zu verifizierende Peer-ID
        seed: Basis-String
        nonce: Nonce
        difficulty: Schwierigkeit

    Returns:
        True wenn gültig
    """
    candidate = f"{seed}:{nonce}"
    hash_hex = hashlib.sha256(candidate.encode()).hexdigest()

    if hash_hex != peer_id:
        return False

    return hash_hex.startswith("0" * difficulty)


def estimate_pow_time(difficulty: int) -> float:
    """Schätzt PoW-Zeit in Sekunden.

    Args:
        difficulty: Schwierigkeit

    Returns:
        Geschätzte Zeit in Sekunden (bei 1M Hashes/s)
    """
    expected_hashes = 16 ** difficulty
    return expected_hashes / 1_000_000
