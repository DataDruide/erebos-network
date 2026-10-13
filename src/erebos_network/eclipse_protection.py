"""Eclipse-Schutz fuer Erebos Network.

Schuetzt gegen Eclipse-Angriffe durch IP/Subnetz-Diversity.

Basiert auf py-libp2p Issue #1383 (2026) und S/Kademlia.
"""

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# Subnetz-Konfiguration
SUBNET_PREFIX_V4 = 24  # /24 = 256 IPs
SUBNET_PREFIX_V6 = 48  # /48 = 2^80 IPs
MAX_PEERS_PER_SUBNET = 2


@dataclass
class EclipseProtectionConfig:
    """Konfiguration fuer Eclipse-Schutz."""

    max_peers_per_subnet: int = MAX_PEERS_PER_SUBNET
    subnet_prefix_v4: int = SUBNET_PREFIX_V4
    subnet_prefix_v6: int = SUBNET_PREFIX_V6
    exempt_loopback: bool = True
    exempt_link_local: bool = True


def extract_subnet(address: str) -> Optional[str]:
    """Extrahiert das Subnetz aus einer Adresse.

    Args:
        address: IP:Port (z.B. "127.0.0.1:8000" oder "[::1]:8000")

    Returns:
        Subnetz-String (z.B. "127.0.0.0/24") oder None
    """
    try:
        # Parse IP:Port
        if address.startswith("["):
            # IPv6: [::1]:8000
            host = address.split("]")[0][1:]
        else:
            # IPv4: 127.0.0.1:8000
            host = address.rsplit(":", 1)[0]

        ip = ipaddress.ip_address(host)

        # Loopback exempt
        if ip.is_loopback:
            return None

        # Link-local exempt
        if ip.is_link_local:
            return None

        # Subnetz berechnen
        if isinstance(ip, ipaddress.IPv4Address):
            network = ipaddress.ip_network(
                f"{ip}/{SUBNET_PREFIX_V4}", strict=False
            )
        else:
            network = ipaddress.ip_network(
                f"{ip}/{SUBNET_PREFIX_V6}", strict=False
            )

        return str(network)

    except (ValueError, IndexError) as e:
        logger.warning(f"Ungueltige Adresse: {address} ({e})")
        return None


class EclipseProtection:
    """Eclipse-Schutz durch Subnetz-Diversity.

    Verhindert, dass ein Angreifer viele Peers aus demselben
    Subnetz in die Routing-Tabelle einfuegt.
    """

    def __init__(self, config: Optional[EclipseProtectionConfig] = None):
        self.config = config or EclipseProtectionConfig()
        self._subnet_counts: dict[str, int] = {}
        self.stats = {
            "peers_accepted": 0,
            "peers_rejected_subnet": 0,
            "subnets_seen": 0,
        }

    def can_accept(self, address: str) -> bool:
        """Prueft, ob ein Peer akzeptiert werden kann.

        Args:
            address: IP:Port

        Returns:
            True wenn akzeptiert
        """
        subnet = extract_subnet(address)

        # Loopback/link-local exempt
        if subnet is None:
            self.stats["peers_accepted"] += 1
            return True

        # Subnetz-Limit pruefen
        current = self._subnet_counts.get(subnet, 0)
        if current >= self.config.max_peers_per_subnet:
            self.stats["peers_rejected_subnet"] += 1
            logger.warning(
                f"Subnetz {subnet} voll ({current}/"
                f"{self.config.max_peers_per_subnet}), "
                f"Peer {address} abgelehnt"
            )
            return False

        self._subnet_counts[subnet] = current + 1
        self.stats["peers_accepted"] += 1
        if current == 0:
            self.stats["subnets_seen"] += 1
        return True

    def remove(self, address: str) -> None:
        """Entfernt einen Peer aus der Subnetz-Zaehlung."""
        subnet = extract_subnet(address)
        if subnet and subnet in self._subnet_counts:
            self._subnet_counts[subnet] -= 1
            if self._subnet_counts[subnet] <= 0:
                del self._subnet_counts[subnet]

    def get_subnet_stats(self) -> dict:
        """Statistiken pro Subnetz."""
        return dict(self._subnet_counts)

    def get_stats(self) -> dict:
        """Gesamt-Statistiken."""
        return {
            **self.stats,
            "active_subnets": len(self._subnet_counts),
            "config": {
                "max_per_subnet": self.config.max_peers_per_subnet,
                "prefix_v4": self.config.subnet_prefix_v4,
                "prefix_v6": self.config.subnet_prefix_v6,
            },
        }
