"""Erebos verschluesselter Tunnel zu einem festen Peer.

Nutzt Ed25519 fuer Authentifizierung, X25519 fuer Schluesselaustausch
und ChaCha20-Poly1305 fuer Verschluesselung.

Frame-Typen:
  FRAME_RELAY (0x01): payload ist eine Onion-Layer, an Peer-2 weiterleiten
  FRAME_OPEN  (0x02): payload ist "host:port", Ziel oeffnen
  FRAME_DATA  (0x03): payload ist Stream-Nutzdaten
"""

import asyncio
import logging
import os
import random
import secrets
import struct
from pathlib import Path

try:
    import oqs
    HAS_LIBOQS = True
except ImportError:
    HAS_LIBOQS = False
    oqs = None
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .onion import open_layer
from .crypto.hybrid_kem import derive_hybrid_key
from .dht import PeerDhtStore

logger = logging.getLogger(__name__)

KEYS_DIR = Path(__file__).parent.parent.parent / "erebos_keys"
PEER_HOST = os.environ.get("EREBOS_PEER_HOST", "127.0.0.1")
PEER_PORT = 9999

MAX_FRAME = 65536

# Padding-Konfiguration für Größen-Obfuskation.
#   0   = Padding aus (Backward-Compat, altes Wire-Format)
#   256 = Padding auf 256-Byte-Grenzen (uniform, mehr Bandbreite)
#   1024 = Padding auf 1024-Byte-Grenzen (empfohlen)
# Kann per Environment-Variable überschrieben werden:
#   EREBOS_PADDING_BLOCK=1024 python -m erebos_network --proxy
PADDING_BLOCK_SIZE = int(os.environ.get("EREBOS_PADDING_BLOCK", "1024"))

# Frame-Typen (erstes Byte im entschluesselten Frame einer Tunnel-Session)

# Frame-Typen (erstes Byte im entschluesselten Frame einer Tunnel-Session)
FRAME_RELAY = 0x01  # payload = onion-layer, bitte weiterleiten
FRAME_OPEN  = 0x02  # payload = "host:port", Ziel oeffnen
FRAME_DATA  = 0x03  # payload = Stream-Nutzdaten
FRAME_COVER = 0x04  # payload = Cover-Traffic (verwerfen)
FRAME_COVER_ACK = 0x05  # payload = Downlink-Cover-ACK (verwerfen)
FRAME_RENDEZVOUS_REQUEST = 0x10  # payload = Rendezvous-Anfrage
FRAME_RENDEZVOUS_RESPONSE = 0x11  # payload = Rendezvous-Antwort
FRAME_DHT_PUT = 0x12  # payload = JSON {key, value}
FRAME_DHT_GET = 0x13  # payload = JSON {key}
FRAME_RENDEZVOUS_REGISTER = 0x14  # payload = Peer-ID des Hidden Service

# Handshake-Versionen (erstes Byte im Handshake-Frame)
HANDSHAKE_V1_CLASSIC = 0x01  # legacy: X25519 + Ed25519 + HKDF
HANDSHAKE_V2_HYBRID  = 0x02  # PQ: X25519 + ML-KEM-1024 + Ed25519 + HKDF

MLKEM_ALG = "ML-KEM-1024"
MLKEM_PUB_LEN = 1568
MLKEM_PRIV_LEN = 3168
MLKEM_CT_LEN = 1568
ED25519_SIG_LEN = 64
X25519_PUB_LEN = 32

# Port → Peer-Identitaet. Jeder Peer weiss anhand seines Listen-Ports,
# welcher Private-Key ihm gehoert.
PORT_TO_PEER_NAME = {
    9997: "peer3",
    9998: "peer2",
    9999: "peer1",
}


def _load_or_create_keypair(name: str):
    """Laedt ein Ed25519+X25519 Schluesselpaar (erstellt es NICHT)."""
    ed_path = KEYS_DIR / f"{name}_ed25519"
    x_path = KEYS_DIR / f"{name}_x25519"

    if not ed_path.exists() or not x_path.exists():
        raise FileNotFoundError(
            f"Schluessel fuer '{name}' fehlen in {KEYS_DIR}. "
            f"Bitte zuerst mit dem Key-Generator erstellen."
        )

    ed_priv = Ed25519PrivateKey.from_private_bytes(ed_path.read_bytes())
    x_priv = X25519PrivateKey.from_private_bytes(x_path.read_bytes())

    ed_pub = ed_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x_pub = x_priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return ed_priv, x_priv, ed_pub, x_pub


def _load_mlkem_keypair(name: str):
    """Laedt ein ML-KEM-1024 Schluesselpaar (Raw Bytes)."""
    if not HAS_LIBOQS:
        raise RuntimeError(
            "liboqs nicht verfuegbar. ML-KEM-Keys koennen nicht geladen "
            "werden. Installiere: pip install liboqs-python "
            "(plus liboqs systemweit)."
        )
    priv_path = KEYS_DIR / f"{name}_mlkem"
    pub_path = KEYS_DIR / f"{name}_mlkem.pub"

    if not priv_path.exists() or not pub_path.exists():
        raise FileNotFoundError(
            f"ML-KEM-Schluessel fuer '{name}' fehlen in {KEYS_DIR}. "
            f"Bitte zuerst mit dem Key-Generator erstellen."
        )

    priv = priv_path.read_bytes()
    pub = pub_path.read_bytes()

    if len(priv) != MLKEM_PRIV_LEN:
        raise ValueError(f"{name}_mlkem: {len(priv)} statt {MLKEM_PRIV_LEN} Byte")
    if len(pub) != MLKEM_PUB_LEN:
        raise ValueError(f"{name}_mlkem.pub: {len(pub)} statt {MLKEM_PUB_LEN} Byte")

    return priv, pub


