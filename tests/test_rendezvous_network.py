"""Netzwerk-Test für Rendezvous-Frames.

Startet einen Peer-Server, verbindet sich als Client, sendet einen
Rendezvous-Request und prüft, ob eine Antwort zurückkommt.
Der Tunnel-Aufbau zum Rendezvous-Punkt wird gemockt, weil im Test
kein zweiter Peer läuft.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from erebos_network.tunnel import (
    ErebosTunnelClient,
    FRAME_RENDEZVOUS_REQUEST,
    run_peer_server,
)


@pytest.mark.asyncio
async def test_rendezvous_over_real_socket():
    """Echter Socket-Test: Peer startet, Client verbindet, sendet Request."""
    port = 9997
    # Starte den Peer-Server im Hintergrund
    peer_task = asyncio.create_task(
        run_peer_server(port=port, ack_cover=False, host="127.0.0.1")
    )
    await asyncio.sleep(0.5)  # Warten, bis der Server lauscht

    try:
        # Client verbindet sich
        client = ErebosTunnelClient(port=port)
        await client.connect()
        assert client.cipher is not None

        # Sende einen Rendezvous-Request
        request_data = {
            "client_ephemeral_key": "01" * 32,
            "rendezvous_peer_id": "peer2",
            "rendezvous_address": "127.0.0.1:9998",
            "created_at": 1234567890.0,
        }
        await client.send_rendezvous_request(request_data)

        # Warte auf Antwort (mit Timeout)
        raw = await asyncio.wait_for(client.receive(), timeout=5.0)
        assert raw is not None
        response = json.loads(raw.decode("utf-8"))
        # Der Status kann "ok" oder "error" sein (weil der Tunnel-Aufbau
        # zu einem nicht existierenden Peer fehlschlägt). Wichtig ist,
        # dass eine Antwort ankommt.
        assert "status" in response
        assert "message" in response

        await client.close()
    finally:
        peer_task.cancel()
        try:
            await peer_task
        except asyncio.CancelledError:
            pass
