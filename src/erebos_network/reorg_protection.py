"""Monero-Reorg-Schutz fuer Erebos Network.

Schuetzt gegen Chain-Reorganizations (Monero 2025: 18-Block-Reorg).
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ReorgStatus(Enum):
    """Status einer Reorg-Pruefung."""

    OK = "ok"
    PENDING = "pending"
    REORG_DETECTED = "reorg_detected"
    INVALIDATED = "invalidated"


@dataclass
class ReorgConfig:
    """Konfiguration fuer Reorg-Schutz."""

    min_confirmations: int = 20
    high_value_confirmations: int = 30
    high_value_threshold_xmr: float = 10.0
    check_interval_seconds: int = 60
    max_reorg_depth: int = 50


@dataclass
class ChainSnapshot:
    """Snapshot der Chain zu einem Zeitpunkt."""

    height: int
    block_hash: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class PaymentRecord:
    """Aufzeichnung einer Zahlung mit Reorg-Schutz."""

    tx_hash: str
    amount_xmr: float
    confirmations: int
    block_height: int
    block_hash: str
    status: ReorgStatus = ReorgStatus.PENDING
    created_at: float = field(default_factory=time.time)
    last_checked: float = field(default_factory=time.time)
    invalidated_at: Optional[float] = None

    @property
    def required_confirmations(self) -> int:
        """Erforderliche Bestaetigungen je nach Wert."""
        return 30 if self.amount_xmr >= 10.0 else 20

    @property
    def is_safe(self) -> bool:
        """Zahlung ist sicher (genug Bestaetigungen)."""
        return (
            self.status == ReorgStatus.OK
            and self.confirmations >= self.required_confirmations
        )


class MoneroReorgProtection:
    """Schutz gegen Monero-Chain-Reorganizations."""

    def __init__(self, config: Optional[ReorgConfig] = None):
        self.config = config or ReorgConfig()
        self._payments: dict[str, PaymentRecord] = {}
        self._chain_history: list[ChainSnapshot] = []
        self._current_height: int = 0
        self._current_hash: str = ""
        self._last_reorg: Optional[float] = None
        self.stats = {
            "payments_tracked": 0,
            "payments_confirmed": 0,
            "payments_invalidated": 0,
            "reorgs_detected": 0,
            "checks_performed": 0,
        }

    def update_chain(self, height: int, block_hash: str) -> bool:
        """Aktualisiert den Chain-Status.

        Returns:
            True wenn Reorg erkannt wurde
        """
        reorg_detected = False

        if height < self._current_height:
            logger.warning(
                f"REORG ERKANNT: Height {self._current_height} -> {height}"
            )
            reorg_detected = True
            self.stats["reorgs_detected"] += 1
            self._last_reorg = time.time()
            self._handle_reorg(height, block_hash)

        self._current_height = height
        self._current_hash = block_hash

        snapshot = ChainSnapshot(height=height, block_hash=block_hash)
        self._chain_history.append(snapshot)
        if len(self._chain_history) > 1000:
            self._chain_history.pop(0)

        return reorg_detected

    def _handle_reorg(self, new_height: int, new_hash: str) -> None:
        """Behandelt eine Reorg (invalidiert betroffene Payments)."""
        for tx_hash, payment in self._payments.items():
            if payment.block_height > new_height:
                if payment.status != ReorgStatus.INVALIDATED:
                    payment.status = ReorgStatus.INVALIDATED
                    payment.invalidated_at = time.time()
                    self.stats["payments_invalidated"] += 1
                    logger.warning(
                        f"Payment invalidiert durch Reorg: {tx_hash}"
                    )

    def register_payment(
        self,
        tx_hash: str,
        amount_xmr: float,
        confirmations: int,
        block_height: int,
        block_hash: str,
    ) -> PaymentRecord:
        """Registriert eine Zahlung zur Ueberwachung."""
        record = PaymentRecord(
            tx_hash=tx_hash,
            amount_xmr=amount_xmr,
            confirmations=confirmations,
            block_height=block_height,
            block_hash=block_hash,
        )
        self._payments[tx_hash] = record
        self.stats["payments_tracked"] += 1
        return record

    def update_confirmations(
        self,
        tx_hash: str,
        confirmations: int,
        block_height: int,
        block_hash: str,
    ) -> ReorgStatus:
        """Aktualisiert Bestaetigungen (mit Reorg-Check)."""
        self.stats["checks_performed"] += 1

        payment = self._payments.get(tx_hash)
        if not payment:
            return ReorgStatus.PENDING

        if payment.status == ReorgStatus.INVALIDATED:
            return ReorgStatus.INVALIDATED

        # Pruefen ob Block noch existiert
        if payment.block_height > self._current_height:
            payment.status = ReorgStatus.INVALIDATED
            self.stats["payments_invalidated"] += 1
            return ReorgStatus.INVALIDATED

        # Hash-Pruefung
        if payment.block_height == block_height:
            if payment.block_hash != block_hash:
                payment.status = ReorgStatus.INVALIDATED
                self.stats["payments_invalidated"] += 1
                return ReorgStatus.INVALIDATED

        # Bestaetigungen aktualisieren
        payment.confirmations = confirmations
        payment.last_checked = time.time()

        if confirmations >= payment.required_confirmations:
            payment.status = ReorgStatus.OK
            self.stats["payments_confirmed"] += 1
        else:
            payment.status = ReorgStatus.PENDING

        return payment.status

    def is_payment_safe(self, tx_hash: str) -> bool:
        """Prueft, ob eine Zahlung sicher ist."""
        payment = self._payments.get(tx_hash)
        if not payment:
            return False
        return payment.is_safe

    def get_payment(self, tx_hash: str) -> Optional[PaymentRecord]:
        """Gibt eine Zahlung zurueck."""
        return self._payments.get(tx_hash)

    @property
    def current_height(self) -> int:
        return self._current_height

    @property
    def last_reorg(self) -> Optional[float]:
        return self._last_reorg

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "current_height": self._current_height,
            "active_payments": len(self._payments),
            "last_reorg": self._last_reorg,
            "config": {
                "min_confirmations": self.config.min_confirmations,
                "high_value_confirmations": self.config.high_value_confirmations,
                "high_value_threshold": self.config.high_value_threshold_xmr,
            },
        }
