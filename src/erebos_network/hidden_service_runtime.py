"""Produktiver Erebos Hidden-Service mit HTTP-Datenkanal.

Der Hidden-Service registriert sich beim Rendezvous-Punkt, veröffentlicht
seinen Descriptor in der DHT und leitet eingehende HTTP-Anfragen an ein
lokales HTTP-Backend weiter (z.B. Port 8080).

Beispiel:
    runtime = HiddenServiceRuntime(
        rendezvous_host="127.0.0.1",
        rendezvous_port=9999,
        http_backend_host="127.0.0.1",
        http_backend_port=8080,
        intro_points=[("peer1", "127.0.0.1:9997")],
        dht_peers=[9997, 9998, 9999],
    )
    await runtime.run()
"""

import asyncio
import hashlib
import json
import logging
import struct
from pathlib import Path
import time
from typing import Callable, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from .hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from .tunnel import (
    ErebosTunnelClient,
    FRAME_DATA,
    FRAME_DHT_PUT,
    FRAME_RENDEZVOUS_REGISTER,
)
from .e2e import (
    E2EServer,
    E2E_FLAG_CLEARTEXT,
    E2E_FLAG_ENCRYPTED,
    E2E_FLAG_KEY_INIT,
    E2E_FLAG_KEY_RESP,
)

logger = logging.getLogger(__name__)


# HTTP-Methoden, an denen wir echte HTTP-Anfragen im Datenstrom erkennen.
HTTP_PREFIXES = (
    b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ",
    b"HTTP/",
)


