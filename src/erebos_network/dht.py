"""Distributed Hash Table für Erebos Network.

Dezentrales Peer-Verzeichnis ohne zentralen Server.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


# DHT-Parameter
KEY_SIZE = 256  # Bits
K_BUCKET_SIZE = 20  # Peers pro Bucket
ALPHA = 3  # Parallelität


@dataclass
class PeerInfo:
    """Information über einen Peer."""

    peer_id: str  # Hex-String (SHA-256)
    address: str  # IP:Port
    last_seen: float = field(default_factory=time.time)
    reputation: float = 0.5  # 0.0 - 1.0
    is_online: bool = True

    @property
    def age_seconds(self) -> float:
        """Alter in Sekunden."""
        return time.time() - self.last_seen

    def is_stale(self, max_age: float = 3600) -> bool:
        """Ob Peer veraltet ist."""
        return self.age_seconds > max_age


def generate_peer_id(address: str) -> str:
    """Erzeugt eine Peer-ID aus einer Adresse.

    Args:
        address: IP:Port

    Returns:
        SHA-256 Hash als Hex-String
    """
    return hashlib.sha256(address.encode()).hexdigest()


def xor_distance(id1: str, id2: str) -> int:
    """XOR-Distanz zwischen zwei Peer-IDs.

    Args:
        id1: Erste Peer-ID (hex)
        id2: Zweite Peer-ID (hex)

    Returns:
        XOR-Distanz als Integer
    """
    return int(id1, 16) ^ int(id2, 16)


def common_prefix_length(id1: str, id2: str) -> int:
    """Gemeinsame Präfix-Länge in Bits.

    Args:
        id1: Erste Peer-ID (hex)
        id2: Zweite Peer-ID (hex)

    Returns:
        Anzahl gemeinsamer Bits
    """
    x = xor_distance(id1, id2)
    if x == 0:
        return KEY_SIZE
    return KEY_SIZE - x.bit_length()


@dataclass
class KBucket:
    """Ein K-Bucket der DHT.

    Speichert bis zu K Peers mit ähnlicher ID.
    """

    prefix: int = 0
    depth: int = 0
    peers: list[PeerInfo] = field(default_factory=list)

    @property
    def size(self) -> int:
        """Anzahl Peers."""
        return len(self.peers)

    @property
    def is_full(self) -> bool:
        """Ob Bucket voll ist."""
        return len(self.peers) >= K_BUCKET_SIZE

    def add(self, peer: PeerInfo) -> bool:
        """Fügt einen Peer hinzu.

        Returns:
            True wenn hinzugefügt, False wenn Bucket voll
        """
        for existing in self.peers:
            if existing.peer_id == peer.peer_id:
                existing.last_seen = time.time()
                return True

        if self.is_full:
            self.peers.sort(key=lambda p: p.reputation, reverse=True)
            worst = self.peers[-1]
            if peer.reputation > worst.reputation:
                self.peers.remove(worst)
                self.peers.append(peer)
                return True
            return False

        self.peers.append(peer)
        return True

    def remove(self, peer_id: str) -> bool:
        """Entfernt einen Peer."""
        for p in self.peers:
            if p.peer_id == peer_id:
                self.peers.remove(p)
                return True
        return False

    def get_stale(self, max_age: float = 3600) -> list[PeerInfo]:
        """Gibt veraltete Peers zurück."""
        return [p for p in self.peers if p.is_stale(max_age)]


class RoutingTable:
    """Routing-Tabelle der DHT.

    Organisiert Peers in K-Buckets basierend auf
    gemeinsamer Präfix-Länge mit der eigenen ID.
    """

    def __init__(self, own_id: str):
        self.own_id = own_id
        self.buckets: dict[int, KBucket] = {}
        self._initialize_buckets()

    def _initialize_buckets(self) -> None:
        """Initialisiert K-Buckets."""
        for i in range(KEY_SIZE):
            self.buckets[i] = KBucket(prefix=i, depth=i)

    def add_peer(self, peer: PeerInfo) -> bool:
        """Fügt einen Peer zur Routing-Tabelle hinzu."""
        if peer.peer_id == self.own_id:
            return False

        distance = common_prefix_length(self.own_id, peer.peer_id)
        bucket = self.buckets[distance]
        return bucket.add(peer)

    def remove_peer(self, peer_id: str) -> bool:
        """Entfernt einen Peer."""
        for bucket in self.buckets.values():
            if bucket.remove(peer_id):
                return True
        return False

    def find_closest(
        self, target_id: str, count: int = K_BUCKET_SIZE
    ) -> list[PeerInfo]:
        """Findet die nächsten Peers zu einer Ziel-ID.

        Args:
            target_id: Ziel-Peer-ID
            count: Anzahl der Peers

        Returns:
            Liste der nächsten Peers
        """
        all_peers = []
        for bucket in self.buckets.values():
            all_peers.extend(bucket.peers)

        all_peers.sort(
            key=lambda p: xor_distance(p.peer_id, target_id)
        )
        return all_peers[:count]

    @property
    def total_peers(self) -> int:
        """Gesamtzahl der Peers."""
        return sum(b.size for b in self.buckets.values())

    def to_edges(self, use_addresses: bool = False) -> list[tuple[str, str]]:
        """Exportiert Peer-Verbindungen als (src, dst)-Paare.

        Fuer Topologie-Analyse: jeder Peer in einem Bucket ist direkt
        mit dem eigenen Knoten verbunden.

        Args:
            use_addresses: True  -> IP:Port als Knoten-IDs (lesbar)
                           False -> Peer-IDs (Hex, kanonisch)

        Returns:
            Kantenliste, jede Kante ist (own_key, peer_key).
        """
        own_key = self.own_id
        edges: list[tuple[str, str]] = []
        for bucket in self.buckets.values():
            for peer in bucket.peers:
                peer_key = peer.address if use_addresses else peer.peer_id
                edges.append((own_key, peer_key))
        return edges

    def get_stats(self) -> dict:
        """Gibt Statistiken zurück."""
        return {
            "total_peers": self.total_peers,
            "buckets_used": sum(1 for b in self.buckets.values() if b.size > 0),
            "buckets_total": KEY_SIZE,
        }


# ---------------------------------------------------------------------------
# Datei-persistenter Peer-DHT-Store
# ---------------------------------------------------------------------------

class PeerDhtStore:
    """Lokaler DHT-Speicher eines Peers mit Datei-Persistenz.

    Unterstuetzt die grundlegende Dict-API (__getitem__, __setitem__,
    __contains__, get), damit er als Drop-in-Ersatz fuer ein einfaches
    `dht_store = {}` funktioniert.

    Schreibt bei jedem __setitem__ den gesamten Store atomar in eine
    JSON-Datei (tmp + rename) und laedt ihn beim Start wieder.
    """

    def __init__(self, path: str = "/tmp/erebos_peer_dht.json", verbose: bool = False):
        self.path = path
        self._store = {}
        self._verbose = verbose
        self._load()

    # -- Dict-API ----------------------------------------------------------

    def __getitem__(self, key):
        return self._store[key]

    def __setitem__(self, key, value):
        self._store[key] = value
        self._persist()

    def __contains__(self, key) -> bool:
        return key in self._store

    def __delitem__(self, key):
        del self._store[key]
        self._persist()

    def __len__(self) -> int:
        return len(self._store)

    def __iter__(self):
        return iter(self._store)

    def get(self, key, default=None):
        return self._store.get(key, default)

    def items(self):
        return self._store.items()

    def keys(self):
        return self._store.keys()

    def values(self):
        return self._store.values()

    def setdefault(self, key, default=None):
        if key not in self._store:
            self[key] = default
        return self._store[key]

    def update(self, other) -> None:
        self._store.update(other)
        self._persist()

    # -- Persistenz --------------------------------------------------------

    def _load(self) -> None:
        import json
        from pathlib import Path

        p = Path(self.path)
        if not p.exists():
            return
        try:
            raw = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError) as e:
            if self._verbose:
                print(f"PeerDhtStore: Laden fehlgeschlagen ({e}) - starte leer", flush=True)
            return

        loaded = 0
        for key_hex, entry in raw.items():
            try:
                key = bytes.fromhex(key_hex)
                # Format: {"value": ..., "ts": ...}
                value = entry.get("value", entry)
                self._store[key] = value
                loaded += 1
            except (ValueError, AttributeError):
                continue
        if self._verbose or loaded:
            print(f"PeerDhtStore: {loaded} Eintraege aus {self.path} geladen", flush=True)

    def _persist(self) -> None:
        import json
        import os
        import tempfile
        import time
        from pathlib import Path

        data = {
            key.hex(): {"value": value, "ts": time.time()}
            for key, value in self._store.items()
        }
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(p.parent), prefix=".dht_", suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, p)
        except Exception as e:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            if self._verbose:
                print(f"PeerDhtStore: Persist fehlgeschlagen: {e}", flush=True)
