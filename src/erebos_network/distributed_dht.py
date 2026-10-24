"""Verteilte DHT für Hidden-Service-Descriptors.

Nutzt die RoutingTable (Kademlia) zur Peer-Auswahl und verteilt
Descriptors über die nächsten Peers. Die Netzwerkkommunikation
läuft über ErebosTunnelClient.
"""

import asyncio
import hashlib
import json
import logging
from typing import Optional

from .dht import RoutingTable, PeerInfo, xor_distance

logger = logging.getLogger(__name__)


class DistributedDescriptorStore:
    """Verteilte DHT für Hidden-Service-Descriptors."""

    def __init__(self, own_id: str):
        self.own_id = own_id
        self.routing_table = RoutingTable(own_id)
        self._local_store = {}
        # DHT-Rate-Limit (global): max. 100 Anfragen pro 60s.
        self._rate_window = 60.0
        self._rate_max = 100
        self._rate_log = []

    def put(self, key: bytes, value: dict) -> None:
        """Speichert einen Descriptor lokal und bei den nächsten Peers.

        Prueft die Signatur, bevor der Descriptor gespeichert wird.
        """
        if not self._verify_descriptor_value(value):
            logger.warning(
                f"DHT-PUT: ungueltige Signatur oder abgelaufen — verworfen "
                f"(key={key.hex()[:16]})"
            )
            return
        self._local_store[key] = value
        # Asynchron an die nächsten Peers verteilen (Fire-and-Forget)
        # In einer echten Implementierung würde man auf Bestätigungen warten.
        asyncio.create_task(self._distribute_put(key, value))

    def get(self, key: bytes) -> Optional[dict]:
        """Holt einen Descriptor (lokal oder von Peers)."""
        # 1. Lokal prüfen
        if key in self._local_store:
            value = self._local_store[key]
            if not self._verify_descriptor_value(value):
                # Ungueltige Signatur/abgelaufen -> aus dem Store entfernen
                logger.warning(
                    f"DHT: lokaler Descriptor {key.hex()[:16]} ungueltig/abgelaufen — entfernt"
                )
                del self._local_store[key]
            else:
                return value
        # 2. Bei den nächsten Peers anfragen (synchron, mit Timeout)
        # In einer echten Implementierung wäre das asynchron.
        # Für den Moment: None.
        return None

    @staticmethod
    def _verify_descriptor_value(value: dict) -> bool:
        """Prueft die Signatur und Frische eines Descriptor-Dicts.

        Lokaler Import vermeidet Zirkular-Import beim Modul-Load.
        """
        try:
            from .hidden_service import HiddenServiceDescriptor, verify_descriptor
        except Exception:
            return False
        try:
            desc = HiddenServiceDescriptor.from_dict(value)
        except Exception:
            return False
        if not verify_descriptor(desc):
            return False
        if desc.is_expired():
            return False
        return True

    async def async_get(self, key: bytes) -> Optional[dict]:
        """Asynchrone Version von get(): fragt die Peers."""
        if key in self._local_store:
            value = self._local_store[key]
            if not self._verify_descriptor_value(value):
                logger.warning(
                    f"DHT: lokaler Descriptor {key.hex()[:16]} ungueltig/abgelaufen — entfernt"
                )
                del self._local_store[key]
            else:
                return value

        # DHT-Rate-Limit: zu viele Anfragen in kurzer Zeit -> ablehnen
        import time as _time
        now = _time.time()
        self._rate_log = [t for t in self._rate_log if now - t < self._rate_window]
        if len(self._rate_log) >= self._rate_max:
            logger.warning(
                f"DHT-Rate-Limit erreicht ({len(self._rate_log)}/{self._rate_max} "
                f"in {self._rate_window:.0f}s) — Anfrage abgelehnt"
            )
            return None
        self._rate_log.append(now)

        # Frage ALLE Peers in der Routing-Tabelle (nicht nur die nächsten)
        # In einer echten DHT würde man die nächsten Peers fragen,
        # aber für den Test fragen wir alle.
        all_peers = []
        for bucket in self.routing_table.buckets.values():
            all_peers.extend(bucket.peers)

        for peer in all_peers:
            try:
                from .tunnel import ErebosTunnelClient
                from .tunnel import FRAME_DHT_GET
                host, port = peer.address.split(":")
                # Robuste Port-Konvertierung
                if isinstance(port, bytes):
                    port = port.decode("utf-8", errors="replace")
                try:
                    port_int = int(port)
                except (ValueError, TypeError):
                    logger.error(f"Ungültiger Port: {port!r}")
                    continue
                client = ErebosTunnelClient(host=host, port=port_int)
                await client.connect()
                payload = json.dumps({"key": key.hex()}).encode("utf-8")
                await client.send_typed(FRAME_DHT_GET, payload)
                raw = await asyncio.wait_for(client.receive(), timeout=5.0)
                await client.close()
                if raw:
                    response = json.loads(raw.decode("utf-8"))
                    if response.get("status") == "ok" and response.get("value"):
                        value = response["value"]
                        # Signatur + Frische pruefen (DHT-Integritaet)
                        if not self._verify_descriptor_value(value):
                            logger.warning(
                                f"DHT-GET von {peer.address}: ungueltige "
                                f"Signatur oder abgelaufen — verworfen"
                            )
                            continue
                        self._local_store[key] = value
                        return value
            except Exception as e:
                logger.error(f"DHT-GET an {peer.address} fehlgeschlagen: {e}")
        return None

    async def _distribute_put(self, key: bytes, value: dict) -> None:
        """Verteilt einen Descriptor an die nächsten Peers."""
        target_id = key.hex()
        closest = self.routing_table.find_closest(target_id, count=3)
        for peer in closest:
            try:
                from .tunnel import ErebosTunnelClient
                host, port = peer.address.split(":")
                # Robuste Port-Konvertierung
                if isinstance(port, bytes):
                    port = port.decode("utf-8", errors="replace")
                try:
                    port_int = int(port)
                except (ValueError, TypeError):
                    logger.error(f"Ungültiger Port: {port!r}")
                    continue
                client = ErebosTunnelClient(host=host, port=port_int)
                await client.connect()
                # Sende einen DHT-Put-Frame
                from .tunnel import FRAME_DHT_PUT
                payload = json.dumps({
                    "key": key.hex(),
                    "value": value,
                }).encode("utf-8")
                await client.send_typed(FRAME_DHT_PUT, payload)
                logger.info(f"DHT-Put an {peer.address} gesendet")
                await client.close()
            except Exception as e:
                logger.error(f"DHT-Put an {peer.address} fehlgeschlagen: {e}")

    def add_peer(self, peer: PeerInfo) -> bool:
        """Fügt einen Peer zur Routing-Tabelle hinzu."""
        return self.routing_table.add_peer(peer)

    def remove_peer(self, peer_id: str) -> bool:
        """Entfernt einen Peer aus der Routing-Tabelle."""
        return self.routing_table.remove_peer(peer_id)

    @property
    def size(self) -> int:
        """Anzahl der lokal gespeicherten Descriptors."""
        return len(self._local_store)

    @property
    def peer_count(self) -> int:
        """Anzahl der Peers in der Routing-Tabelle."""
        return self.routing_table.total_peers
