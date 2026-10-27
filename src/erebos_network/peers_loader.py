"""Lädt die konfigurierbare Peer-Liste aus peers.json."""

import json
import logging
import os
from typing import List, Optional

from .dht import PeerInfo

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "peers.json",
)


class PeerEntry:
    """Ein Eintrag aus der Peer-Liste mit Rolle und Eigenschaften."""

    def __init__(self, name: str, address: str, peer_id: str,
                 role: str = "mix", latency_ms: int = 0, enabled: bool = True):
        self.name = name
        self.address = address
        self.peer_id = peer_id
        self.role = role
        self.latency_ms = latency_ms
        self.enabled = enabled

    def to_peer_info(self) -> PeerInfo:
        return PeerInfo(peer_id=self.peer_id, address=self.address)

    def __repr__(self):
        return (f"PeerEntry(name={self.name!r}, address={self.address!r}, "
                f"role={self.role!r}, enabled={self.enabled})")


def load_peers(path: Optional[str] = None) -> List[PeerEntry]:
    """Lädt peers.json und gibt die aktivierten PeerEntry-Objekte zurück.

    Falls die Datei fehlt oder fehlerhaft ist, wird eine leere Liste
    zurückgegeben – der Aufrufer fällt dann auf die bisherige Logik zurück.
    """
    path = path or DEFAULT_PATH
    if not os.path.isfile(path):
        logger.info("Peer-Liste nicht gefunden: %s (Fallback auf Auto-Erkennung)", path)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Peer-Liste %s konnte nicht gelesen werden: %s", path, e)
        return []

    entries: List[PeerEntry] = []
    for raw in data.get("peers", []):
        try:
            entry = PeerEntry(
                name=raw["name"],
                address=raw["address"],
                peer_id=raw["peer_id"],
                role=raw.get("role", "mix"),
                latency_ms=int(raw.get("latency_ms", 0)),
                enabled=bool(raw.get("enabled", True)),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("Ungültiger Peer-Eintrag %r: %s", raw, e)
            continue
        if entry.enabled:
            entries.append(entry)

    logger.info("Peer-Liste geladen: %d aktive Peers aus %s", len(entries), path)
    return entries


def peers_by_role(entries: List[PeerEntry], role: str) -> List[PeerEntry]:
    """Filtert die Peer-Liste nach Rolle (entry/mix/exit)."""
    return [e for e in entries if e.role == role]


def latency_for_peer(name: str, path: Optional[str] = None) -> float:
    """Gibt die konfigurierte Latenz in Sekunden für einen Peer zurück.

    Falls der Peer nicht in peers.json steht oder die Datei fehlt,
    wird 0.0 zurückgegeben.
    """
    for entry in load_peers(path):
        if entry.name == name:
            return entry.latency_ms / 1000.0
    return 0.0
