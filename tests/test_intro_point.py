import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from erebos_network.intro_point import (
    forward_rendezvous_request,
    receive_rendezvous_response_from_hs,
)


def test_forward_rendezvous_request():
    tunnel = MagicMock()
    tunnel.send_rendezvous_request = AsyncMock()

    payload = {
        "rendezvous_peer_id": "peer2",
        "rendezvous_address": "127.0.0.1:9998",
    }

    asyncio.run(forward_rendezvous_request(payload, tunnel))
    tunnel.send_rendezvous_request.assert_called_once_with(payload)


def test_receive_rendezvous_response_from_hs():
    tunnel = MagicMock()
    tunnel.receive = AsyncMock(return_value=json.dumps({
        "status": "ok",
        "message": "Tunnel aufgebaut",
    }).encode("utf-8"))

    response = asyncio.run(receive_rendezvous_response_from_hs(tunnel))
    assert response is not None
    assert response["status"] == "ok"
