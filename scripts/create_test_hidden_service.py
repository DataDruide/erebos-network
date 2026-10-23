"""Test-Hidden-Service mit HTTP-Datenkanal.

Erstellt einen Hidden Service, veröffentlicht den Descriptor,
und leitet eingehende Daten an einen lokalen HTTP-Server weiter.
"""

import asyncio
import hashlib
import json
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
from erebos_network.tunnel import (
    ErebosTunnelClient,
    FRAME_DHT_PUT,
    FRAME_RENDEZVOUS_REQUEST,
    FRAME_DATA,
)
from erebos_network.rendezvous import RendezvousRequest


async def handle_http(reader, writer):
    """Einfacher HTTP-Server, der auf Anfragen antwortet."""
    try:
        request = await reader.read(4096)
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
        print(f"HTTP-Fehler: {e}")
    finally:
        writer.close()


async def keep_alive(client):
    """Hält die Rendezvous-Verbindung offen und verarbeitet eingehende Daten.

    Wichtig: ErebosTunnelClient.receive() liefert die Nutzlast OHNE Frame-Typ.
    Wir unterscheiden daher am Inhalt:
    - JSON-Steuerframes ({"status": ...}) -> ignorieren (ACK, ready, ...)
    - HTTP-Anfragen (GET/POST/...)        -> an lokalen HTTP-Server weiterleiten
    - alles andere                        -> ignorieren
    """
    HTTP_PREFIXES = (b"GET ", b"POST ", b"HEAD ", b"PUT ", b"DELETE ", b"OPTIONS ", b"PATCH ", b"HTTP/")
    try:
        while True:
            try:
                data = await asyncio.wait_for(client.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                continue
            if not data:
                break
            # 1) JSON-Steuerframe? -> ignorieren (aber 'ready' loggen)
            try:
                msg = json.loads(data.decode("utf-8"))
                if isinstance(msg, dict) and "status" in msg:
                    if msg.get("status") == "ready":
                        print("Rendezvous-Paar vollständig!")
                    else:
                        print(f"Steuerframe ignoriert: {msg}")
                    continue
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
            # 2) Nur echte HTTP-Anfragen weiterleiten
            if not data.startswith(HTTP_PREFIXES):
                print(f"Ignoriere Nicht-HTTP-Daten: {data[:60]!r}")
                continue
            print(f"HTTP-Anfrage empfangen: {len(data)}B")
            http_reader, http_writer = await asyncio.open_connection("127.0.0.1", 8080)
            http_writer.write(data)
            await http_writer.drain()
            http_response = await http_reader.read(4096)
            http_writer.close()
            # WICHTIG: als FRAME_DATA senden, damit peer1 den Frame als
            # weiterzuleitenden Datenframe erkennt (sonst Typ 0x48 = 'H').
            await client.send_typed(FRAME_DATA, http_response)
            print(f"HTTP-Antwort gesendet: {len(http_response)}B")
    except (asyncio.IncompleteReadError, ConnectionResetError):
        print("keep_alive: Verbindung regulaer beendet")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"keep_alive Fehler: {type(e).__name__}: {e}")


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

    # 3. Descriptor an alle Peers verteilen
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

    print(f"Descriptor veröffentlicht in DHT (Key: {key.hex()[:16]}...)")

    # 4. HTTP-Server starten
    http_server = await asyncio.start_server(handle_http, "127.0.0.1", 8080)
    print("HTTP-Server läuft auf 127.0.0.1:8080")

    # 5. Beim Rendezvous-Punkt (Port 9999) registrieren
    print("Registriere Hidden Service beim Rendezvous-Punkt (Port 9999)...")
    try:
        rendezvous_client = ErebosTunnelClient(host="127.0.0.1", port=9999)
        await rendezvous_client.connect()
        from erebos_network.tunnel import FRAME_RENDEZVOUS_REGISTER
        import json as _json
        reg_key = address[:32]
        reg_payload = _json.dumps({"role": "hidden", "key": reg_key}).encode("utf-8")
        await rendezvous_client.send_typed(FRAME_RENDEZVOUS_REGISTER, reg_payload)
        print(f"Rendezvous-Registrierung (hidden) gesendet für Key {reg_key[:16]}...")
        # Warte NICHT auf 'ready' – starte sofort den Rendezvous-Server
        # Der keep_alive übernimmt das Warten auf 'ready' und die Datenweiterleitung
        print("Rendezvous-Registrierung abgeschlossen, starte Rendezvous-Server...")
        # Behalte die Verbindung offen (für Datenkanal)
        asyncio.create_task(keep_alive(rendezvous_client))
    except Exception as e:
        print(f"Fehler bei Rendezvous-Registrierung: {e}")

    # 6. Auf Rendezvous-Anfragen warten
    print("Hidden Service läuft. Warte auf Rendezvous-Anfragen...")

    async def handle_rendezvous(reader, writer):
        """Empfängt eine Rendezvous-Anfrage über einen Tunnel."""
        try:
            raw = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            if not raw:
                return

            if raw[0] == FRAME_RENDEZVOUS_REQUEST:
                data = json.loads(raw[1:].decode("utf-8"))
                print(f"Rendezvous-Anfrage empfangen: {data}")

                rendezvous_address = data.get("rendezvous_address", "")
                if ":" in rendezvous_address:
                    host, port = rendezvous_address.split(":")
                    port = int(port)
                    print(f"Baue Tunnel zum Rendezvous-Punkt {host}:{port}")

                    rendezvous_client = ErebosTunnelClient(host=host, port=port)
                    await rendezvous_client.connect()

                    # Registriere sich beim Rendezvous-Punkt
                    from erebos_network.tunnel import FRAME_RENDEZVOUS_REGISTER
                    import json as _json
                    reg_key = address[:32]  # Key für die Paarung
                    reg_payload = _json.dumps({"role": "hidden", "key": reg_key}).encode("utf-8")
                    await rendezvous_client.send_typed(FRAME_RENDEZVOUS_REGISTER, reg_payload)
                    print(f"Rendezvous-Registrierung (hidden) gesendet für Key {reg_key[:16]}...")

                    # Bestätigung senden
                    response = json.dumps({"status": "ok", "message": "Rendezvous aufgebaut"}).encode("utf-8")
                    writer.write(bytes([FRAME_RENDEZVOUS_REQUEST]) + response)
                    await writer.drain()

                    # Datenkanal: Leite eingehende Daten an HTTP-Server weiter
                    while True:
                        try:
                            data = await asyncio.wait_for(rendezvous_client.receive(), timeout=10.0)
                            if not data:
                                break
                            print(f"Daten empfangen: {len(data)}B")
                            # Leite an HTTP-Server weiter
                            http_reader, http_writer = await asyncio.open_connection("127.0.0.1", 8080)
                            http_writer.write(data)
                            await http_writer.drain()
                            http_response = await http_reader.read(4096)
                            http_writer.close()
                            # Sende Antwort zurück
                            await rendezvous_client.send(http_response)
                            print(f"Antwort gesendet: {len(http_response)}B")
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            print(f"Datenkanal-Fehler: {e}")
                            break

                    await rendezvous_client.close()
        except Exception as e:
            print(f"Rendezvous-Fehler: {e}")
        finally:
            writer.close()

    # 6. Rendezvous-Server starten
    rendezvous_server = await asyncio.start_server(handle_rendezvous, "127.0.0.1", 9996)
    print("Rendezvous-Server läuft auf 127.0.0.1:9996")

    async with http_server:
        async with rendezvous_server:
            await asyncio.gather(
                http_server.serve_forever(),
                rendezvous_server.serve_forever(),
            )


if __name__ == "__main__":
    asyncio.run(main())
