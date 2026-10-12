"""Atomic-Swap-Stub für Erebos Network.

Peer-zu-Peer-Handel ohne zentrale Börse.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SwapStatus(Enum):
    """Status eines Atomic Swaps."""

    INITIATED = "initiated"
    COUNTERPARTY_JOINED = "counterparty_joined"
    FUNDED = "funded"
    REDEEMED = "redeemed"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class SwapOffer:
    """Ein Atomic-Swap-Angebot."""

    swap_id: str
    initiator_peer_id: str
    offer_amount_xmr: float
    request_amount_xmr: float  # Was der Initiator will
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: SwapStatus = SwapStatus.INITIATED
    counterparty_peer_id: Optional[str] = None

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 7200  # 2h

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class AtomicSwap:
    """Atomic-Swap-System.

    Vereinfachter Prototyp für Peer-zu-Peer-Handel.
    In Produktion: Hash-Time-Locked Contracts (HTLC).
    """

    def __init__(self):
        self._offers: dict[str, SwapOffer] = {}
        self._stats = {
            "offers_created": 0,
            "swaps_completed": 0,
            "swaps_failed": 0,
        }

    def create_offer(
        self,
        initiator_peer_id: str,
        offer_amount_xmr: float,
        request_amount_xmr: float,
        expires_in_seconds: int = 7200,
    ) -> SwapOffer:
        """Erstellt ein Swap-Angebot.

        Args:
            initiator_peer_id: Initiator
            offer_amount_xmr: Was der Initiator anbietet
            request_amount_xmr: Was der Initiator will
            expires_in_seconds: Ablaufzeit

        Returns:
            SwapOffer
        """
        if offer_amount_xmr <= 0 or request_amount_xmr <= 0:
            raise ValueError("Beträge müssen positiv sein")

        swap_id = hashlib.sha256(
            f"{initiator_peer_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        offer = SwapOffer(
            swap_id=swap_id,
            initiator_peer_id=initiator_peer_id,
            offer_amount_xmr=offer_amount_xmr,
            request_amount_xmr=request_amount_xmr,
            expires_at=time.time() + expires_in_seconds,
        )
        self._offers[swap_id] = offer
        self._stats["offers_created"] += 1
        return offer

    def join_swap(
        self,
        swap_id: str,
        counterparty_peer_id: str,
    ) -> bool:
        """Tritt einem Swap bei.

        Args:
            swap_id: Swap-ID
            counterparty_peer_id: Gegenpartei

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Swap nicht existiert oder abgelaufen
        """
        if swap_id not in self._offers:
            raise ValueError(f"Swap nicht gefunden: {swap_id}")

        offer = self._offers[swap_id]

        if offer.is_expired:
            offer.status = SwapStatus.FAILED
            self._stats["swaps_failed"] += 1
            raise ValueError("Swap ist abgelaufen")

        if offer.status != SwapStatus.INITIATED:
            raise ValueError(f"Swap nicht im Status 'initiated': {offer.status}")

        offer.counterparty_peer_id = counterparty_peer_id
        offer.status = SwapStatus.COUNTERPARTY_JOINED
        return True

    def execute_swap(self, swap_id: str) -> bool:
        """Führt einen Swap aus.

        Args:
            swap_id: Swap-ID

        Returns:
            True wenn erfolgreich
        """
        if swap_id not in self._offers:
            return False

        offer = self._offers[swap_id]

        if offer.status != SwapStatus.COUNTERPARTY_JOINED:
            return False

        # Simulierte Ausführung
        offer.status = SwapStatus.REDEEMED
        self._stats["swaps_completed"] += 1
        return True

    def get_offer(self, swap_id: str) -> Optional[SwapOffer]:
        """Gibt ein Swap-Angebot zurück."""
        return self._offers.get(swap_id)

    def list_offers(
        self, status: Optional[SwapStatus] = None
    ) -> list[SwapOffer]:
        """Listet Swap-Angebote auf."""
        offers = list(self._offers.values())
        if status:
            offers = [o for o in offers if o.status == status]
        return offers

    @property
    def offer_count(self) -> int:
        return len(self._offers)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self._stats,
            "offer_count": self.offer_count,
        }
