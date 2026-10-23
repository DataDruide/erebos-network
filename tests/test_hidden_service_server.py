import asyncio
from erebos_network.rendezvous import RendezvousRequest
from erebos_network.hidden_service_server import handle_rendezvous_request


class MockTunnelFactory:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.connected_to = None

    async def __call__(self, address):
        self.connected_to = address
        if self.should_fail:
            raise ConnectionError("Tunnel-Aufbau fehlgeschlagen")
        return "mock-tunnel"


def test_handle_rendezvous_request_ok():
    request = RendezvousRequest(
        client_ephemeral_key=b"\x01" * 32,
        rendezvous_peer_id="peer2",
        rendezvous_address="127.0.0.1:9998",
        created_at=0.0,
    )
    factory = MockTunnelFactory()
    response = asyncio.run(handle_rendezvous_request(request, factory))
    assert response.status == "ok"
    assert factory.connected_to == "127.0.0.1:9998"


def test_handle_rendezvous_request_error():
    request = RendezvousRequest(
        client_ephemeral_key=b"\x01" * 32,
        rendezvous_peer_id="peer2",
        rendezvous_address="127.0.0.1:9998",
        created_at=0.0,
    )
    factory = MockTunnelFactory(should_fail=True)
    response = asyncio.run(handle_rendezvous_request(request, factory))
    assert response.status == "error"
    assert "Tunnel-Aufbau fehlgeschlagen" in response.message
