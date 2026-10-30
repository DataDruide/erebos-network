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
import traceback
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
from .landing_pages import render_page
from .http_utils import http_response, parse_http_request
from .forum import (get_or_create_client_id, get_session_user,
                   CLIENT_COOKIE, SESSION_COOKIE, ADMIN_COOKIE,
                   IDENTITY_COOKIE)
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

from .human_validator import HumanValidator
from . import pages_human

logger = logging.getLogger(__name__)

# --- DEBUG-Handler nur für Datei (Konsole bleibt INFO) ---
import logging as _logging
from logging.handlers import RotatingFileHandler as _RotatingFileHandler
_debug_handler = _RotatingFileHandler(
    "/tmp/erebos_debug.log", maxBytes=5_000_000, backupCount=3
)
_debug_handler.setLevel(_logging.DEBUG)
_debug_handler.setFormatter(_logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
))
_logging.getLogger().addHandler(_debug_handler)
_logging.getLogger().setLevel(_logging.INFO)

_human_validator = HumanValidator()

# Maximal erlaubte HTTP-Body-Groesse (Schutz vor Memory-DoS).
MAX_HTTP_BODY_BYTES = 1024 * 1024  # 1 MB (für Uploads)

# Globales HTTP-Request-Limit (Schutz vor Flooding/DoS).
MAX_HTTP_REQUESTS_PER_WINDOW = 500
HTTP_WINDOW_SECONDS = 60


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
        dht_peers: Peers fuer die DHT-Verteilung. Jeder Eintrag ist entweder
            ein reiner Port (int/str, dann wird rendezvous_host genutzt)
            oder "host:port" (str).
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
        dht_peers: Optional[List] = None,
        ttl_seconds: int = 3600,
        http_request_handler: Optional[Callable] = None,
        bind_host: str = "127.0.0.1",
        bind_port: int = 8080,
    ):
        self.rendezvous_host = rendezvous_host
        self.rendezvous_port = rendezvous_port
        self.http_backend_host = http_backend_host
        self.http_backend_port = http_backend_port
        self.intro_points = intro_points or [
            ("peer1", "127.0.0.1:9999"),
            ("peer2", "127.0.0.1:9998"),
            ("peer3", "127.0.0.1:9997"),
        ]
        self.dht_peers = dht_peers or [9997, 9998, 9999]
        # Normalisieren: reine Ports (int/str) und "host:port"-Strings
        self._dht_targets = []
        for entry in self.dht_peers:
            if isinstance(entry, int):
                self._dht_targets.append((self.rendezvous_host, int(entry)))
            elif isinstance(entry, str) and ":" in entry:
                h, p_ = entry.rsplit(":", 1)
                self._dht_targets.append((h, int(p_)))
            else:
                self._dht_targets.append((self.rendezvous_host, int(entry)))
        self.ttl_seconds = ttl_seconds
        self.http_request_handler = http_request_handler
        self.bind_host = bind_host
        self.bind_port = bind_port

        # Wird in run() gesetzt
        self.address: Optional[str] = None
        self.private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self.public_key: Optional[bytes] = None
        self._stop_event = asyncio.Event()
        # HTTP-Request-Limit (global, pro Fenster)
        self._http_request_log = []
        self._reconnecting = False
        # B2: Health-Monitoring + Rotation
        self._intro_failures = {}  # index -> consecutive failures
        self._monitor_task = None
        self._auto_rotate_task = None
        self._known_peers = [
            ("peer1", "127.0.0.1:9999"),
            ("peer2", "127.0.0.1:9998"),
            ("peer3", "127.0.0.1:9997"),
            ("peer4", "127.0.0.1:9996"),
            ("peer5", "127.0.0.1:9995"),
        ]

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
        # B2: Health-Monitoring starten
        self._monitor_task = asyncio.create_task(self._monitor_intro_points())
        self._auto_rotate_task = asyncio.create_task(self._auto_rotate_loop())
        try:
            await self._stop_event.wait()
        finally:
            if self._monitor_task is not None:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass

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

        for host, port in self._dht_targets:
            try:
                client = ErebosTunnelClient(host=host, port=port)
                await client.connect()
                await client.send_typed(FRAME_DHT_PUT, payload)
                await client.close()
                logger.info(f"Descriptor an {host}:{port} gesendet")
            except Exception as e:
                logger.error(f"Fehler beim Senden an {host}:{port}: {e}")

        logger.info(f"Descriptor veröffentlicht in DHT (Key: {key.hex()[:16]}...)")

    async def _monitor_intro_points(self) -> None:
        """Prueft alle 30s die Intro-Points und rotiert bei Ausfall.

        Nach 3 aufeinanderfolgenden Fehlschlaegen wird der Intro-Point
        durch einen anderen verfuegbaren Peer ersetzt und der Descriptor
        neu veroeffentlicht.
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30.0)
                return  # stop_event gesetzt
            except asyncio.TimeoutError:
                pass
            for i, (peer_id, addr) in enumerate(list(self.intro_points)):
                try:
                    healthy = await self._check_intro_point(peer_id, addr)
                except Exception as e:
                    logger.debug(f"Health-Check {peer_id} fehlgeschlagen: {e}")
                    healthy = False
                if healthy:
                    self._intro_failures[i] = 0
                else:
                    failures = self._intro_failures.get(i, 0) + 1
                    self._intro_failures[i] = failures
                    logger.warning(
                        f"Intro-Point {peer_id} ({addr}) nicht erreichbar "
                        f"({failures}/3)"
                    )
                    if failures >= 3:
                        await self._rotate_intro_point(i)
                        self._intro_failures[i] = 0
                        # Descriptor neu veroeffentlichen
                        try:
                            await self._publish_descriptor()
                            logger.info(
                                f"Descriptor nach Rotation neu veroeffentlicht"
                            )
                        except Exception as e:
                            logger.error(f"Republish fehlgeschlagen: {e}")

    async def _check_intro_point(self, peer_id: str, addr: str) -> bool:
        """Prueft, ob der Peer-Port offen ist (TCP-Connect).

        Ein voller Erebos-Handshake ist fuer den Health-Check zu teuer
        und zu langsam. Ein einfacher TCP-Connect reicht: wenn der
        Port offen ist, ist der Peer erreichbar.
        """
        try:
            host, port_str = addr.split(":")
            port = int(port_str)
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=3.0
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def _rotate_intro_point(self, index: int) -> None:
        """Ersetzt den Intro-Point an `index` durch einen erreichbaren Peer."""
        current_peers = {pid for pid, _ in self.intro_points}
        for peer_id, addr in self._known_peers:
            if peer_id not in current_peers:
                # Health-Check vor Rotation: nur erreichbare Peers waehlen
                if await self._check_intro_point(peer_id, addr):
                    old = self.intro_points[index]
                    self.intro_points[index] = (peer_id, addr)
                    logger.info(
                        f"Intro-Point rotiert: {old[0]} ({old[1]}) -> "
                        f"{peer_id} ({addr})"
                    )
                    return
                else:
                    logger.debug(
                        f"Ersatz-Peer {peer_id} ({addr}) nicht erreichbar - ueberspringe"
                    )
        logger.warning(
            f"Keine Rotation moeglich: kein erreichbarer Ersatz-Peer "
            f"(aktuell: {current_peers})"
        )

    async def _start_http_backend(self) -> None:
        handler = self.http_request_handler or self._default_http_handler
        self._http_server = await asyncio.start_server(
            handler, self.bind_host, self.bind_port
        )
        logger.info(f"HTTP-Server läuft auf {self.bind_host}:{self.bind_port}")

    async def _default_http_handler(self, reader, writer) -> None:
        """HTTP-Backend: Startseite, Wiki, Forum (mit POST-Support)."""
        # 0) Globales HTTP-Request-Limit (Schutz vor Flooding/DoS)
        import time as _time
        now = _time.time()
        self._http_request_log = [
            t for t in self._http_request_log
            if now - t < HTTP_WINDOW_SECONDS
        ]
        # LAN-Whitelist: Rate-Limit für localhost/LAN überspringen
        import ipaddress as _ipaddress
        import os as _os_rl
        _lan_env = _os_rl.environ.get(
            "EREBOS_LAN_WHITELIST", "192.168.0.0/24,127.0.0.1/32,::1/128"
        )
        _is_lan = False
        try:
            # Kommagetrennte Liste von Netzwerken
            _lan_nets = [
                _ipaddress.ip_network(s.strip(), strict=False)
                for s in _lan_env.split(",")
                if s.strip()
            ]
            # Client-IP aus asyncio-Writer holen
            _peer = writer.get_extra_info("peername")
            _client_ip_str = _peer[0] if _peer else ""
            try:
                _client_ip = _ipaddress.ip_address(_client_ip_str)
                _is_lan = any(_client_ip in net for net in _lan_nets)
            except ValueError:
                pass
        except (ValueError, AttributeError):
            pass

        if not _is_lan and len(self._http_request_log) >= MAX_HTTP_REQUESTS_PER_WINDOW:
            logger.warning(
                f"HTTP-Rate-Limit erreicht "
                f"({len(self._http_request_log)}/{MAX_HTTP_REQUESTS_PER_WINDOW} "
                f"in {HTTP_WINDOW_SECONDS}s)"
            )
            body_429 = (
                "<!DOCTYPE html><html><head><title>429</title></head>"
                "<body><h1>Zu viele Anfragen</h1>"
                "<p>Bitte warte einen Moment und versuche es erneut.</p>"
                "</body></html>"
            ).encode("utf-8")
            resp = http_response(429, "text/html; charset=utf-8", body_429)
            try:
                writer.write(resp)
                await writer.drain()
            except Exception:
                pass
            finally:
                writer.close()
            return
        self._http_request_log.append(now)

        try:
            # 1) Header lesen bis "\r\n\r\n" (früh abbrechen)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < MAX_HTTP_BODY_BYTES:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
                if not chunk:
                    break
                raw += chunk
                if b"\r\n\r\n" in raw:
                    break

            method, path, headers, body = parse_http_request(raw)

            # 2) Body nachlesen, falls Content-Length groesser als bereits
            #    gelesener Body. Kurzer Timeout (1s), damit ein haengender
            #    Client den Dienst nicht blockiert.
            try:
                content_length = int(headers.get("content-length", "0") or 0)
            except ValueError:
                content_length = 0
            # Schutz vor Memory-DoS: zu grosse Bodies ablehnen (HTTP 413).
            if content_length > MAX_HTTP_BODY_BYTES:
                logger.warning(
                    f"HTTP 413: Content-Length {content_length} > "
                    f"{MAX_HTTP_BODY_BYTES}"
                )
                body_413 = (
                    "<!DOCTYPE html><html><head><title>413</title></head>"
                    "<body><h1>Anfrage zu gross</h1>"
                    "<p>Der Request-Body ueberschreitet das Limit.</p>"
                    "</body></html>"
                ).encode("utf-8")
                resp = http_response(413, "text/html; charset=utf-8", body_413)
                writer.write(resp)
                await writer.drain()
                return
            if content_length > len(body):
                need = content_length - len(body)
                while need > 0:
                    chunk = await asyncio.wait_for(
                        reader.read(min(need, 4096)), timeout=1.0
                    )
                    if not chunk:
                        break
                    body += chunk
                    need -= len(chunk)

            # Suchanfragen nicht mit Query-String loggen (Privacy)
            log_path = path
            if path.startswith("/search"):
                log_path = "/search (query redacted)"
            logger.info(f"HTTP {method} {log_path} ({len(body)}B body)")

            # 3) Query-String aus dem Original-Request extrahieren
            query = ""
            if b" " in raw:
                try:
                    request_line = raw.split(b"\r\n", 1)[0].decode("utf-8", "replace")
                    target = request_line.split(" ")[1] if " " in request_line else ""
                    if "?" in target:
                        query = target.split("?", 1)[1]
                except Exception:
                    pass

            # 4) Client-ID aus Cookie (oder neu erzeugen)
            cookie_header = headers.get("cookie", "")
            client_id, is_new_client = get_or_create_client_id(cookie_header)
            if is_new_client:
                logger.info(f"HTTP: neuer Client (cookie gesetzt: {client_id[:8]}...)")

            # 4b) Session-, Admin- und Identity-Cookie lesen (optional)
            session_token = ""
            admin_cookie = ""
            identity_uuid = ""
            for part in cookie_header.split(";"):
                part = part.strip()
                if part.startswith(SESSION_COOKIE + "="):
                    session_token = part[len(SESSION_COOKIE) + 1:].strip()
                elif part.startswith(ADMIN_COOKIE + "="):
                    admin_cookie = part[len(ADMIN_COOKIE) + 1:].strip()
                elif part.startswith(IDENTITY_COOKIE + "="):
                    identity_uuid = part[len(IDENTITY_COOKIE) + 1:].strip()
            username = get_session_user(session_token) or ""

            # --- HUMAN VALIDATOR ROUTEN ---
            if path == "/human":
                from urllib.parse import parse_qs
                q = parse_qs(query)
                stage = int(q.get("stage", ["1"])[0])
                hash_code = q.get("hash", [""])[0]
                if not hash_code and stage == 1:
                    hash_code = _human_validator.generate_stage1()
                body_out = pages_human.render_human_challenge(self.address, stage, hash_code)
                resp = http_response(200, "text/html; charset=utf-8", body_out)
                writer.write(resp)
                await writer.drain()
                return

            if path == "/human/verify" and method == "POST":
                from urllib.parse import parse_qs
                q = parse_qs(body.decode("utf-8", errors="replace"))
                stage = int(q.get("stage", ["0"])[0])
                user_input = q.get("input_code", [""])[0].strip()
                
                if stage == 1:
                    expected = q.get("expected", [""])[0]
                    if user_input == expected:
                        # Weiter zu Stufe 2
                        resp = http_response(302, "text/plain", b"", location="/human?stage=2")
                    else:
                        body_out = pages_human.render_human_challenge(self.address, 1, expected, "Falscher Code!")
                        resp = http_response(200, "text/html; charset=utf-8", body_out)
                elif stage == 2:
                    if _human_validator.check_stage2(user_input):
                        resp = http_response(302, "text/plain", b"", location="/human?stage=3")
                    else:
                        body_out = pages_human.render_human_challenge(self.address, 2, error="Falsches Lösungswort!")
                        resp = http_response(200, "text/html; charset=utf-8", body_out)
                elif stage == 3:
                    if _human_validator.check_stage3(user_input):
                        token = _human_validator.issue_human_token()
                        # Token als Cookie setzen und zur Startseite
                        set_cookie = f"erebos_human={token}; Path=/; HttpOnly; SameSite=Lax"
                        resp = http_response(302, "text/plain", b"", location="/", set_cookie=set_cookie)
                    else:
                        body_out = pages_human.render_human_challenge(self.address, 3, error="Falsches Gefühl!")
                        resp = http_response(200, "text/html; charset=utf-8", body_out)
                else:
                    resp = http_response(400, "text/plain", b"Bad Request")
                
                writer.write(resp)
                await writer.drain()
                return
            # --- ENDE HUMAN ROUTEN ---
            # 4b) CUSTOM HUMAN VALIDATOR (PoW + human.json)
            client_ip = headers.get("x-forwarded-for", "127.0.0.1").split(",")[0].strip()
            pow_nonce = headers.get("x-erebos-pow-nonce")
            pow_solution = headers.get("x-erebos-pow-solution")
            
            # Fallback: Wenn die Lösung per URL-Parameter kommt (z.B. vom Browser-Skript)
            if not pow_nonce or not pow_solution:
                from urllib.parse import parse_qs
                q = parse_qs(query)
                pow_nonce = (q.get("pow_nonce", [""])[0] or "").strip()
                pow_solution = (q.get("pow_solution", [""])[0] or "").strip()
            
            # --- 0. LOCALHOST-AUSNAHME: Nur im Dev-Modus (EREBOS_DEV_MODE=1) ---
            import os as _os
            _is_dev = _os.environ.get("EREBOS_DEV_MODE", "0") == "1"
            _is_localhost = client_ip in ("127.0.0.1", "::1", "localhost")
            if _is_dev and _is_localhost:
                logger.info(f"DEV-MODE: Localhost-Client ({client_ip}): PoW übersprungen")
                has_human_token = True
            else:
                has_human_token = False
            
            # --- 1. Prüfe Human-Token (Cookie oder URL) ---
            human_token = headers.get("x-erebos-human-token") or parse_qs(query).get("human_token", [""])[0]
            if not _is_localhost:
                has_human_token = human_token and _human_validator.verify_human_token(human_token)
            
            if has_human_token:
                logger.info("Human-Token gültig, PoW und Rätsel übersprungen.")
            elif path.startswith("/human"):
                # Der Nutzer ist gerade im Rätsel-Prozess
                pass
            elif _human_validator.check_human_json(headers):
                logger.info("Human-json-Signal erkannt, PoW übersprungen.")
            else:
                # --- 2. PoW prüfen ---
                if pow_nonce and pow_solution:
                    if not _human_validator.verify_solution(pow_nonce, pow_solution):
                        logger.warning("PoW-Validierung fehlgeschlagen.")
                        resp = http_response(403, "text/plain; charset=utf-8", b"PoW validation failed")
                        writer.write(resp)
                        await writer.drain()
                        return
                    # PoW bestanden -> jetzt Human-Token prüfen
                    if not has_human_token:
                        logger.info("PoW bestanden, aber kein Human-Token -> leite zu /human um.")
                        resp = http_response(302, "text/plain", b"", location="/human?stage=1")
                        writer.write(resp)
                        await writer.drain()
                        return
                else:
                    logger.info(f"[DEBUG] client_ip={client_ip!r}, lan_network={_human_validator.lan_network}")
                    challenge = _human_validator.issue_challenge(client_ip)
                    logger.info(f"[DEBUG] challenge={challenge}")
                    if challenge.get("skip"):
                        # LAN-Whitelist: PoW überspringen, weiter zur Antwort
                        logger.info(f"LAN-Whitelist: {client_ip} – PoW übersprungen")
                        # nichts tun, Fallthrough zur Response-Erzeugung
                    else:
                        extra_hdrs = (
                            f"X-Erebos-PoW-Nonce: {challenge['nonce']}\r\n"
                            f"X-Erebos-PoW-Difficulty: {challenge['difficulty']}\r\n"
                            f"Retry-After: 5\r\n"
                        )
                        resp = http_response(429, "text/plain; charset=utf-8", b"PoW required", extra_headers=extra_hdrs)
                        writer.write(resp)
                        await writer.drain()
                        return

            # 5) Response erzeugen
            # --- Statische Seiten + JSON + Status-API ---
            from pathlib import Path as _Path
            _static_dir = _Path(__file__).parent / "static"

            # /api/status – prüft alle Dienste auf einmal
            if path == "/api/status":
                import json as _json
                _services = [
                    "/", "/onboard", "/wiki",
                    "/search", "/forum", "/mail", "/chat", "/rules",
                ]
                _status = {}
                for _p in _services:
                    # HEAD-Request gegen uns selbst (localhost, kein Proxy)
                    try:
                        import asyncio as _asyncio
                        _reader, _writer = await _asyncio.open_connection(
                            "127.0.0.1", 8080
                        )
                        _req = (
                            f"HEAD {_p} HTTP/1.1\r\n"
                            f"Host: 127.0.0.1:8080\r\n"
                            f"Connection: close\r\n\r\n"
                        ).encode()
                        _writer.write(_req)
                        await _writer.drain()
                        _line = await _asyncio.wait_for(
                            _reader.readline(), timeout=2.0
                        )
                        _parts = _line.split()
                        _code = int(_parts[1]) if len(_parts) > 1 else 0
                        _status[_p] = {"ok": 200 <= _code < 400, "code": _code}
                        _writer.close()
                        try:
                            await _writer.wait_closed()
                        except Exception:
                            pass
                    except Exception:
                        _status[_p] = {"ok": False, "code": 0}
                body_out = _json.dumps(_status).encode("utf-8")
                resp = http_response(
                    200, "application/json; charset=utf-8", body_out
                )
                writer.write(resp)
                await writer.drain()
                return

            # /wiki-services.json – Dienste-Liste für die Wiki-Seite
            if path == "/wiki-services.json":
                _svc_path = _static_dir / "wiki-services.json"
                if _svc_path.exists():
                    body_out = _svc_path.read_bytes()
                else:
                    body_out = b"[]"
                resp = http_response(
                    200, "application/json; charset=utf-8", body_out
                )
                writer.write(resp)
                await writer.drain()
                return

            # /static/ – statische Dateien (Bilder, CSS, JS)
            if path.startswith("/static/"):
                _rel = path[len("/static/"):]
                # Pfad-Traversal verhindern
                if ".." in _rel or _rel.startswith("/"):
                    resp = http_response(400, "text/plain", b"Bad Request")
                else:
                    _file = _static_dir / _rel
                    if _file.is_file():
                        _ext = _file.suffix.lower()
                        _mime = {
                            ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
                            ".png": "image/png", ".gif": "image/gif",
                            ".svg": "image/svg+xml", ".webp": "image/webp",
                            ".css": "text/css", ".js": "application/javascript",
                            ".json": "application/json", ".html": "text/html",
                        }.get(_ext, "application/octet-stream")
                        body_out = _file.read_bytes()
                        resp = http_response(200, _mime, body_out)
                    else:
                        resp = http_response(404, "text/plain", b"Not Found")
                writer.write(resp)
                await writer.drain()
                return

            # /habibbi – Habibbi Pay Vorstellungsseite
            if path in ("/habibbi", "/habibbi/"):
                _habibbi_path = _static_dir / "habibbi.html"
                if _habibbi_path.exists():
                    body_out = _habibbi_path.read_bytes()
                else:
                    body_out = b"<h1>404 - Habibbi Pay nicht gefunden</h1>"
                resp = http_response(200, "text/html; charset=utf-8", body_out)
                writer.write(resp)
                await writer.drain()
                return

            # /wiki – statische Hidden-Wiki-Seite
            if path == "/wiki":
                _wiki_path = _static_dir / "hidden_wiki.html"
                if _wiki_path.exists():
                    body_out = _wiki_path.read_bytes()
                else:
                    body_out = b"<h1>404 - Hidden Wiki nicht gefunden</h1>"
                resp = http_response(
                    200, "text/html; charset=utf-8", body_out
                )
                writer.write(resp)
                await writer.drain()
                return

            # Alle anderen Pfade → render_page (bestehende Logik)
            body_out = render_page(
                path, self.address, f"{method} {path}",
                method=method, body=body, query=query, client_id=client_id,
                username=username, session_token=session_token,
                admin_cookie=admin_cookie, identity_uuid=identity_uuid,
                headers=headers,
            )

            # 3a) Rate-Limit-Fall (HTTP 429)
            # Format: RATE_LIMIT:<retry_after_sec>\n<html>...
            # Wenn <retry_after_sec> leer/0: kein Retry-After-Header
            if body_out.startswith(b"RATE_LIMIT:"):
                rest = body_out[len("RATE_LIMIT:"):]
                if b"\n" in rest:
                    retry_part, html_body = rest.split(b"\n", 1)
                    try:
                        retry_sec = int(retry_part.strip() or b"0")
                    except ValueError:
                        retry_sec = 0
                else:
                    retry_sec = 0
                    html_body = rest

                if not html_body:
                    html_body = (
                        "<!DOCTYPE html><html><head><title>429</title></head>"
                        "<body><h1>Zu viele Anfragen</h1>"
                        "<p>Bitte warte und versuche es erneut.</p></body></html>"
                    ).encode("utf-8")

                extra_headers = ""
                if retry_sec > 0:
                    extra_headers = f"Retry-After: {retry_sec}\r\n"

                resp = http_response(
                    429, "text/html; charset=utf-8", html_body,
                    set_cookie=(CLIENT_COOKIE + "=" + client_id + "; Path=/; HttpOnly; SameSite=Lax") if is_new_client else "",
                    extra_headers=extra_headers,
                )
                writer.write(resp)
                await writer.drain()
                return

            # 3b) Redirect-Fall (POST /forum/*/antwort)
            if body_out.startswith(b"REDIRECT:"):
                # Format: REDIRECT:/ziel  [SET_SESSION:<token>]  [CLEAR_SESSION:1]
                parts = body_out[len("REDIRECT:"):].split(b"\n")
                target = parts[0].decode("utf-8", "replace")
                extra_cookies = []
                if is_new_client:
                    extra_cookies.append(
                        CLIENT_COOKIE + "=" + client_id + "; Path=/; HttpOnly; SameSite=Lax"
                    )
                for part in parts[1:]:
                    if part.startswith(b"SET_SESSION:"):
                        token = part[len("SET_SESSION:"):].decode("utf-8", "replace")
                        extra_cookies.append(
                            SESSION_COOKIE + "=" + token + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800"
                        )
                    elif part.startswith(b"CLEAR_SESSION:"):
                        extra_cookies.append(
                            SESSION_COOKIE + "=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
                        )
                    elif part.startswith(b"SET_ADMIN:"):
                        admin_val = part[len("SET_ADMIN:"):].decode("utf-8", "replace")
                        extra_cookies.append(
                            ADMIN_COOKIE + "=" + admin_val + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=3600"
                        )
                    elif part.startswith(b"SET_IDENTITY:"):
                        ident_val = part[len("SET_IDENTITY:"):].decode("utf-8", "replace")
                        extra_cookies.append(
                            IDENTITY_COOKIE + "=" + ident_val + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000"
                        )
                resp = http_response(
                    302, "text/plain; charset=utf-8", b"Redirecting...", location=target,
                    set_cookie="\r\nSet-Cookie: ".join(extra_cookies) if extra_cookies else "",
                )
                writer.write(resp)
                await writer.drain()
                return

            # 3a2) JSON-Fall (z.B. Chat-Polling)
            # Format: JSON:<json-bytes>
            if body_out.startswith(b"JSON:"):
                payload = body_out[len("JSON:"):]
                resp = http_response(
                    200, "application/json; charset=utf-8", payload,
                    set_cookie=(CLIENT_COOKIE + "=" + client_id + "; Path=/; HttpOnly; SameSite=Lax") if is_new_client else "",
                )
                writer.write(resp)
                await writer.drain()
                return

            # 3b) Normale Seite
            resp = http_response(
                200, "text/html; charset=utf-8", body_out,
                set_cookie=(CLIENT_COOKIE + "=" + client_id + "; Path=/; HttpOnly; SameSite=Lax") if is_new_client else "",
            )
            writer.write(resp)
            await writer.drain()
        except asyncio.TimeoutError:
            logger.warning("HTTP-Timeout beim Lesen des Requests")
        except Exception as e:
            logger.error(f"HTTP-Fehler: {type(e).__name__}: {e}")
            # Stacktrace nur bei EREBOS_DEBUG=1 (OWASP A10:2025):
            # Im Produktivbetrieb keine Code-Pfade leaken.
            import os as _os
            if _os.environ.get("EREBOS_DEBUG") == "1":
                traceback.print_exc()
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
        # Cover-Traffic-Task starten (Timing-Obfuskation)
        cover_task = asyncio.create_task(self._cover_traffic_loop(client))
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
                    # Antwort vollstaendig lesen (bis EOF, max. 256 KB)
                    chunks = []
                    total = 0
                    while total < 262144:  # 256 KB Limit
                        chunk = await asyncio.wait_for(
                            http_reader.read(65536), timeout=5.0
                        )
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    http_response = b"".join(chunks)
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

    async def _cover_traffic_loop(self, client) -> None:
        """Sendet alle 5s ein FRAME_DATA mit Zufallsdaten.

        Der Client (Proxy) verwirft es (stream_id=0xFFFF).
        Erhoeht die Grundlast und erschwert Timing-Korrelation.
        """
        import os as _os
        import struct as _struct
        COVER_INTERVAL = 5.0
        COVER_SIZE = 512
        sent = 0
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=COVER_INTERVAL
                )
                return
            except asyncio.TimeoutError:
                pass
            try:
                stream_id = 0xFFFF
                payload = _os.urandom(COVER_SIZE)
                framed = _struct.pack(">H", stream_id) + bytes([0x00]) + payload
                await client.send_typed(FRAME_DATA, framed)
                sent += 1
                if sent % 4 == 1:
                    logger.info(f"Cover-Traffic gesendet ({COVER_SIZE}B, #{sent})")
            except Exception as e:
                logger.debug(f"Cover-Traffic fehlgeschlagen: {e}")
                return

    async def _auto_rotate_loop(self) -> None:
        """Hintergrund-Job: rotiert ablaufende Mail-Keys regelmaessig.

        Prueft alle ROTATE_CHECK_INTERVAL_SECONDS, ob Keys in den
        naechsten ROTATE_BEFORE_EXPIRY_DAYS Tagen ablaufen, und
        rotiert sie automatisch.

        Laeuft bis _stop_event gesetzt ist.
        """
        from .config import (
            ROTATE_CHECK_INTERVAL_SECONDS,
            ROTATE_BEFORE_EXPIRY_DAYS,
        )
        from .forum_db import auto_rotate_expiring_keys

        # Beim Start kurz warten, damit die DB und HTTP-Server initialisiert sind
        await asyncio.sleep(10)

        while not self._stop_event.is_set():
            try:
                result = auto_rotate_expiring_keys()
                if result["rotated"] or result["failed"]:
                    logger.info(
                        f"Auto-Rotation: {len(result['rotated'])} rotiert, "
                        f"{len(result['failed'])} fehlgeschlagen, "
                        f"{len(result['skipped'])} skipped "
                        f"(Schwelle: {ROTATE_BEFORE_EXPIRY_DAYS} Tage)"
                    )
            except Exception as e:
                logger.error(f"Auto-Rotation-Job fehlgeschlagen: {type(e).__name__}: {e}")

            # Warte ROTATE_CHECK_INTERVAL_SECONDS oder bis _stop_event
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=ROTATE_CHECK_INTERVAL_SECONDS,
                )
                return  # _stop_event gesetzt
            except asyncio.TimeoutError:
                continue  # normale Wartezeit abgelaufen

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
