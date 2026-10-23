from erebos_network.rendezvous import RendezvousRequest, build_rendezvous_request


def test_rendezvous_request_roundtrip():
    req = build_rendezvous_request(
        client_ephemeral_key=b"\x01" * 32,
        rendezvous_peer_id="peer1",
        rendezvous_address="127.0.0.1:9999",
    )
    data = req.to_dict()
    req2 = RendezvousRequest.from_dict(data)
    assert req2.rendezvous_peer_id == "peer1"
    assert req2.rendezvous_address == "127.0.0.1:9999"
    assert req2.client_ephemeral_key == b"\x01" * 32
