"""Adaptive Sektoren für Erebos Network.

Sektoren definieren Anonymitäts-Level und Routing-Eigenschaften.
"""

from dataclasses import dataclass
from enum import Enum


class SectorType(Enum):
    """Verfügbare Sektor-Typen."""

    FAST = "fast"
    STANDARD = "standard"
    HIGH = "high"
    MIXNET = "mixnet"


@dataclass
class Sector:
    """Ein Sektor definiert Routing-Parameter.

    Attributes:
        name: Name des Sektors
        hops: Anzahl der Hops
        anonymity: Anonymitäts-Level (1-10)
        latency_ms: Erwartete Latenz in Millisekunden
        padding: Ob Padding verwendet wird
        delay_ms: Maximale zufällige Verzögerung pro Hop
    """

    name: str
    hops: int
    anonymity: int
    latency_ms: int
    padding: bool
    delay_ms: int

    def __str__(self) -> str:
        return (
            f"Sector({self.name}, hops={self.hops}, "
            f"anonymity={self.anonymity}/10, latency~{self.latency_ms}ms)"
        )


# Vordefinierte Sektoren
SECTORS = {
    SectorType.FAST: Sector(
        name="fast",
        hops=2,
        anonymity=4,
        latency_ms=300,
        padding=False,
        delay_ms=0,
    ),
    SectorType.STANDARD: Sector(
        name="standard",
        hops=3,
        anonymity=7,
        latency_ms=800,
        padding=True,
        delay_ms=50,
    ),
    SectorType.HIGH: Sector(
        name="high",
        hops=5,
        anonymity=9,
        latency_ms=2000,
        padding=True,
        delay_ms=200,
    ),
    SectorType.MIXNET: Sector(
        name="mixnet",
        hops=7,
        anonymity=10,
        latency_ms=5000,
        padding=True,
        delay_ms=500,
    ),
}


def get_sector(sector_type: SectorType) -> Sector:
    """Gibt einen Sektor nach Typ zurück."""
    return SECTORS[sector_type]


def list_sectors() -> list[Sector]:
    """Listet alle verfügbaren Sektoren."""
    return list(SECTORS.values())