class HiddenServiceRuntime:
    """Produktiver Erebos Hidden-Service.

    Parameter:
        rendezvous_host/port: Adresse des Rendezvous-Punkts, bei dem sich
            der Hidden-Service registriert.
        http_backend_host/port: Lokales HTTP-Backend, an das eingehende
            Anfragen weitergeleitet werden.
        intro_points: Liste von (peer_id, address)-Tupeln für den Descriptor.
        dht_peers: Ports der Peers, an die der Descriptor verteilt wird.
        ttl_seconds: Gültigkeit des Descriptors.
        http_request_handler: Optionales Override für das HTTP-Backend.
            Standard: TCP-Weiterleitung an http_backend_host:port.
    """

    def __init__(
        self,
        rendezvous_host: str = "127.0.0.1",
        rendezvous_port: int = 9999,
        http_backend_host: str = "127.0.0.1",
        http_backend_port: int = 8080,
        intro_points: Optional[List[Tuple[str, str]]] = None,
        dht_peers: Optional[List[int]] = None,
        ttl_seconds: int = 3600,
        http_request_handler: Optional[Callable] = None,
        bind_host: str = "127.0.0.1",
        bind_port: int = 8080,
    ):
        self.rendezvous_host = rendezvous_host
        self.rendezvous_port = rendezvous_port
        self.http_backend_host = http_backend_host
        self.http_backend_port = http_backend_port
        self.intro_points = intro_points or [("peer1", "127.0.0.1:9997")]
        self.dht_peers = dht_peers or [9997, 9998, 9999]
        self.ttl_seconds = ttl_seconds
        self.http_request_handler = http_request_handler
        self.bind_host = bind_host
        self.bind_port = bind_port

        # Wird in run() gesetzt
        self.address: Optional[str] = None
        self.private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self.public_key: Optional[bytes] = None
        self._stop_event = asyncio.Event()
        self._reconnecting = False

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Startet den Hidden-Service (blockiert bis stop() aufgerufen wird)."""
        self._generate_keys()
        await self._publish_descriptor()
        await self._start_http_backend()
        await self._register_at_rendezvous()
        logger.info(f"Hidden Service läuft: {self.address}")
        await self._stop_event.wait()

    def stop(self) -> None:
        """Beendet den Hidden-Service (run() kehrt zurück)."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Interne Schritte
    # ------------------------------------------------------------------

    def _generate_keys(self) -> None:
        """Laedt oder generiert das Ed25519-Schluesselpaar.

        Persistenz: ~/.erebos/hs_key_<bind_port>.pem. Damit bleibt die
        .erebos-Adresse ueber Neustarts stabil (wichtig fuer Clients,
        die die Adresse gecacht haben).
        """
        key_path = Path.home() / ".erebos" / f"hs_key_{self.bind_port}.pem"
        if key_path.exists():
            try:
                self.private_key = serialization.load_pem_private_key(
                    key_path.read_bytes(), password=None
                )
                self.public_key = self.private_key.public_key().public_bytes_raw()
                self.address = derive_erebos_address(self.public_key)
                logger.info(
                    f"Hidden Service Schluessel geladen: {key_path} "
                    f"(Adresse: {self.address})"
                )
                return
            except Exception as e:
                logger.warning(
                    f"Schluessel-Datei {key_path} konnte nicht geladen werden: {e} "
                    f"- generiere neu"
                )

        # Neu generieren
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key().public_bytes_raw()
        self.address = derive_erebos_address(self.public_key)

        # Speichern
        try:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(
                self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            key_path.chmod(0o600)
            logger.info(f"Hidden Service Schluessel gespeichert: {key_path}")
        except Exception as e:
            logger.warning(f"Schluessel konnte nicht gespeichert werden: {e}")

        logger.info(f"Hidden Service Adresse: {self.address}")

    async def _publish_descriptor(self) -> None:
        descriptor = HiddenServiceDescriptor(
            address=self.address,
            public_key=self.public_key,
            intro_points=[
                IntroPoint(peer_id=pid, address=addr, public_key=self.public_key)
                for pid, addr in self.intro_points
            ],
            created_at=time.time(),
            ttl_seconds=self.ttl_seconds,
        )
        sign_descriptor(descriptor, self.private_key)

        key = hashlib.sha256(self.address.encode()).digest()
        payload = json.dumps(
            {"key": key.hex(), "value": descriptor.to_dict()}
        ).encode("utf-8")

        for port in self.dht_peers:
            try:
                client = ErebosTunnelClient(host=self.rendezvous_host, port=port)
                await client.connect()
                await client.send_typed(FRAME_DHT_PUT, payload)
                await client.close()
                logger.info(f"Descriptor an Peer auf Port {port} gesendet")
            except Exception as e:
                logger.error(f"Fehler beim Senden an Port {port}: {e}")

        logger.info(f"Descriptor veröffentlicht in DHT (Key: {key.hex()[:16]}...)")

    async def _start_http_backend(self) -> None:
        handler = self.http_request_handler or self._default_http_handler
        self._http_server = await asyncio.start_server(
            handler, self.bind_host, self.bind_port
        )
        logger.info(f"HTTP-Server läuft auf {self.bind_host}:{self.bind_port}")

    async def _default_http_handler(self, reader, writer) -> None:
        """Standard-HTTP-Backend: einfache 200-OK-Antwort."""
        try:
            await reader.read(4096)
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: 22\r\n"
                b"\r\n"
                b"Hidden Service works!\n"
            )
            writer.write(response)
            await writer.drain()
        except Exception as e:
            logger.error(f"HTTP-Fehler: {e}")
        finally:
            writer.close()

    async def _register_at_rendezvous(self) -> None:
        logger.info(
            f"Registriere Hidden Service beim Rendezvous-Punkt "
            f"({self.rendezvous_host}:{self.rendezvous_port})..."
        )
        client = ErebosTunnelClient(host=self.rendezvous_host, port=self.rendezvous_port)
        await client.connect()

        reg_key = self.address[:32]
        reg_payload = json.dumps({"role": "hidden", "key": reg_key}).encode("utf-8")
        await client.send_typed(FRAME_RENDEZVOUS_REGISTER, reg_payload)
        logger.info(f"Rendezvous-Registrierung (hidden) gesendet für Key {reg_key[:16]}...")

        # keep_alive als Hintergrund-Task
        asyncio.create_task(self._keep_alive(client))

    async def _keep_alive(self, client: ErebosTunnelClient) -> None:
        """Hält die Rendezvous-Verbindung offen und verarbeitet eingehende Daten.

        ErebosTunnelClient.receive() liefert die Nutzlast OHNE Frame-Typ.
        Wir unterscheiden am Inhalt:
        - JSON-Steuerframes ({"status": ...}) -> ignorieren
        - E2E_KEY_INIT -> E2E-Schluessel aushandeln
        - HTTP-Anfragen ([stream_id][e2e_flag][GET/POST/...]) -> an HTTP-Backend
        - alles andere -> ignorieren
        """
        # E2E-Server pro stream_id
        e2e_servers = {}
        try:
            while True:
                try:
                    data = await asyncio.wait_for(client.receive(), timeout=30.0)
                except asyncio.TimeoutError:
                    continue
                if not data:
                    break

                # 1) JSON-Steuerframe?
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if isinstance(msg, dict) and "status" in msg:
                        if msg.get("status") == "ready":
                            logger.info("Rendezvous-Paar vollständig!")
                        else:
                            logger.debug(f"Steuerframe ignoriert: {msg}")
                        continue
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

                # 2) Stream-ID + e2e_flag + HTTP-Anfrage?
                if len(data) < 3:
                    logger.debug(f"Ignoriere zu kurze Daten: {len(data)}B")
                    continue
                stream_id = struct.unpack(">H", data[:2])[0]
                e2e_flag = data[2]
                payload_data = data[3:]

                # E2E_KEY_INIT: Schluessel aushandeln
                if e2e_flag == E2E_FLAG_KEY_INIT:
                    try:
                        e2e_server = E2EServer()
                        resp_payload = e2e_server.process_key_init(payload_data)
                        e2e_servers[stream_id] = e2e_server
                        framed_resp = (
                            struct.pack(">H", stream_id)
                            + bytes([E2E_FLAG_KEY_RESP])
                            + resp_payload
                        )
                        await client.send_typed(FRAME_DATA, framed_resp)
                        logger.info(
                            f"E2E-Schluessel abgeleitet (stream={stream_id})"
                        )
                    except Exception as e:
                        logger.error(f"E2E_KEY_INIT fehlgeschlagen: {e}")
                    continue

                # E2E-verschluesselte Anfrage: entschluesseln
                if e2e_flag == E2E_FLAG_ENCRYPTED:
                    e2e_server = e2e_servers.get(stream_id)
                    if e2e_server is None:
                        logger.warning(
                            f"Verschluesselte Anfrage ohne E2E-Schluessel "
                            f"(stream={stream_id}) - verworfen"
                        )
                        continue
                    try:
                        payload_data = e2e_server.decrypt(payload_data)
                        logger.info(
                            f"E2E-Anfrage entschluesselt (stream={stream_id}, "
                            f"{len(payload_data)}B)"
                        )
                    except Exception as e:
                        logger.error(
                            f"E2E-Entschluesselung fehlgeschlagen "
                            f"(stream={stream_id}): {e}"
                        )
                        continue
                elif e2e_flag != E2E_FLAG_CLEARTEXT:
                    logger.debug(f"Unbekanntes e2e_flag (stream={stream_id}): {e2e_flag:#x}")

                if not payload_data.startswith(HTTP_PREFIXES):
                    logger.debug(
                        f"Ignoriere Nicht-HTTP-Daten (stream={stream_id}): "
                        f"{payload_data[:60]!r}"
                    )
                    continue

                logger.info(
                    f"HTTP-Anfrage empfangen (stream={stream_id}, {len(payload_data)}B)"
                )
                try:
                    http_reader, http_writer = await asyncio.open_connection(
                        self.http_backend_host, self.http_backend_port
                    )
                    http_writer.write(payload_data)
                    await http_writer.drain()
                    http_response = await http_reader.read(65536)
                    http_writer.close()
                except Exception as e:
                    logger.error(f"HTTP-Backend-Fehler: {e}")
                    continue

                # Antwort verschluesseln, falls E2E-Schluessel vorhanden
                e2e_server = e2e_servers.get(stream_id)
                if e2e_server is not None:
                    try:
                        encrypted_resp = e2e_server.encrypt(http_response)
                        framed_response = (
                            struct.pack(">H", stream_id)
                            + bytes([E2E_FLAG_ENCRYPTED])
                            + encrypted_resp
                        )
                        logger.info(
                            f"E2E-Antwort verschluesselt (stream={stream_id}, "
                            f"{len(http_response)}B -> {len(encrypted_resp)}B)"
                        )
                    except Exception as e:
                        logger.error(f"E2E-Verschluesselung fehlgeschlagen: {e}")
                        framed_response = (
                            struct.pack(">H", stream_id)
                            + bytes([E2E_FLAG_CLEARTEXT])
                            + http_response
                        )
                else:
                    framed_response = (
                        struct.pack(">H", stream_id)
                        + bytes([E2E_FLAG_CLEARTEXT])
                        + http_response
                    )
                await client.send_typed(FRAME_DATA, framed_response)
                logger.info(
                    f"HTTP-Antwort gesendet (stream={stream_id}, "
                    f"{len(http_response)}B)"
                )
        except (asyncio.IncompleteReadError, ConnectionResetError):
            logger.warning("keep_alive: Rendezvous-Verbindung verloren")
            if not self._stop_event.is_set():
                asyncio.create_task(self._reconnect_loop())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"keep_alive Fehler: {type(e).__name__}: {e}")
            if not self._stop_event.is_set():
                asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Verbindet sich nach Abbruch neu mit dem Rendezvous-Punkt.

        Exponential Backoff: 1s, 2s, 4s, ... max 60s.
        Wird beendet, sobald _stop_event gesetzt ist oder die
        Registrierung erfolgreich war.
        """
        if getattr(self, "_reconnecting", False):
            logger.debug("Reconnect laeuft bereits")
            return
        self._reconnecting = True
        backoff = 1.0
        max_backoff = 60.0
        attempt = 0
        try:
            while not self._stop_event.is_set():
                attempt += 1
                logger.info(
                    f"Reconnect-Versuch {attempt} in {backoff:.0f}s "
                    f"({self.rendezvous_host}:{self.rendezvous_port})..."
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                    # _stop_event wurde gesetzt -> abbrechen
                    return
                except asyncio.TimeoutError:
                    pass
                try:
                    await self._register_at_rendezvous()
                    logger.info(f"Reconnect erfolgreich (Versuch {attempt})")
                    return
                except Exception as e:
                    logger.error(f"Reconnect fehlgeschlagen: {type(e).__name__}: {e}")
                    backoff = min(backoff * 2, max_backoff)
        finally:
            self._reconnecting = False
