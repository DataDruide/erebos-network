"""Integration-Tests für das komplette Erebos-Ökosystem."""

import pytest

from erebos_network.discovery import PeerDiscovery
from erebos_network.governance import Governance, GovernanceConfig
from erebos_network.naming import NamingService
from erebos_network.payment import PaymentPurpose, PaymentSystem
from erebos_network.peer import ErebosPeer, PeerConfig
from erebos_network.swap import AtomicSwap
from erebos_network.wallet import MoneroWallet


@pytest.mark.asyncio
async def test_full_ecosystem():
    """Komplettes Ökosystem funktioniert zusammen."""
    # 1. Peer-Netzwerk
    config = PeerConfig(address="127.0.0.1:9000")
    peer = ErebosPeer(config)
    await peer.start()

    # 2. Domain registrieren
    domain = peer.register_domain("marketplace")
    assert domain == "marketplace.erebos"

    # 3. Wallet + Payment
    wallet = MoneroWallet()
    wallet.receive(100.0)
    payment = PaymentSystem(wallet)

    # 4. Angebot erstellen
    payment.create_offer(
        offer_id="job-1",
        provider_peer_id="peer1",
        title="Web-Entwicklung",
        description="5 Stunden Arbeit",
        price_xmr=2.5,
        purpose=PaymentPurpose.JOB,
    )

    # 5. Bestellung + Bezahlung
    payment.create_order("order-1", "job-1", "buyer1")
    assert payment.pay_order("order-1") is True
    assert payment.complete_order("order-1") is True

    # 6. Statistiken
    stats = payment.get_stats()
    assert stats["orders_paid"] == 1
    assert stats["total_volume_xmr"] == 2.5

    await peer.stop()


def test_governance_with_payment():
    """Governance + Payment funktionieren."""
    gov = Governance(GovernanceConfig(pow_difficulty=2))
    wallet = MoneroWallet()
    wallet.receive(50.0)
    payment = PaymentSystem(wallet)

    # Peer registrieren
    pow_result = gov.register_peer("127.0.0.1:8000")
    assert gov.is_registered(pow_result.peer_id) is True

    # Payment parallel
    payment.create_offer("o1", pow_result.peer_id, "Service", "D", 1.0)
    assert payment.offer_count == 1


def test_swap_with_wallet():
    """Atomic Swap + Wallet funktionieren."""
    wallet = MoneroWallet()
    wallet.receive(10.0)

    swap = AtomicSwap()
    offer = swap.create_offer("peer1", 1.0, 2.0)
    swap.join_swap(offer.swap_id, "peer2")
    assert swap.execute_swap(offer.swap_id) is True


def test_discovery_with_naming():
    """Discovery + Naming funktionieren zusammen."""
    discovery = PeerDiscovery("127.0.0.1:8000")
    naming = NamingService()

    discovery.add_peer("127.0.0.1:8001")
    discovery.add_peer("127.0.0.1:8002")

    naming.register("forum", "127.0.0.1:8001")
    naming.register("stats", "127.0.0.1:8002")

    assert discovery.peer_count == 2
    assert naming.count == 2

    record = naming.resolve("forum.erebos")
    assert record.address == "127.0.0.1:8001"
