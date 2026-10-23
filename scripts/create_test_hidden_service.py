"""Erstellt einen Test-Hidden-Service und veröffentlicht den Descriptor."""

import asyncio
import hashlib
import time
from cryptography.hazmat.primitives.asymmetric import ed25519

from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from erebos_network.distributed_dht import DistributedDescriptorStore
from erebos_network.dht import PeerInfo


async def main():
    # 1. Schlüsselpaar generieren
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    address = derive_erebos_address(public_key)
    print(f"Hidden Service Adresse: {address}")

    # 2. Descriptor erstellen
    intro = IntroPoint(
        peer_id="peer1",
        address="127.0.0.1:9997",
        public_key=public_key,
    )
    descriptor = HiddenServiceDescriptor(
        address=address,
        public_key=public_key,
        intro_points=[intro],
        created_at=time.time(),
        ttl_seconds=3600,
    )
    sign_descriptor(descriptor, private_key)

    # 3. In DHT veröffentlichen (an ALLE Peers)
    from erebos_network.tunnel import ErebosTunnelClient, FRAME_DHT_PUT
    import json
    key = hashlib.sha256(address.encode()).digest()
    payload = json.dumps({"key": key.hex(), "value": descriptor.to_dict()}).encode("utf-8")

    for port in [9997, 9998, 9999]:
        try:
            client = ErebosTunnelClient(host="127.0.0.1", port=port)
            await client.connect()
            await client.send_typed(FRAME_DHT_PUT, payload)
            await client.close()
            print(f"Descriptor an Peer auf Port {port} gesendet")
        except Exception as e:
            print(f"Fehler beim Senden an Port {port}: {e}")
    await asyncio.sleep(0.5)
    print(f"Descriptor veröffentlicht in DHT (Key: {key.hex()[:16]}...)")

    # 4. HTTP-Server starten (der Hidden Service antwortet auf Anfragen)
    async def handle_http(reader, writer):
        try:
            request = await reader.read(1024)
            response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 22\r\n\r\nHidden Service works!\n"
            writer.write(response)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle_http, "127.0.0.1", 8080)
    print("HTTP-Server läuft auf 127.0.0.1:8080")
    print("Hidden Service läuft. Drücke Strg+C zum Beenden.")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
