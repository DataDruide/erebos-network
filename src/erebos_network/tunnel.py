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
import struct
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .onion import open_layer

logger = logging.getLogger(__name__)

KEYS_DIR = Path(__file__).parent.parent.parent / "erebos_keys"
PEER_HOST = "127.0.0.1"
PEER_PORT = 9999

MAX_FRAME = 65536

# Frame-Typen (erstes Byte im entschluesselten Frame einer Tunnel-Session)
FRAME_RELAY = 0x01  # payload = onion-layer, bitte weiterleiten
FRAME_OPEN  = 0x02  # payload = "host:port", Ziel oeffnen
FRAME_DATA  = 0x03  # payload = Stream-Nutzdaten

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


def _derive_key(shared_secret: bytes) -> bytes:
    """Leitet einen 32-Byte-Schluessel aus dem Shared Secret ab."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"erebos-tunnel-v1",
    ).derive(shared_secret)


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    return await reader.readexactly(n)


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

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        ed_priv, x_priv, ed_pub, x_pub = _load_or_create_keypair("client")

        # Sende unsere X25519 oeffentlichen Schluessel + Ed25519 Signatur
        signature = ed_priv.sign(x_pub)
        logger.debug(f"Client sendet: x_pub={len(x_pub)}B, sig={len(signature)}B")
        logger.debug(f"Client x_pub hex: {x_pub.hex()}")
        logger.debug(f"Client sig hex:   {signature.hex()[:32]}...")
        await _send_frame(self.writer, x_pub + signature)

        # Empfange Peer's X25519 oeffentlichen Schluessel + Signatur
        peer_data = await _recv_frame(self.reader)
        peer_x_pub = peer_data[:32]
        peer_sig = peer_data[32:]

        # Verifiziere Peer's Signatur (Peer's Ed25519 Pubkey ist in KEYS_DIR)
        _, _, peer_ed_pub, _ = _load_or_create_keypair("peer")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        peer_ed = Ed25519PublicKey.from_public_bytes(peer_ed_pub)
        peer_ed.verify(peer_sig, peer_x_pub)

        # X25519 Schluesselaustausch
        shared = x_priv.exchange(X25519PublicKey.from_public_bytes(peer_x_pub))
        key = _derive_key(shared)
        self.cipher = ChaCha20Poly1305(key)
        logger.info(f"Verschluesselter Tunnel zu {self.host}:{self.port} aufgebaut")

    async def send(self, data: bytes):
        nonce = os.urandom(12)
        ct = self.cipher.encrypt(nonce, data, None)
        await _send_frame(self.writer, nonce + ct)

    async def send_typed(self, frame_type: int, payload: bytes):
        """Sendet einen typisierten Frame innerhalb der Tunnel-Session."""
        await self.send(bytes([frame_type]) + payload)

    async def receive(self) -> bytes:
        frame = await _recv_frame(self.reader)
        nonce, ct = frame[:12], frame[12:]
        return self.cipher.decrypt(nonce, ct, None)

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass


async def _handle_exit(reader, writer, cipher, host, port):
    """Exit-Modus: Ziel oeffnen und Klartext-Strom durchleiten.

    Wird von Peer-2 aufgerufen. `host:port` kommt hier NICHT mehr aus
    dem ersten Frame, sondern wurde vom Aufrufer bereits aus der
    entschluesselten Onion-Layer gelesen.
    """
    remote_reader, remote_writer = await asyncio.open_connection(host, port)

    async def peer_to_target():
        while True:
            frame = await _recv_frame(reader)
            data = cipher.decrypt(frame[:12], frame[12:], None)
            if not data:
                break
            logger.debug(f"Peer -> Ziel: {len(data)}B")
            remote_writer.write(data)
            await remote_writer.drain()

    async def target_to_peer():
        while True:
            data = await remote_reader.read(MAX_FRAME)
            if not data:
                break
            logger.debug(f"Ziel -> Peer: {len(data)}B")
            nonce = os.urandom(12)
            ct = cipher.encrypt(nonce, data, None)
            await _send_frame(writer, nonce + ct)

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


async def _handle_relay(reader, writer, cipher, peer_name: str, first_payload: bytes):
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

    NEXT_HOST = "127.0.0.1"

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

    next_layer = decrypted[3:]
    logger.info(
        f"Relay: leite weiter an {NEXT_HOST}:{next_port} "
        f"(frame_type={next_frame_type:#x}, layer_len={len(next_layer)})"
    )

    tunnel2 = ErebosTunnelClient(host=NEXT_HOST, port=next_port)
    try:
        await tunnel2.connect()
    except Exception as e:
        logger.error(f"Relay: Tunnel zu {NEXT_HOST}:{next_port} fehlgeschlagen: {e}")
        return

    try:
        await tunnel2.send_typed(next_frame_type, next_layer)

        async def client_to_next():
            try:
                while True:
                    frame = await _recv_frame(reader)
                    data = cipher.decrypt(frame[:12], frame[12:], None)
                    if not data:
                        break
                    await tunnel2.send(data)
            except Exception:
                pass

        async def next_to_client():
            try:
                while True:
                    data = await tunnel2.receive()
                    if not data:
                        break
                    nonce = os.urandom(12)
                    ct = cipher.encrypt(nonce, data, None)
                    await _send_frame(writer, nonce + ct)
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


async def run_peer_server(port: int = PEER_PORT):
    """Startet den Peer-Server, der Tunnel-Verbindungen annimmt."""

    peer_name = PORT_TO_PEER_NAME.get(port)
    if peer_name is None:
        raise ValueError(
            f"Port {port} ist keinem Peer-Namen zugeordnet. "
            f"Bekannte Ports: {sorted(PORT_TO_PEER_NAME.keys())}"
        )
    logger.info(f"Peer-Identitaet: {peer_name} (Port {port})")

    async def handle(reader, writer):
        logger.info("Eingehende Tunnel-Verbindung")
        try:
            client_data = await _recv_frame(reader)
            logger.debug(f"Peer empfing: {len(client_data)}B total")
            client_x_pub = client_data[:32]
            client_sig = client_data[32:]
            logger.debug(f"Peer empfaengt x_pub: {client_x_pub.hex()}")
            logger.debug(f"Peer empfaengt sig:   {client_sig.hex()[:32]}...")

            ed_priv, x_priv, ed_pub, x_pub = _load_or_create_keypair("peer")

            # Verifiziere Client's Signatur
            _, _, client_ed_pub, _ = _load_or_create_keypair("client")
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            client_ed = Ed25519PublicKey.from_public_bytes(client_ed_pub)
            logger.debug(f"Peer Pubkey: {client_ed_pub.hex()}")
            logger.debug(f"Peer x_pub:  {client_x_pub.hex()}")
            logger.debug(f"Peer sig:    {client_sig.hex()[:32]}...")
            try:
                client_ed.verify(client_sig, client_x_pub)
                logger.debug("Peer Verifikation: GUELTIG")
            except Exception as ve:
                logger.debug(f"Peer Verifikation FEHLER: {type(ve).__name__}: {ve!r}")
                raise

            # Sende unsere X25519 Pubkey + Signatur
            signature = ed_priv.sign(x_pub)
            await _send_frame(writer, x_pub + signature)

            # Schluessel ableiten
            shared = x_priv.exchange(X25519PublicKey.from_public_bytes(client_x_pub))
            key = _derive_key(shared)
            cipher = ChaCha20Poly1305(key)

            # Ersten typisierten Frame empfangen
            frame = await _recv_frame(reader)
            first = cipher.decrypt(frame[:12], frame[12:], None)
            if not first:
                logger.warning("Leerer erster Frame")
                return

            frame_type = first[0]
            payload = first[1:]

            if frame_type == FRAME_RELAY:
                logger.info("Relay-Modus aktiv (kein Ziel sichtbar)")
                await _handle_relay(reader, writer, cipher, peer_name, payload)
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
                await _handle_exit(reader, writer, cipher, host, port)
            else:
                logger.error(f"Unbekannter Frame-Typ: {frame_type:#x}")
        except Exception as e:
            logger.error(f"Peer-Fehler: {type(e).__name__}: {e!r}")
        finally:
            writer.close()

    server = await asyncio.start_server(handle, PEER_HOST, port)
    logger.info(f"Peer-Server laeuft auf {PEER_HOST}:{port}")
    async with server:
        await server.serve_forever()
