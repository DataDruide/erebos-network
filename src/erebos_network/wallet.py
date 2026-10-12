"""Monero-Wallet-Integration für Erebos Network.

Verbindet Erebos mit Monero-Wallet-RPC.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PaymentStatus(Enum):
    """Status einer Zahlung."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class PaymentRequest:
    """Eine Zahlungsanfrage."""

    request_id: str
    amount_xmr: float  # in XMR
    recipient_address: str
    memo: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: PaymentStatus = PaymentStatus.PENDING
    tx_hash: Optional[str] = None
    confirmations: int = 0

    def __post_init__(self):
        if self.expires_at == 0.0:
            self.expires_at = self.created_at + 3600  # 1h

    @property
    def is_expired(self) -> bool:
        """Ob Anfrage abgelaufen ist."""
        return time.time() > self.expires_at

    @property
    def is_paid(self) -> bool:
        """Ob bezahlt."""
        return self.status == PaymentStatus.CONFIRMED

    @property
    def amount_atomic(self) -> int:
        """Betrag in atomic units (1 XMR = 10^12 atomic)."""
        return int(self.amount_xmr * 1_000_000_000_000)


@dataclass
class WalletInfo:
    """Information über eine Wallet."""

    address: str
    balance_xmr: float
    unlocked_balance_xmr: float
    height: int
    is_view_only: bool = False


class MoneroWallet:
    """Monero-Wallet-Interface.

    Simuliert Wallet-RPC für den Prototyp.
    In Produktion: echte RPC-Verbindung zu monero-wallet-rpc.
    """

    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:18082",
        address: Optional[str] = None,
    ):
        self.rpc_url = rpc_url
        self.address = address or self._generate_address()
        self._balance_xmr: float = 0.0
        self._requests: dict[str, PaymentRequest] = {}
        self._transactions: list[dict] = []
        self._height = 0

    def _generate_address(self) -> str:
        """Generiert eine Pseudo-Monero-Adresse (für Prototyp)."""
        seed = f"erebos-{time.time()}"
        return "4" + hashlib.sha256(seed.encode()).hexdigest()[:94]

    def get_info(self) -> WalletInfo:
        """Gibt Wallet-Informationen zurück."""
        return WalletInfo(
            address=self.address,
            balance_xmr=self._balance_xmr,
            unlocked_balance_xmr=self._balance_xmr,
            height=self._height,
        )

    def create_request(
        self,
        amount_xmr: float,
        recipient_address: str,
        memo: str = "",
        expires_in_seconds: int = 3600,
    ) -> PaymentRequest:
        """Erstellt eine Zahlungsanfrage.

        Args:
            amount_xmr: Betrag in XMR
            recipient_address: Empfänger-Adresse
            memo: Optionaler Verwendungszweck
            expires_in_seconds: Ablaufzeit

        Returns:
            PaymentRequest

        Raises:
            ValueError: Wenn Betrag ungültig
        """
        if amount_xmr <= 0:
            raise ValueError(f"Betrag muss positiv sein: {amount_xmr}")

        request_id = hashlib.sha256(
            f"{self.address}:{recipient_address}:{time.time()}".encode()
        ).hexdigest()[:16]

        request = PaymentRequest(
            request_id=request_id,
            amount_xmr=amount_xmr,
            recipient_address=recipient_address,
            memo=memo,
            expires_at=time.time() + expires_in_seconds,
        )
        self._requests[request_id] = request
        return request

    def pay(self, request_id: str) -> bool:
        """Bezahlt eine Anfrage (simuliert).

        Args:
            request_id: ID der Anfrage

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn Anfrage nicht existiert
        """
        if request_id not in self._requests:
            raise ValueError(f"Anfrage nicht gefunden: {request_id}")

        request = self._requests[request_id]

        if request.is_expired:
            request.status = PaymentStatus.EXPIRED
            return False

        if self._balance_xmr < request.amount_xmr:
            request.status = PaymentStatus.FAILED
            return False

        # Simulierte Transaktion
        tx_hash = hashlib.sha256(
            f"{request_id}:{time.time()}".encode()
        ).hexdigest()

        request.status = PaymentStatus.CONFIRMED
        request.tx_hash = tx_hash
        request.confirmations = 10

        self._balance_xmr -= request.amount_xmr
        self._transactions.append({
            "tx_hash": tx_hash,
            "amount": request.amount_xmr,
            "recipient": request.recipient_address,
            "timestamp": time.time(),
        })

        return True

    def receive(self, amount_xmr: float, memo: str = "") -> dict:
        """Simuliert den Empfang einer Zahlung.

        Args:
            amount_xmr: Betrag in XMR
            memo: Verwendungszweck

        Returns:
            Transaktions-Dict
        """
        if amount_xmr <= 0:
            raise ValueError("Betrag muss positiv sein")

        self._balance_xmr += amount_xmr
        tx = {
            "tx_hash": hashlib.sha256(
                f"in:{time.time()}".encode()
            ).hexdigest(),
            "amount": amount_xmr,
            "memo": memo,
            "timestamp": time.time(),
            "direction": "in",
        }
        self._transactions.append(tx)
        return tx

    def get_request(self, request_id: str) -> Optional[PaymentRequest]:
        """Gibt eine Anfrage zurück."""
        return self._requests.get(request_id)

    def list_requests(
        self, status: Optional[PaymentStatus] = None
    ) -> list[PaymentRequest]:
        """Listet Anfragen auf."""
        requests = list(self._requests.values())
        if status:
            requests = [r for r in requests if r.status == status]
        return requests

    @property
    def request_count(self) -> int:
        return len(self._requests)

    @property
    def transaction_count(self) -> int:
        return len(self._transactions)

    def get_stats(self) -> dict:
        """Statistiken."""
        pending = sum(
            1 for r in self._requests.values()
            if r.status == PaymentStatus.PENDING
        )
        confirmed = sum(
            1 for r in self._requests.values()
            if r.status == PaymentStatus.CONFIRMED
        )
        return {
            "address": self.address[:16] + "...",
            "balance_xmr": round(self._balance_xmr, 6),
            "requests_total": self.request_count,
            "requests_pending": pending,
            "requests_confirmed": confirmed,
            "transactions": self.transaction_count,
        }