def _derive_key(shared_secret: bytes) -> bytes:
    """Leitet einen 32-Byte-Schluessel aus dem Shared Secret ab."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"erebos-tunnel-v1",
    ).derive(shared_secret)


def _derive_key_pq(x25519_shared: bytes, mlkem_shared: bytes) -> bytes:
    """Hybrid-Schluesselableitung: X25519 + ML-KEM-1024.

    Delegiert an crypto.hybrid_kem.derive_hybrid_key (HKDF-SHA256).
    Die info-String bleibt b"erebos-tunnel-pq-v1", damit bestehende
    Tunnel-Verbindungen kompatibel bleiben.

    Wird fuer HANDSHAKE_V2_HYBRID benutzt. Der klassische _derive_key
    bleibt fuer Rueckwaertskompatibilitaet.
    """
    return derive_hybrid_key(
        x25519_shared,
        mlkem_shared,
        info=b"erebos-tunnel-pq-v1",
    )


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    return await reader.readexactly(n)


# 2-Byte-Header für padding_len (big-endian).
# Erlaubt Blockgrößen bis 65535 ohne Hack.
PADDING_HEADER_LEN = 2


def _apply_padding(data: bytes, block_size: int = None) -> bytes:
    """Wendet Padding auf Klartext an (nur wenn block_size > 0).

    Format: [2B padding_len (BE)][original data][random padding]
    Der Empfänger liest padding_len und entfernt das Padding.

    Args:
        data: Klartext
        block_size: Padding-Blockgröße. None → Modul-Global PADDING_BLOCK_SIZE.
                    0 → kein Padding (Klassisches Format).

    padding_len = 0 ist gültig (kein Padding, nur 2 Byte Header).
    """
    if block_size is None:
        block_size = PADDING_BLOCK_SIZE
    if block_size <= 0:
        return data  # Klassisches Format ohne Header
    if block_size > 65535:
        raise ValueError(f"block_size muss <= 65535 sein, ist {block_size}")

    total = PADDING_HEADER_LEN + len(data)
    # Nächste Blockgrenze >= total (mindestens 1 Block)
    padded_total = ((total + block_size - 1) // block_size) * block_size
    if padded_total < block_size:
        padded_total = block_size
    padding_len = padded_total - total
    header = padding_len.to_bytes(PADDING_HEADER_LEN, "big")
    if padding_len == 0:
        return header + data
    return header + data + os.urandom(padding_len)


def _strip_padding(padded: bytes, block_size: int = None) -> bytes:
    """Entfernt Padding. Symmetrisch zu _apply_padding.

    Args:
        padded: Padding-behafteter Klartext
        block_size: None → Modul-Global. 0 → Klassisches Format (passthrough).

    Raises:
        ValueError: bei ungültigem Header oder padding_len > Restlänge.
    """
    if block_size is None:
        block_size = PADDING_BLOCK_SIZE
    if block_size <= 0:
        return padded  # Klassisches Format
    if len(padded) < PADDING_HEADER_LEN:
        raise ValueError("Padding-Frame zu kurz")
    padding_len = int.from_bytes(padded[:PADDING_HEADER_LEN], "big")
    end = len(padded) - padding_len
    if end < PADDING_HEADER_LEN:
        raise ValueError(f"Ungültige padding_len={padding_len}")
    return padded[PADDING_HEADER_LEN:end]


async def _send_frame(writer: asyncio.StreamWriter, data: bytes):
    writer.write(struct.pack("!I", len(data)) + data)
    await writer.drain()


async def _recv_frame(reader: asyncio.StreamReader) -> bytes:
    header = await _read_exact(reader, 4)
    length = struct.unpack("!I", header)[0]
    return await _read_exact(reader, length)


class ErebosTunnelClient:
    """Verbindet sich verschluesselt mit einem festen Erebos-Peer."""

    def __init__(self, host=PEER_HOST, port=PEER_PORT):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.cipher = None

    async def connect(self, peer_name: str = None, latency_s: float = 0.0):
        """Baut den Hybrid-Handshake (X25519 + ML-KEM-1024) auf.

        peer_name: Name der Peer-Identitaet, deren statische Keys wir kennen.
                   Wenn None, wird der Name aus dem Ziel-Port via
                   PORT_TO_PEER_NAME abgeleitet (z.B. 9999 -> peer1).

        Raises:
            RuntimeError: wenn liboqs nicht verfuegbar ist.
        """
        # Guard VOR jedem Netzwerk-Zugriff (fail fast).
        if not HAS_LIBOQS:
            raise RuntimeError(
                "liboqs nicht verfuegbar. PQ-Hybrid-Handshake benoetigt "
                "liboqs-python. Installiere: pip install liboqs-python "
                "(plus liboqs systemweit)."
            )

        if peer_name is None:
            peer_name = PORT_TO_PEER_NAME.get(self.port)
            if peer_name is None:
                raise ValueError(
                    f"Kein Peer-Name fuer Port {self.port} bekannt. "
                    f"Bekannte Ports: {sorted(PORT_TO_PEER_NAME.keys())}"
                )
            logger.debug(
                f"connect(): peer_name aus Port {self.port} abgeleitet -> "
                f"{peer_name}"
            )

        if latency_s > 0:
            logger.debug(
                f"connect(): künstliche Latenz {latency_s*1000:.1f} ms vor "
                f"Verbindung zu {self.host}:{self.port}"
            )
            await asyncio.sleep(latency_s)

        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        ed_priv, x_priv, ed_pub, x_pub = _load_or_create_keypair("client")
        _, my_mlkem_pub = _load_mlkem_keypair("client")

        # Handshake-Frame bauen: version || x_pub || mlkem_pub || sig
        # Signatur deckt version || x_pub || mlkem_pub
        signed_data = (
            bytes([HANDSHAKE_V2_HYBRID]) + x_pub + my_mlkem_pub
        )
        signature = ed_priv.sign(signed_data)
        assert len(signature) == ED25519_SIG_LEN

        frame = (
            bytes([HANDSHAKE_V2_HYBRID])
            + x_pub
            + my_mlkem_pub
            + signature
        )
        logger.debug(
            f"Client sendet Handshake: version=0x{HANDSHAKE_V2_HYBRID:02x}, "
            f"x_pub={len(x_pub)}B, mlkem_pub={len(my_mlkem_pub)}B, "
            f"sig={len(signature)}B, total={len(frame)}B"
        )
        await _send_frame(self.writer, frame)

        # Peer-Antwort empfangen: version || x_pub || mlkem_ct || sig
        peer_data = await _recv_frame(self.reader)
        if len(peer_data) < 1:
            raise ValueError("Leere Peer-Handshake-Antwort")

        peer_version = peer_data[0]
        if peer_version != HANDSHAKE_V2_HYBRID:
            raise ValueError(
                f"Peer spricht Handshake-Version 0x{peer_version:02x}, "
                f"erwartet 0x{HANDSHAKE_V2_HYBRID:02x}"
            )

        peer_x_pub = peer_data[1:1 + X25519_PUB_LEN]
        peer_mlkem_ct = peer_data[
            1 + X25519_PUB_LEN : 1 + X25519_PUB_LEN + MLKEM_CT_LEN
        ]
        peer_sig = peer_data[1 + X25519_PUB_LEN + MLKEM_CT_LEN:]

        if len(peer_sig) != ED25519_SIG_LEN:
            raise ValueError(
                f"Peer-Signatur falsche Groesse: {len(peer_sig)} statt "
                f"{ED25519_SIG_LEN}"
            )

        # Peer-Signatur verifizieren
        signed_data = (
            bytes([HANDSHAKE_V2_HYBRID]) + peer_x_pub + peer_mlkem_ct
        )
        _, _, peer_ed_pub, _ = _load_or_create_keypair(peer_name)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        peer_ed = Ed25519PublicKey.from_public_bytes(peer_ed_pub)
        peer_ed.verify(peer_sig, signed_data)

        # X25519 Shared Secret
        x_shared = x_priv.exchange(
            X25519PublicKey.from_public_bytes(peer_x_pub)
        )

        # ML-KEM Decapsulate mit Client-Privkey
        my_mlkem_priv, _ = _load_mlkem_keypair("client")
        with oqs.KeyEncapsulation(MLKEM_ALG, my_mlkem_priv) as dec:
            mlkem_shared = dec.decap_secret(peer_mlkem_ct)

        # Kombinierter Session-Key
        key = _derive_key_pq(x_shared, mlkem_shared)
        self.cipher = ChaCha20Poly1305(key)
        logger.info(
            f"Verschluesselter Hybrid-Tunnel zu {self.host}:{self.port} "
            f"aufgebaut (peer={peer_name})"
        )

    async def send(self, data: bytes):
        padded = _apply_padding(data)
        nonce = os.urandom(12)
        ct = self.cipher.encrypt(nonce, padded, None)
        await _send_frame(self.writer, nonce + ct)

    async def send_typed(self, frame_type: int, payload: bytes):
        """Sendet einen typisierten Frame innerhalb der Tunnel-Session."""
        await self.send(bytes([frame_type]) + payload)

    async def receive(self) -> bytes:
        """Liest einen Datenframe; verwirft Cover + Cover-ACK.

        Datenframes haben Format [FRAME_DATA][payload]. Cover-Frames
        ([FRAME_COVER], [FRAME_COVER_ACK]) werden verworfen, ohne an
        den Aufrufer zurueckgegeben zu werden. Unbekannte Typen werden
        mit Warnung verworfen.
        """
        while True:
            frame = await _recv_frame(self.reader)
            nonce, ct = frame[:12], frame[12:]
            padded = self.cipher.decrypt(nonce, ct, None)
            if not padded:
                return b""
            data = _strip_padding(padded)
            if not data:
                continue
            frame_type = data[0]
            payload = data[1:]
            if frame_type == FRAME_DATA:
                return payload
            if frame_type == FRAME_COVER:
                logger.debug(f"Cover-Frame empfangen: {len(payload)}B (verworfen)")
                continue
            if frame_type == FRAME_COVER_ACK:
                logger.debug(f"Cover-ACK empfangen: {len(payload)}B (verworfen)")
                continue
            if frame_type == FRAME_RENDEZVOUS_REQUEST:
                logger.debug(f"Rendezvous-Request empfangen: {len(payload)}B")
                return payload
            if frame_type == FRAME_RENDEZVOUS_RESPONSE:
                logger.debug(f"Rendezvous-Response empfangen: {len(payload)}B")
                return payload
            if frame_type == FRAME_DHT_PUT:
                logger.debug(f"DHT-PUT empfangen: {len(payload)}B")
                return payload
            if frame_type == FRAME_DHT_GET:
                logger.debug(f"DHT-GET empfangen: {len(payload)}B")
                return payload
            if frame_type == FRAME_RENDEZVOUS_REGISTER:
                logger.debug(f"Rendezvous-Register empfangen: {len(payload)}B")
                return payload
            logger.warning(f"Unbekannter Frame-Typ im receive(): {frame_type:#x}")
            # Fallback: alles nach dem ersten Byte zurueckgeben
            return payload

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass

    async def send_rendezvous_request(self, request: dict) -> None:
        """Sendet eine Rendezvous-Anfrage durch den Tunnel."""
        import json
        payload = json.dumps(request).encode('utf-8')
        logger.debug(f"Sende Rendezvous-Request: {len(payload)}B an {self.host}:{self.port}")
        await self.send_typed(FRAME_RENDEZVOUS_REQUEST, payload)

    async def send_rendezvous_response(self, response: dict) -> None:
        """Sendet eine Rendezvous-Antwort durch den Tunnel."""
        import json
        payload = json.dumps(response).encode('utf-8')
        await self.send_typed(FRAME_RENDEZVOUS_RESPONSE, payload)



async def _send_cover_ack(writer, cipher, size_min: int, size_max: int) -> None:
    """Sendet einen FRAME_COVER_ACK-Frame an den Client.

    Wird optional nach echten Downlink-Frames gesendet, um die
    Uplink-Downlink-Asymmetrie zu verwischen. Der Client filtert
    FRAME_COVER_ACK in receive() automatisch heraus.
    """
    size = random.randint(size_min, size_max)
    ack_payload = secrets.token_bytes(size)
    typed = bytes([FRAME_COVER_ACK]) + ack_payload
    padded = _apply_padding(typed)
    nonce = os.urandom(12)
    ct = cipher.encrypt(nonce, padded, None)
    await _send_frame(writer, nonce + ct)


async def _handle_exit(reader, writer, cipher, host, port,
                       ack_cover: bool = False,
                       ack_delay_max_ms: int = 50,
                       ack_size_min: int = 64,
                       ack_size_max: int = 256):
    """Exit-Modus: Ziel oeffnen und Klartext-Strom durchleiten.

    Wird von Peer-2 aufgerufen. `host:port` kommt hier NICHT mehr aus
    dem ersten Frame, sondern wurde vom Aufrufer bereits aus der
    entschluesselten Onion-Layer gelesen.
    """
    remote_reader, remote_writer = await asyncio.open_connection(host, port)

    async def peer_to_target():
        while True:
            frame = await _recv_frame(reader)
            padded = cipher.decrypt(frame[:12], frame[12:], None)
            if not padded:
                break
            data = _strip_padding(padded)
            if not data:
                continue
            frame_type = data[0]
            payload = data[1:]
            if frame_type == FRAME_COVER:
                logger.debug(f"Uplink-Cover: {len(payload)}B (verworfen)")
                continue
            if frame_type == FRAME_DATA:
                logger.debug(f"Peer -> Ziel: {len(payload)}B")
                remote_writer.write(payload)
                await remote_writer.drain()
            else:
                logger.warning(f"Unbekannter Uplink-Typ: {frame_type:#x} (verworfen)")

    async def target_to_peer():
        while True:
            data = await remote_reader.read(MAX_FRAME)
            if not data:
                break
            logger.debug(f"Ziel -> Peer: {len(data)}B")
            typed = bytes([FRAME_DATA]) + data
            padded = _apply_padding(typed)
            nonce = os.urandom(12)
            ct = cipher.encrypt(nonce, padded, None)
            await _send_frame(writer, nonce + ct)

            # Optional: Cover-ACK nach echtem Downlink-Frame
            if ack_cover:
                await asyncio.sleep(random.uniform(0, ack_delay_max_ms / 1000.0))
                try:
                    await _send_cover_ack(writer, cipher, ack_size_min, ack_size_max)
                except Exception as e:
                    logger.debug(f"Cover-ACK send error: {e}")

    try:
        await asyncio.gather(
            peer_to_target(), target_to_peer(), return_exceptions=True
        )
    finally:
        remote_writer.close()
        try:
            await remote_writer.wait_closed()
        except Exception:
            pass


async def _handle_relay(reader, writer, cipher, peer_name: str, first_payload: bytes,
                        ack_cover: bool = False,
                        ack_delay_max_ms: int = 50,
                        ack_size_min: int = 64,
                        ack_size_max: int = 256):
    """Relay-Modus: entschluesselt die eingehende Onion-Layer, liest
    naechsten Hop aus dem Relay-Header und baut einen verschluesselten
    Transport-Tunnel dorthin.

    first_payload ist die GESEALTE Layer, adressiert an diesen Peer.
    Nach open_layer():
      [0]     = next_frame_type (RELAY oder OPEN)
      [1:3]   = next_port (uint16, big endian)
      [3:]    = naechste Onion-Layer (bereits gesealt fuer den Nachbar-Peer)

    Der Peer oeffnet NUR seine eigene Schicht. Die naechste Onion-Layer
    wird unveraendert weitergegeben — kein weiteres Verpacken.
    """
    from .onion import unpack_relay_header, open_layer
    from .peers_config import peer_host

    NEXT_HOST = "127.0.0.1"  # Fallback, wird nach unpack_relay_header gesetzt

    self_priv = (KEYS_DIR / f"{peer_name}_x25519").read_bytes()
    try:
        decrypted = open_layer(self_priv, first_payload)
    except Exception as e:
        logger.error(f"Relay: Onion-Layer oeffnen fehlgeschlagen: {e}")
        return

    if len(decrypted) < 3:
        logger.error("Relay: entschluesselte Layer zu kurz fuer Relay-Header")
        return

    try:
        next_frame_type, next_port = unpack_relay_header(decrypted[:3])
    except Exception as e:
        logger.error(f"Relay: Header-Fehler: {e}")
        return

    # NEXT_HOST konfigurierbar (Docker / echte Peers)
    next_peer_name = PORT_TO_PEER_NAME.get(next_port)
    if next_peer_name:
        NEXT_HOST = peer_host(next_peer_name)

    next_layer = decrypted[3:]

    logger.info(
        f"Relay: leite weiter an {NEXT_HOST}:{next_port} "
        f"(frame_type={next_frame_type:#x}, layer_len={len(next_layer)})"
    )

    tunnel2 = ErebosTunnelClient(host=NEXT_HOST, port=next_port)
    try:
        await asyncio.wait_for(tunnel2.connect(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning(
            f"Relay: Tunnel zu {NEXT_HOST}:{next_port} Timeout nach 5s "
            f"(naechster Hop nicht erreichbar)"
        )
        return
    except Exception as e:
        logger.error(f"Relay: Tunnel zu {NEXT_HOST}:{next_port} fehlgeschlagen: {e}")
        return

    try:
        await tunnel2.send_typed(next_frame_type, next_layer)

        async def client_to_next():
            try:
                while True:
                    frame = await _recv_frame(reader)
                    padded = cipher.decrypt(frame[:12], frame[12:], None)
                    if not padded:
                        break
                    data = _strip_padding(padded)
                    if not data:
                        continue
                    frame_type = data[0]
                    payload = data[1:]
                    if frame_type == FRAME_COVER:
                        logger.debug(f"Relay-Uplink-Cover: {len(payload)}B (verworfen)")
                        continue
                    await tunnel2.send_typed(frame_type, payload)
            except Exception:
                pass

        async def next_to_client():
            try:
                while True:
                    # tunnel2.receive() filtert Cover + strippt Typ bereits
                    data = await tunnel2.receive()
                    if not data:
                        break
                    typed = bytes([FRAME_DATA]) + data
                    nonce = os.urandom(12)
                    padded = _apply_padding(typed)
                    ct = cipher.encrypt(nonce, padded, None)
                    await _send_frame(writer, nonce + ct)

                    # Optional: Cover-ACK nach echtem Downlink
                    if ack_cover:
                        await asyncio.sleep(random.uniform(0, ack_delay_max_ms / 1000.0))
                        try:
                            await _send_cover_ack(writer, cipher, ack_size_min, ack_size_max)
                        except Exception as e:
                            logger.debug(f"Relay Cover-ACK send error: {e}")
            except Exception:
                pass

        await asyncio.gather(
            client_to_next(), next_to_client(), return_exceptions=True
        )
    finally:
        try:
            await tunnel2.close()
        except Exception:
            pass


async def run_peer_server(port: int = PEER_PORT,
                          ack_cover: bool = False,
                          ack_delay_max_ms: int = 50,
                          ack_size_min: int = 64,
                          ack_size_max: int = 256,
                          host: str = None):
    """Startet den Peer-Server, der Tunnel-Verbindungen annimmt.

    Args:
        host: Bind-Adresse. None -> PEER_HOST (127.0.0.1 oder aus
              EREBOS_PEER_HOST). "0.0.0.0" fuer oeffentlich erreichbare Peers.
    """
    if host is None:
        host = PEER_HOST

    peer_name = PORT_TO_PEER_NAME.get(port)
    if peer_name is None:
        raise ValueError(
            f"Port {port} ist keinem Peer-Namen zugeordnet. "
            f"Bekannte Ports: {sorted(PORT_TO_PEER_NAME.keys())}"
        )
    logger.info(f"Peer-Identitaet: {peer_name} (Port {port})")

    # Lokaler DHT-Speicher mit Datei-Persistenz pro Peer-Port.
    # Ueberlebt Peer-Neustarts (Datei bleibt in /tmp).
    dht_store = PeerDhtStore(path=f"/tmp/erebos_peer_dht_{port}.json", verbose=True)
    # Kademlia-DHT: echter verteilter Store auf UDP-Port (port + 1000).
    # Fallback: wenn kademlia_dynamic nicht verfuegbar ist, laeuft nur
    # der lokale dht_store (Verhalten wie vorher).
    kad = None
    try:
        from kademlia_dynamic import KademliaServer
        kad = KademliaServer()
        kad_port = port + 1000
        await kad.listen(port=kad_port, ip="0.0.0.0")
        logger.info(f"Kademlia-DHT laeuft auf UDP-Port {kad_port}")
        # Bootstrap: die anderen Peers als Bootstrap-Nodes
        bootstrap_nodes = []
        from .peers_config import peer_host
        for other_port in (9997, 9998, 9999):
            if other_port != port:
                other_name = PORT_TO_PEER_NAME.get(other_port)
                other_host = peer_host(other_name) if other_name else "127.0.0.1"
                bootstrap_nodes.append((other_host, other_port + 1000))
        if bootstrap_nodes:
            # Bootstrap mit Retry: die anderen Peers starten ggf. gleichzeitig.
            # Bis zu 5 Versuche mit 1s, 2s, 4s, 8s, 16s Backoff.
            async def _bootstrap_with_retry():
                backoff = 1.0
                # 10 Versuche: bei gleichzeitigem Start aller Peers
                # brauchen die anderen ggf. 20-30s, bis sie erreichbar sind.
                for attempt in range(1, 11):
                    try:
                        await kad.bootstrap(bootstrap_nodes)
                        logger.info(f"Kademlia-Bootstrap erfolgreich (Versuch {attempt}): {bootstrap_nodes}")
                        return
                    except Exception as e:
                        logger.debug(f"Kademlia-Bootstrap Versuch {attempt} fehlgeschlagen: {e}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                logger.warning(f"Kademlia-Bootstrap nach 10 Versuchen fehlgeschlagen: {bootstrap_nodes}")
            asyncio.create_task(_bootstrap_with_retry())
    except ImportError:
        logger.warning("kademlia_dynamic nicht installiert - nur lokaler DHT-Speicher")
    except Exception as e:
        logger.warning(f"Kademlia-Initialisierung fehlgeschlagen: {e} - nur lokaler DHT")

    rendezvous_pairs = {}  # Key -> {"hidden": (r,w,c), "clients": [(r,w,c), ...]}

    async def handle(reader, writer):
        logger.info("Eingehende Tunnel-Verbindung")
        try:
            client_data = await _recv_frame(reader)
            logger.debug(f"Peer empfing: {len(client_data)}B total")

            if len(client_data) < 1:
                logger.error("Peer: leere Handshake-Anfrage")
                return

            client_version = client_data[0]
            if client_version != HANDSHAKE_V2_HYBRID:
                logger.error(
                    f"Peer: Client spricht Version 0x{client_version:02x}, "
                    f"erwartet 0x{HANDSHAKE_V2_HYBRID:02x}"
                )
                return

            # Layout: version(1) || x_pub(32) || mlkem_pub(1568) || sig(64)
            client_x_pub = client_data[1:1 + X25519_PUB_LEN]
            client_mlkem_pub = client_data[
                1 + X25519_PUB_LEN : 1 + X25519_PUB_LEN + MLKEM_PUB_LEN
            ]
            client_sig = client_data[1 + X25519_PUB_LEN + MLKEM_PUB_LEN:]

            if len(client_sig) != ED25519_SIG_LEN:
                logger.error(
                    f"Peer: Client-Sig falsche Groesse: {len(client_sig)}"
                )
                return

            # Peer-Identitaet aus Port
            ed_priv, x_priv, ed_pub, x_pub = _load_or_create_keypair(peer_name)
            if not HAS_LIBOQS:
                logger.error(
                    "Peer: liboqs nicht verfuegbar, lehne Handshake ab"
                )
                return

            _, my_mlkem_pub = _load_mlkem_keypair(peer_name)
            my_mlkem_priv, _ = _load_mlkem_keypair(peer_name)

            # Client-Signatur verifizieren: deckt version || x_pub || mlkem_pub
            _, _, client_ed_pub, _ = _load_or_create_keypair("client")
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            client_ed = Ed25519PublicKey.from_public_bytes(client_ed_pub)
            signed_data = (
                bytes([HANDSHAKE_V2_HYBRID]) + client_x_pub + client_mlkem_pub
            )
            try:
                client_ed.verify(client_sig, signed_data)
                logger.debug("Peer Verifikation: GUELTIG")
            except Exception as ve:
                logger.debug(
                    f"Peer Verifikation FEHLER: {type(ve).__name__}: {ve!r}"
                )
                raise

            # X25519 Shared Secret
            x_shared = x_priv.exchange(
                X25519PublicKey.from_public_bytes(client_x_pub)
            )

            # ML-KEM Encapsulate mit Client-ML-KEM-Pubkey
            with oqs.KeyEncapsulation(MLKEM_ALG) as enc:
                mlkem_ct, mlkem_shared_enc = enc.encap_secret(client_mlkem_pub)

            # Peer-Signatur ueber version || x_pub || mlkem_ct
            peer_signed_data = (
                bytes([HANDSHAKE_V2_HYBRID]) + x_pub + mlkem_ct
            )
            signature = ed_priv.sign(peer_signed_data)
            assert len(signature) == ED25519_SIG_LEN

            # Antwort bauen und senden
            response = (
                bytes([HANDSHAKE_V2_HYBRID])
                + x_pub
                + mlkem_ct
                + signature
            )
            logger.debug(
                f"Peer sendet Handshake-Antwort: {len(response)}B "
                f"(x_pub={len(x_pub)}, mlkem_ct={len(mlkem_ct)}, "
                f"sig={len(signature)})"
            )
            await _send_frame(writer, response)

            # Kombinierter Session-Key
            key = _derive_key_pq(x_shared, mlkem_shared_enc)
            cipher = ChaCha20Poly1305(key)

            # Ersten typisierten Frame empfangen
            frame = await _recv_frame(reader)
            padded = cipher.decrypt(frame[:12], frame[12:], None)
            first = _strip_padding(padded)
            if not first:
                logger.warning("Leerer erster Frame")
                return

            frame_type = first[0]
            payload = first[1:]

            if frame_type == FRAME_COVER:
                # Cover-Traffic: verwerfen, kein Log (sonst Log-Flooding)
                logger.debug(f"Cover-Frame empfangen: {len(payload)}B (verworfen)")
                return
            if frame_type == FRAME_RELAY:
                logger.info("Relay-Modus aktiv (kein Ziel sichtbar)")
                await _handle_relay(reader, writer, cipher, peer_name, payload,
                                    ack_cover=ack_cover,
                                    ack_delay_max_ms=ack_delay_max_ms,
                                    ack_size_min=ack_size_min,
                                    ack_size_max=ack_size_max)
            elif frame_type == FRAME_OPEN:
                # payload ist die gesealte l3, adressiert an DIESEN Peer.
                # Der Klartext ist direkt "host:port" (kein Frame-Marker
                # in der Layer; der Marker kommt aus dem Transport-Frame).
                self_priv = (KEYS_DIR / f"{peer_name}_x25519").read_bytes()
                try:
                    decrypted = open_layer(self_priv, payload)
                except Exception as e:
                    logger.error(f"{peer_name}: Onion-Layer oeffnen fehlgeschlagen: {e}")
                    return
                if not decrypted:
                    logger.error(f"{peer_name}: leere innere Layer")
                    return
                target = decrypted.decode()
                host, port = target.rsplit(":", 1)
                port = int(port)
                logger.info(f"Ziel: {host}:{port}")
                await _handle_exit(reader, writer, cipher, host, port,
                                   ack_cover=ack_cover,
                                   ack_delay_max_ms=ack_delay_max_ms,
                                   ack_size_min=ack_size_min,
                                   ack_size_max=ack_size_max)
            elif frame_type == FRAME_RENDEZVOUS_REQUEST:
                logger.info(f"Rendezvous-Request empfangen ({len(payload)}B)")
                try:
                    import json as _json
                    request_data = _json.loads(payload.decode("utf-8"))
                    logger.debug(f"Rendezvous-Request Daten: {request_data}")
                    
                    # Als Hidden Service: Baue Tunnel zum Rendezvous-Punkt auf
                    # und sende eine Bestätigung.
                    from .rendezvous import RendezvousRequest, RendezvousResponse
                    from .hidden_service_server import handle_rendezvous_request
                    import time
                    
                    # Sicherstellen, dass alle Felder Strings sind
                    cek_hex = request_data.get("client_ephemeral_key", "00" * 32)
                    if isinstance(cek_hex, bytes):
                        cek_hex = cek_hex.hex()
                    if not isinstance(cek_hex, str):
                        cek_hex = "00" * 32
                    try:
                        cek = bytes.fromhex(cek_hex)
                    except (ValueError, TypeError):
                        cek = b"\x00" * 32

                    # rendezvous_address: Bytes korrekt dekodieren
                    rendezvous_addr = request_data.get("rendezvous_address", "")
                    if isinstance(rendezvous_addr, bytes):
                        rendezvous_addr = rendezvous_addr.decode("utf-8", errors="replace")
                    # Falls es immer noch ein Byte-String ist (z. B. b"..." als Text)
                    if isinstance(rendezvous_addr, str) and rendezvous_addr.startswith("b'") or rendezvous_addr.startswith('b"'):
                        # Entferne die b'...'-Verpackung
                        try:
                            rendezvous_addr = eval(rendezvous_addr).decode("utf-8", errors="replace")
                        except Exception:
                            pass
                    rendezvous_addr = str(rendezvous_addr)

                    request = RendezvousRequest(
                        client_ephemeral_key=cek,
                        rendezvous_peer_id=str(request_data.get("rendezvous_peer_id", "unknown")),
                        rendezvous_address=rendezvous_addr,
                        created_at=request_data.get("created_at", time.time()),
                    )
                    
                    async def tunnel_factory(address):
                        from .tunnel import ErebosTunnelClient
                        if isinstance(address, bytes):
                            address = address.decode("utf-8", errors="replace")
                        address = str(address)
                        if ":" not in address:
                            raise ValueError(f"Ungültige Adresse (kein Doppelpunkt): {address!r}")
                        host, port_str = address.split(":", 1)
                        try:
                            port = int(port_str)
                        except ValueError:
                            raise ValueError(f"Ungültiger Port: {port_str!r} (Adresse: {address!r})")
                        client = ErebosTunnelClient(host=host, port=port)
                        await client.connect()
                        return client
                    
                    response = await handle_rendezvous_request(request, tunnel_factory)
                    logger.info(f"Rendezvous-Verarbeitung: {response.status} - {response.message}")
                    
                    # Sende Antwort
                    import struct
                    response_payload = _json.dumps({
                        "status": response.status,
                        "message": response.message,
                        "created_at": response.created_at,
                    }).encode("utf-8")
                    typed = bytes([FRAME_RENDEZVOUS_RESPONSE]) + response_payload
                    padded = _apply_padding(typed)
                    nonce = __import__("os").urandom(12)
                    ct = cipher.encrypt(nonce, padded, None)
                    frame = struct.pack(">I", len(ct) + 12) + nonce + ct
                    writer.write(frame)
                    await writer.drain()
                    logger.debug(f"Rendezvous-Response gesendet: {len(response_payload)}B")
                    # Kurz warten, damit der Client die Antwort lesen kann
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Fehler bei Rendezvous-Request: {e}")
            elif frame_type == FRAME_DHT_PUT:
                logger.info(f"DHT-PUT empfangen ({len(payload)}B)")
                try:
                    import json as _json
                    data = _json.loads(payload.decode("utf-8"))
                    key_hex = data.get("key")
                    value = data.get("value")
                    if key_hex and value:
                        # Speichere lokal (in einer echten DHT: verteile weiter)
                        
                            
                        dht_store[bytes.fromhex(key_hex)] = value
                        # Zusaetzlich in Kademlia verteilen (falls verfuegbar)
                        if kad is not None:
                            try:
                                await kad.set(key_hex, _json.dumps(value))
                                logger.info(f"DHT-PUT an Kademlia verteilt: {key_hex[:16]}...")
                            except Exception as e:
                                logger.warning(f"Kademlia-PUT fehlgeschlagen: {e}")
                        logger.info(f"DHT-PUT gespeichert: {key_hex[:16]}...")
                        # Sende Bestätigung
                        import struct
                        ack_payload = _json.dumps({"status": "ok", "key": key_hex}).encode("utf-8")
                        typed = bytes([FRAME_DHT_PUT]) + ack_payload
                        padded = _apply_padding(typed)
                        nonce = __import__("os").urandom(12)
                        ct = cipher.encrypt(nonce, padded, None)
                        frame = struct.pack(">I", len(ct) + 12) + nonce + ct
                        writer.write(frame)
                        await writer.drain()
                except Exception as e:
                    logger.error(f"Fehler bei DHT-PUT: {e}")
            elif frame_type == FRAME_RENDEZVOUS_REGISTER:
                logger.info(f"Rendezvous-Registrierung empfangen ({len(payload)}B)")
                role = None
                key = None
                try:
                    # 2-Hop-Onion: Pruefe, ob payload eine Onion-Schicht ist
                    # (dann ist der eigentliche Payload verschluesselt).
                    from .onion import open_layer
                    try:
                        self_priv = (KEYS_DIR / f"{peer_name}_x25519").read_bytes()
                        decrypted = open_layer(self_priv, payload)
                        payload = decrypted
                        logger.info(
                            f"Rendezvous-Registrierung: Onion-Schicht entschluesselt "
                            f"({len(payload)}B)"
                        )
                    except Exception:
                        # Keine Onion-Schicht -> payload bleibt Klartext.
                        pass

                    import json as _json
                    data = _json.loads(payload.decode("utf-8"))
                    role = data.get("role")
                    key = data.get("key")
                    if role and key:
                        if key not in rendezvous_pairs:
                            rendezvous_pairs[key] = {}
                        # WICHTIG: Cipher mit speichern, damit FRAME_DATA mit dem
                        # richtigen Schluessel der Ziel-Verbindung verschluesselt wird.
                        # 'hidden' ist eindeutig (ein Hidden-Service pro Key),
                        # 'clients' ist eine Liste (mehrere Clients pro Key moeglich).
                        if role == "hidden":
                            rendezvous_pairs[key]["hidden"] = (reader, writer, cipher)
                        else:
                            rendezvous_pairs[key].setdefault("clients", []).append(
                                (reader, writer, cipher)
                            )
                        # streams: stream_id -> {"client": (reader, writer, cipher)}
                        rendezvous_pairs[key].setdefault("streams", {})
                        logger.info(f"Rendezvous-Registrierung: {role} für Key {key[:16]}...")
                        # Bestätigung senden
                        import struct
                        ack = _json.dumps({"status": "ok", "role": role}).encode("utf-8")
                        typed = bytes([FRAME_RENDEZVOUS_REGISTER]) + ack
                        padded = _apply_padding(typed)
                        nonce = __import__("os").urandom(12)
                        ct = cipher.encrypt(nonce, padded, None)
                        frame = struct.pack(">I", len(ct) + 12) + nonce + ct
                        writer.write(frame)
                        await writer.drain()

                        # Sende 'ready' SOFORT an den, der sich gerade registriert hat
                        import struct
                        ready_msg = _json.dumps({"status": "ready"}).encode("utf-8")
                        typed = bytes([FRAME_RENDEZVOUS_REGISTER]) + ready_msg
                        padded = _apply_padding(typed)
                        nonce = __import__("os").urandom(12)
                        ct = cipher.encrypt(nonce, padded, None)
                        frame = struct.pack(">I", len(ct) + 12) + nonce + ct
                        writer.write(frame)
                        await writer.drain()
                        logger.info(f"'ready' an {role} gesendet")

                        # Prüfe, ob beide Rollen da sind
                        pair = rendezvous_pairs[key]
                        if "hidden" in pair and pair.get("clients"):
                            logger.info(f"Rendezvous-Paar vollständig für Key {key[:16]}...")

                            # Bestaetigung NUR an die ANDERE Seite senden.
                            # Die aktuell registrierende Verbindung hat ihren
                            # 'ready'-Frame bereits oben erhalten; ein zweiter
                            # 'ready' wuerde sie verwirren.
                            def _other_entries(pair_dict, current_role):
                                entries = []
                                if current_role != "hidden" and "hidden" in pair_dict:
                                    entries.append(("hidden", pair_dict["hidden"]))
                                if current_role != "client":
                                    for idx, c in enumerate(pair_dict.get("clients", [])):
                                        entries.append((f"client[{idx}]", c))
                                return entries

                            for role_name, entry in _other_entries(pair, role):
                                try:
                                    r, w, target_cipher = entry
                                    typed_ready = bytes([FRAME_RENDEZVOUS_REGISTER]) + ready_msg
                                    padded_ready = _apply_padding(typed_ready)
                                    nonce_ready = __import__("os").urandom(12)
                                    ct_ready = target_cipher.encrypt(nonce_ready, padded_ready, None)
                                    frame_ready = struct.pack(">I", len(ct_ready) + 12) + nonce_ready + ct_ready
                                    w.write(frame_ready)
                                    await w.drain()
                                except Exception as e:
                                    logger.error(f"Fehler beim Senden der Bestaetigung an {role_name}: {e}")

                        # Endlosschleife laeuft IMMER (für hidden UND client).
                        # 'pair' ist eine Referenz auf das Dict in rendezvous_pairs[key]
                        # und sieht daher auch Rollen, die erst spaeter hinzukommen.
                        logger.info("Rendezvous-Verbindung bleibt offen (warte auf Frames)")
                        while True:
                            try:
                                frame_in = await asyncio.wait_for(_recv_frame(reader), timeout=60.0)
                                if not frame_in:
                                    break
                                padded_in = cipher.decrypt(frame_in[:12], frame_in[12:], None)
                                data_in = _strip_padding(padded_in)
                                if not data_in:
                                    continue
                                ft = data_in[0]
                                pl = data_in[1:]
                                if ft == FRAME_DATA:
                                    # Rendezvous-Pfad: pl = [stream_id:2B][e2e_flag:1B][nutzdaten]
                                    if len(pl) < 3:
                                        logger.warning(f"FRAME_DATA zu kurz ({len(pl)}B) - ignoriert")
                                        continue
                                    stream_id = struct.unpack(">H", pl[:2])[0]
                                    e2e_flag = pl[2]
                                    payload_data = pl[3:]
                                    if e2e_flag != 0x00:
                                        logger.debug(f"FRAME_DATA (stream={stream_id}) mit e2e_flag={e2e_flag:#x}")

                                    streams = pair.setdefault("streams", {})
                                    hidden_entry = pair.get("hidden")

                                    # Bin ich der Hidden-Service oder ein Client?
                                    is_hidden = hidden_entry is not None and writer is hidden_entry[1]

                                    if is_hidden:
                                        # Antwort vom Hidden-Service -> an den Client,
                                        # der zu dieser Stream-ID gehoert.
                                        stream_info = streams.get(stream_id)
                                        if stream_info is None:
                                            logger.warning(
                                                f"FRAME_DATA (stream={stream_id}) vom Hidden-Service, "
                                                f"aber kein Client fuer diesen Stream registriert - verworfen"
                                            )
                                            continue
                                        targets = [(
                                            f"client(stream={stream_id})",
                                            stream_info["client"],
                                        )]
                                    else:
                                        # Anfrage von einem Client -> Stream diesem Client zuordnen
                                        streams[stream_id] = {"client": (reader, writer, cipher)}
                                        if hidden_entry is None:
                                            logger.warning(
                                                f"FRAME_DATA (stream={stream_id}) von Client, "
                                                f"aber kein Hidden-Service registriert - verworfen"
                                            )
                                            continue
                                        targets = [("hidden", hidden_entry)]

                                    logger.info(
                                        f"FRAME_DATA empfangen (stream={stream_id}, {len(payload_data)}B, "
                                        f"from={'hidden' if is_hidden else 'client'}) - leite an "
                                        f"{', '.join(name for name, _ in targets)}"
                                    )

                                    for role_name, entry in targets:
                                        r, w, target_cipher = entry
                                        if w is writer:
                                            continue
                                        try:
                                            forward_payload = pl  # stream_id + payload_data
                                            typed_out = bytes([FRAME_DATA]) + forward_payload
                                            padded_out = _apply_padding(typed_out)
                                            nonce_out = __import__("os").urandom(12)
                                            ct_out = target_cipher.encrypt(nonce_out, padded_out, None)
                                            frame_out = struct.pack(">I", len(ct_out) + 12) + nonce_out + ct_out
                                            w.write(frame_out)
                                            await w.drain()
                                        except Exception as e:
                                            logger.error(f"Weiterleitungsfehler an {role_name}: {e}")
                                else:
                                    logger.debug(f"Frame {ft:#x} empfangen")
                            except asyncio.TimeoutError:
                                continue
                            except (asyncio.IncompleteReadError, ConnectionResetError):
                                logger.debug("Rendezvous-Loop: Verbindung regulaer beendet")
                                break
                            except Exception as e:
                                logger.error(f"Fehler in Rendezvous-Loop: {e}")
                                break
                except Exception as e:
                    logger.error(f"Fehler bei Rendezvous-Registrierung: {e}")
                finally:
                    # Cleanup: Diese Verbindung aus rendezvous_pairs entfernen —
                    # aber NUR, wenn sie tatsaechlich die registrierte ist.
                    # (handle_rendezvous_request baut zusätzliche Tunnel zu peer1 auf,
                    #  die sich NICHT als 'hidden' registrieren und nach dem Response
                    #  wieder enden — die duerfen das Paar nicht aufloesen.)
                    #
                    # WICHTIG: pair["hidden"] bleibt erhalten, solange die
                    # Hidden-Verbindung lebt. Nur wenn der letzte Client geht,
                    # bleibt pair["hidden"] bestehen (hidden ist noch aktiv).
                    # Erst wenn die HIDDEN-Verbindung endet, wird das Paar entfernt.
                    if role and key and key in rendezvous_pairs:
                        try:
                            pair = rendezvous_pairs[key]
                            if role == "hidden":
                                hidden_entry = pair.get("hidden")
                                if hidden_entry is not None and hidden_entry[1] is writer:
                                    # Dies ist die registrierte Hidden-Verbindung -> aufloesen
                                    rendezvous_pairs.pop(key, None)
                                    logger.info(
                                        f"Rendezvous-Paar für Key {key[:16]}... "
                                        f"aufgeloest (hidden getrennt)"
                                    )
                                else:
                                    # Nicht die registrierte Hidden-Verbindung -> ignorieren
                                    pass
                            else:
                                # Client weg -> nur entfernen, wenn dieser writer registriert ist
                                before = len(pair.get("clients", []))
                                pair["clients"] = [
                                    c for c in pair.get("clients", [])
                                    if c[1] is not writer
                                ]
                                after = len(pair["clients"])
                                if before == after:
                                    # Dieser writer war gar nicht registriert -> ignorieren
                                    pass
                                else:
                                    # streams bereinigen, die auf diesen Client zeigen
                                    streams = pair.get("streams", {})
                                    to_remove = [
                                        sid for sid, info in streams.items()
                                        if info.get("client", (None, None, None))[1] is writer
                                    ]
                                    for sid in to_remove:
                                        streams.pop(sid, None)
                                    if not pair["clients"]:
                                        # WICHTIG: pair NICHT entfernen, solange hidden aktiv ist!
                                        # Nur wenn hidden auch weg ist (was hier nicht der Fall ist,
                                        # weil hidden separat bereinigt wird), darf das Paar weg.
                                        if "hidden" not in pair:
                                            rendezvous_pairs.pop(key, None)
                                            logger.info(
                                                f"Rendezvous-Paar für Key {key[:16]}... "
                                                f"aufgeloest (letzter client getrennt)"
                                            )
                                        else:
                                            logger.info(
                                                f"Letzter Client aus Rendezvous-Paar {key[:16]}... "
                                                f"entfernt (hidden bleibt aktiv, {len(to_remove)} streams bereinigt)"
                                            )
                                    else:
                                        logger.info(
                                            f"Client aus Rendezvous-Paar {key[:16]}... entfernt "
                                            f"({after} verbleibend, {len(to_remove)} streams bereinigt)"
                                        )
                        except Exception as cleanup_err:
                            logger.error(f"Fehler beim Rendezvous-Cleanup: {cleanup_err}")
            elif frame_type == FRAME_DATA:
                logger.info(f"FRAME_DATA empfangen ({len(payload)}B)")
                # Leite an die Rendezvous-Verbindung weiter (falls vorhanden)
                if rendezvous_connections:
                    for peer_id, (r, w) in rendezvous_connections.items():
                        try:
                            w.write(payload)
                            await w.drain()
                            logger.debug(f"Daten an {peer_id} weitergeleitet")
                        except Exception as e:
                            logger.error(f"Fehler beim Weiterleiten an {peer_id}: {e}")
                else:
                    logger.warning("Keine Rendezvous-Verbindung vorhanden")
            elif frame_type == FRAME_DHT_GET:
                logger.info(f"DHT-GET empfangen ({len(payload)}B)")
                try:
                    import json as _json
                    data = _json.loads(payload.decode("utf-8"))
                    key_hex = data.get("key")
                    if key_hex:
                        value = dht_store.get(bytes.fromhex(key_hex))
                        # Fallback: Kademlia fragen, wenn lokal nicht vorhanden
                        if value is None and kad is not None:
                            try:
                                kad_value = await kad.get(key_hex)
                                if kad_value is not None:
                                    import json as _json2
                                    value = _json2.loads(kad_value)
                                    # Lokal cachen
                                    dht_store[bytes.fromhex(key_hex)] = value
                                    logger.info(f"DHT-GET aus Kademlia: {key_hex[:16]}...")
                            except Exception as e:
                                logger.warning(f"Kademlia-GET fehlgeschlagen: {e}")
                        response = {"status": "ok", "key": key_hex, "value": value}
                    else:
                        response = {"status": "error", "message": "kein key"}
                    import struct
                    response_payload = _json.dumps(response).encode("utf-8")
                    typed = bytes([FRAME_DHT_GET]) + response_payload
                    padded = _apply_padding(typed)
                    nonce = __import__("os").urandom(12)
                    ct = cipher.encrypt(nonce, padded, None)
                    frame = struct.pack(">I", len(ct) + 12) + nonce + ct
                    writer.write(frame)
                    await writer.drain()
                except Exception as e:
                    logger.error(f"Fehler bei DHT-GET: {e}")
            else:
                logger.error(f"Unbekannter Frame-Typ: {frame_type:#x}")
        except (asyncio.IncompleteReadError, ConnectionResetError):
            logger.debug("Peer-Verbindung regulaer beendet")
        except Exception as e:
            logger.error(f"Peer-Fehler: {type(e).__name__}: {e!r}")
        finally:
            writer.close()

    server = await asyncio.start_server(handle, host, port)
    logger.info(f"Peer-Server laeuft auf {host}:{port}")
    async with server:
        await server.serve_forever()
