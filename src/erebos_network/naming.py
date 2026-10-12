"""Erebos-Naming-System für .erebos-Domains.

Löst .erebos-Adressen zu Peer-IDs auf.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

from .dht import PeerInfo, generate_peer_id


# Regex für .erebos-Domains
EREBOS_DOMAIN_PATTERN = re.compile(
    r"^([a-z0-9][a-z0-9-]{0,62})\.erebos$", re.IGNORECASE
)


@dataclass
class DomainRecord:
    """Ein Eintrag im Naming-System."""

    name: str  # z.B. "forum"
    peer_id: str  # SHA-256 der Domain
    address: str  # IP:Port des Peers
    owner: Optional[str] = None  # Optionaler Besitzer
    created_at: float = 0.0
    ttl_seconds: int = 86400  # 24h

    @property
    def full_domain(self) -> str:
        """Vollständige Domain."""
        return f"{self.name}.erebos"


def is_erebos_domain(name: str) -> bool:
    """Prüft, ob ein Name eine .erebos-Domain ist."""
    return bool(EREBOS_DOMAIN_PATTERN.match(name))


def parse_erebos_domain(name: str) -> Optional[str]:
    """Extrahiert den Namen aus einer .erebos-Domain.

    Args:
        name: z.B. "forum.erebos"

    Returns:
        "forum" oder None
    """
    match = EREBOS_DOMAIN_PATTERN.match(name)
    if match:
        return match.group(1).lower()
    return None


def domain_to_peer_id(name: str) -> str:
    """Konvertiert eine .erebos-Domain zu einer Peer-ID.

    Args:
        name: z.B. "forum.erebos"

    Returns:
        SHA-256 Hash
    """
    clean_name = parse_erebos_domain(name) or name
    return hashlib.sha256(f"{clean_name}.erebos".encode()).hexdigest()


class NamingService:
    """Naming-Service für .erebos-Domains.

    Löst Domains zu Peers auf, dezentral über DHT.
    """

    def __init__(self):
        self._records: dict[str, DomainRecord] = {}

    def register(
        self,
        name: str,
        address: str,
        owner: Optional[str] = None,
        ttl_seconds: int = 86400,
    ) -> DomainRecord:
        """Registriert eine .erebos-Domain.

        Args:
            name: Domain-Name (ohne .erebos)
            address: IP:Port des Peers
            owner: Optionaler Besitzer
            ttl_seconds: Time-to-Live

        Returns:
            DomainRecord

        Raises:
            ValueError: Wenn Name ungültig
        """
        full = f"{name}.erebos"
        if not is_erebos_domain(full):
            raise ValueError(f"Ungültiger Domain-Name: {name}")

        import time

        record = DomainRecord(
            name=name.lower(),
            peer_id=domain_to_peer_id(full),
            address=address,
            owner=owner,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )
        self._records[record.peer_id] = record
        return record

    def resolve(self, name: str) -> Optional[DomainRecord]:
        """Löst eine .erebos-Domain auf.

        Args:
            name: z.B. "forum.erebos"

        Returns:
            DomainRecord oder None
        """
        peer_id = domain_to_peer_id(name)
        return self._records.get(peer_id)

    def unregister(self, name: str) -> bool:
        """Entfernt eine Domain."""
        peer_id = domain_to_peer_id(name)
        if peer_id in self._records:
            del self._records[peer_id]
            return True
        return False

    @property
    def count(self) -> int:
        """Anzahl registrierter Domains."""
        return len(self._records)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            "domains_registered": self.count,
            "names": [r.full_domain for r in self._records.values()],
        }
