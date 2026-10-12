"""Payment-System für Erebos Network.

Ermöglicht Bezahlung für Dienste, Jobbörse, Marktplatz.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .wallet import MoneroWallet, PaymentRequest, PaymentStatus


class PaymentPurpose(Enum):
    """Zweck einer Zahlung."""

    SERVICE = "service"        # Dienstleistung
    JOB = "job"                # Jobbörse
    MARKETPLACE = "marketplace"  # Marktplatz
    DONATION = "donation"      # Spende


@dataclass
class ServiceOffer:
    """Ein Dienstleistungs-Angebot."""

    offer_id: str
    provider_peer_id: str
    title: str
    description: str
    price_xmr: float
    purpose: PaymentPurpose = PaymentPurpose.SERVICE
    created_at: float = field(default_factory=time.time)

    @property
    def is_free(self) -> bool:
        return self.price_xmr <= 0.0


@dataclass
class Order:
    """Eine Bestellung / ein Auftrag."""

    order_id: str
    offer_id: str
    buyer_peer_id: str
    seller_peer_id: str
    amount_xmr: float
    payment_request_id: Optional[str] = None
    status: str = "created"  # created, paid, delivered, completed, cancelled
    created_at: float = field(default_factory=time.time)
    paid_at: Optional[float] = None


class PaymentSystem:
    """Payment-System für Erebos.

    Verbindet Wallet, Angebote und Bestellungen.
    """

    def __init__(self, wallet: Optional[MoneroWallet] = None):
        self.wallet = wallet or MoneroWallet()
        self._offers: dict[str, ServiceOffer] = {}
        self._orders: dict[str, Order] = {}
        self._stats = {
            "offers_created": 0,
            "orders_created": 0,
            "orders_paid": 0,
            "total_volume_xmr": 0.0,
        }

    def create_offer(
        self,
        offer_id: str,
        provider_peer_id: str,
        title: str,
        description: str,
        price_xmr: float,
        purpose: PaymentPurpose = PaymentPurpose.SERVICE,
    ) -> ServiceOffer:
        """Erstellt ein Dienstleistungs-Angebot."""
        if price_xmr < 0:
            raise ValueError("Preis muss >= 0 sein")

        offer = ServiceOffer(
            offer_id=offer_id,
            provider_peer_id=provider_peer_id,
            title=title,
            description=description,
            price_xmr=price_xmr,
            purpose=purpose,
        )
        self._offers[offer_id] = offer
        self._stats["offers_created"] += 1
        return offer

    def get_offer(self, offer_id: str) -> Optional[ServiceOffer]:
        """Gibt ein Angebot zurück."""
        return self._offers.get(offer_id)

    def list_offers(
        self, purpose: Optional[PaymentPurpose] = None
    ) -> list[ServiceOffer]:
        """Listet Angebote auf."""
        offers = list(self._offers.values())
        if purpose:
            offers = [o for o in offers if o.purpose == purpose]
        return offers

    def create_order(
        self,
        order_id: str,
        offer_id: str,
        buyer_peer_id: str,
    ) -> Order:
        """Erstellt eine Bestellung.

        Args:
            order_id: Bestell-ID
            offer_id: Angebots-ID
            buyer_peer_id: Käufer

        Returns:
            Order

        Raises:
            ValueError: Wenn Angebot nicht existiert
        """
        if offer_id not in self._offers:
            raise ValueError(f"Angebot nicht gefunden: {offer_id}")

        offer = self._offers[offer_id]

        # Zahlungsanfrage erstellen
        request = self.wallet.create_request(
            amount_xmr=offer.price_xmr,
            recipient_address=self.wallet.address,
            memo=f"Order {order_id}: {offer.title}",
        )

        order = Order(
            order_id=order_id,
            offer_id=offer_id,
            buyer_peer_id=buyer_peer_id,
            seller_peer_id=offer.provider_peer_id,
            amount_xmr=offer.price_xmr,
            payment_request_id=request.request_id,
        )
        self._orders[order_id] = order
        self._stats["orders_created"] += 1
        return order

    def pay_order(self, order_id: str) -> bool:
        """Bezahlt eine Bestellung.

        Args:
            order_id: Bestell-ID

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Bestellung nicht existiert
        """
        if order_id not in self._orders:
            raise ValueError(f"Bestellung nicht gefunden: {order_id}")

        order = self._orders[order_id]

        if order.status != "created":
            raise ValueError(f"Bestellung nicht im Status 'created': {order.status}")

        if order.payment_request_id is None:
            return False

        # Wallet-Guthaben aufladen (für Prototyp)
        if self.wallet.get_info().balance_xmr < order.amount_xmr:
            self.wallet.receive(order.amount_xmr, memo="Top-up for order")

        success = self.wallet.pay(order.payment_request_id)

        if success:
            order.status = "paid"
            order.paid_at = time.time()
            self._stats["orders_paid"] += 1
            self._stats["total_volume_xmr"] += order.amount_xmr

        return success

    def get_order(self, order_id: str) -> Optional[Order]:
        """Gibt eine Bestellung zurück."""
        return self._orders.get(order_id)

    def complete_order(self, order_id: str) -> bool:
        """Markiert Bestellung als abgeschlossen."""
        if order_id not in self._orders:
            return False
        order = self._orders[order_id]
        if order.status == "paid":
            order.status = "completed"
            return True
        return False

    @property
    def offer_count(self) -> int:
        return len(self._offers)

    @property
    def order_count(self) -> int:
        return len(self._orders)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self._stats,
            "offer_count": self.offer_count,
            "order_count": self.order_count,
            "wallet": self.wallet.get_stats(),
        }
