import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from erebos_network.hidden_service_client import (
    send_rendezvous_over_tunnel,
    receive_rendezvous_response,
)
from erebos_network.rendezvous import build_rendezvous_request


def test_send_rendezvous_over_tunnel():
    tunnel_client = MagicMock()
    tunnel_client.send_rendezvous_request = AsyncMock()
    tunnel_client.peer_name = "peer1"

    request = build_rendezvous_request(
        client_ephemeral_key=b"\x01" * 32,
        rendezvous_peer_id="peer2",
        rendezvous_address="127.0.0.1:9998",
    )

    asyncio.run(send_rendezvous_over_tunnel(tunnel_client, request))
    tunnel_client.send_rendezvous_request.assert_called_once()
    call_args = tunnel_client.send_rendezvous_request.call_args[0][0]
    assert call_args["rendezvous_peer_id"] == "peer2"


def test_receive_rendezvous_response():
    tunnel_client = MagicMock()
    tunnel_client.receive = AsyncMock(return_value=json.dumps({
        "status": "ok",
        "message": "Tunnel aufgebaut",
    }).encode("utf-8"))

    response = asyncio.run(receive_rendezvous_response(tunnel_client))
    assert response is not None
    assert response["status"] == "ok"
