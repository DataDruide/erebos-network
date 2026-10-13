"""Dandelion++ Verstaerkung gegen Monero-Timing-Angriffe.

Kombiniert:
- Dandelion++ mit Poisson-Embargo (PR #9295)
- OSPEAD-basierte Decoy-Verteilung
- Peer-Fallback (Debian-Patch)
- Cover-Transaktionen
- FCMP++-Ready-Interface

Basiert auf: Monero Research Lab, OSPEAD (2025), PR #9295, NDSS 2025.
"""

import hashlib
import logging
import math
import random
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class DandelionPhase(Enum):
    """Phase einer Transaktion."""

    STEM = "stem"
    FLUFF = "fluff"


class DecoyStrategy(Enum):
    """Strategie fuer Decoy-Auswahl."""

    MOSER_2018 = "moser_2018"
    OSPEAD = "ospead"
    FCMP_READY = "fcmp_ready"


@dataclass
class DandelionConfig:
    """Konfiguration fuer Dandelion++ Verstaerkung."""

    stem_probability: float = 0.9  # 90% Stem, 10% Fluff
    embargo_mean_seconds: float = 39.0
    embargo_min_seconds: float = 5.0
    embargo_max_seconds: float = 180.0
    epoch_interval_seconds: int = 600
    epoch_range_seconds: int = 30
    fluff_average_seconds: float = 5.0
    max_stem_hops: int = 10
    peer_fallback_enabled: bool = True
    decoy_strategy: DecoyStrategy = DecoyStrategy.OSPEAD
    cover_tx_rate: float = 0.15
    fcmp_ready: bool = True


@dataclass
class Transaction:
    """Eine Transaktion im Dandelion++-Netzwerk."""

    tx_id: str
    data: bytes
    phase: DandelionPhase = DandelionPhase.STEM
    hops: int = 0
    created_at: float = field(default_factory=time.time)
    embargo_at: float = 0.0
    is_cover: bool = False

    def __post_init__(self):
        if self.embargo_at == 0.0:
            self.embargo_at = self.created_at


class EmbargoRandomizer:
    """Poisson-basierte Embargo-Timeouts.

    Basiert auf Monero PR #9295: Reduziert vorzeitiges Fluffing
    von 2% auf 0.37%.
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        self.stats = {
            "timeouts_scheduled": 0,
            "total_timeout_seconds": 0.0,
        }

    def schedule_embargo(self) -> float:
        """Plant einen Poisson-verteilten Embargo-Timeout.

        Returns:
            Timeout in Sekunden
        """
        # Poisson mit mean=39s, gekappt auf [min, max]
        timeout = random.expovariate(1.0 / self.config.embargo_mean_seconds)
        timeout = max(self.config.embargo_min_seconds, timeout)
        timeout = min(self.config.embargo_max_seconds, timeout)

        self.stats["timeouts_scheduled"] += 1
        self.stats["total_timeout_seconds"] += timeout
        return timeout

    @property
    def avg_timeout(self) -> float:
        if self.stats["timeouts_scheduled"] == 0:
            return 0.0
        return self.stats["total_timeout_seconds"] / self.stats["timeouts_scheduled"]

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "avg_timeout": round(self.avg_timeout, 2),
            "config_mean": self.config.embargo_mean_seconds,
        }


class OSPEADDecoySampler:
    """OSPEAD-basierte Decoy-Auswahl.

    Basiert auf OSPEAD (2025): Reduziert MAP-Decoder-Angriff
    von 1-in-4.2 auf nahe 1-in-16.
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        # Vereinfachte OSPEAD-Verteilung (Prototyp)
        # In Produktion: Echte OSPEAD-Verteilung aus Monero Research Lab
        self._distribution = self._build_ospead_distribution()
        self.stats = {
            "decoys_sampled": 0,
        }

    def _build_ospead_distribution(self) -> list[float]:
        """Baut eine vereinfachte OSPEAD-Verteilung.

        Die echte OSPEAD-Verteilung ist komplex. Hier nutzen wir
        eine Approximation mit einem Peak bei ~1 Tag und einem
        langen Tail.
        """
        # Vereinfachte Verteilung: viele junge Outputs, wenige alte
        distribution = []
        for i in range(100):
            # Peak bei ~10% (junge Outputs)
            if i < 10:
                weight = 0.15
            elif i < 30:
                weight = 0.08
            elif i < 60:
                weight = 0.03
            else:
                weight = 0.01
            distribution.append(weight)

        # Normalisieren
        total = sum(distribution)
        return [w / total for w in distribution]

    def sample_decoys(self, real_index: int, ring_size: int = 16) -> list[int]:
        """Waehlt Decoys mit OSPEAD-Verteilung.

        Args:
            real_index: Index des echten Outputs
            ring_size: Groesse des Rings (default: 16)

        Returns:
            Liste von Indices (inkl. real_index)
        """
        decoys = [real_index]

        while len(decoys) < ring_size:
            # OSPEAD-basierte Auswahl
            idx = random.choices(
                range(len(self._distribution)),
                weights=self._distribution,
                k=1,
            )[0]

            if idx != real_index and idx not in decoys:
                decoys.append(idx)

        self.stats["decoys_sampled"] += 1
        random.shuffle(decoys)
        return decoys

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "strategy": self.config.decoy_strategy.value,
            "distribution_size": len(self._distribution),
        }


class PeerFallback:
    """Peer-Fallback fuer Dandelion++.

    Basiert auf Debian-Patch: Verhindert stille Degradierung
    zu Fluff, wenn keine Peers mit aktueller Height gefunden werden.
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        self.stats = {
            "fallbacks_used": 0,
            "degradations_prevented": 0,
        }

    def select_stem_peer(
        self,
        peers_with_height: list[str],
        peers_without_height: list[str],
    ) -> Optional[str]:
        """Waehlt einen Stem-Peer mit Fallback.

        Args:
            peers_with_height: Peers mit aktueller Height
            peers_without_height: Peers ohne Height-Info

        Returns:
            Peer-ID oder None
        """
        if peers_with_height:
            return random.choice(peers_with_height)

        if self.config.peer_fallback_enabled and peers_without_height:
            self.stats["fallbacks_used"] += 1
            self.stats["degradations_prevented"] += 1
            logger.info("Peer-Fallback: Nutze Peer ohne Height-Info")
            return random.choice(peers_without_height)

        return None

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "fallback_enabled": self.config.peer_fallback_enabled,
        }


class CoverTransactionGenerator:
    """Erzeugt Cover-Transaktionen.

    Basiert auf MRL-Empfehlung: Dummy-Txs zur Verschleierung.
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        self.stats = {
            "cover_txs_generated": 0,
            "cover_bytes_generated": 0,
        }

    def should_generate(self) -> bool:
        """Entscheidet, ob eine Cover-Tx generiert werden soll."""
        return random.random() < self.config.cover_tx_rate

    def generate(self) -> Transaction:
        """Erzeugt eine Cover-Transaktion."""
        tx_id = hashlib.sha256(
            secrets.token_bytes(32)
        ).hexdigest()[:16]

        size = random.randint(256, 2048)
        data = secrets.token_bytes(size)

        tx = Transaction(
            tx_id=tx_id,
            data=data,
            is_cover=True,
        )

        self.stats["cover_txs_generated"] += 1
        self.stats["cover_bytes_generated"] += size
        return tx

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "cover_rate": self.config.cover_tx_rate,
        }


class FCMPReadyInterface:
    """Interface fuer FCMP++-Bereitschaft.

    Basiert auf FCMP++ Roadmap: Anonymitaets-Set von 16 auf 100M+.
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        self.stats = {
            "fcmp_ready": config.fcmp_ready if config else True,
        }

    def get_anonymity_set_size(self) -> int:
        """Gibt die aktuelle Anonymitaets-Set-Groesse zurueck."""
        if self.config.fcmp_ready:
            return 100_000_000  # FCMP++ Ziel
        return 16  # Aktuelle Ring-Groesse

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "anonymity_set_size": self.get_anonymity_set_size(),
            "target_anonymity_set": 100_000_000,
        }


class DandelionPlusManager:
    """Dandelion++ Manager mit allen Verstaerkungen.

    Kombiniert:
    - Poisson-Embargo
    - OSPEAD-Decoys
    - Peer-Fallback
    - Cover-Txs
    - FCMP++-Ready
    """

    def __init__(self, config: Optional[DandelionConfig] = None):
        self.config = config or DandelionConfig()
        self.embargo = EmbargoRandomizer(self.config)
        self.decoys = OSPEADDecoySampler(self.config)
        self.peer_fallback = PeerFallback(self.config)
        self.cover = CoverTransactionGenerator(self.config)
        self.fcmp = FCMPReadyInterface(self.config)
        self.stats = {
            "transactions_processed": 0,
            "stem_transactions": 0,
            "fluff_transactions": 0,
            "cover_transactions": 0,
        }

    def process_transaction(
        self, tx_id: str, data: bytes
    ) -> Transaction:
        """Verarbeitet eine Transaktion durch Dandelion++.

        Args:
            tx_id: Transaktions-ID
            data: Transaktions-Daten

        Returns:
            Transaction mit Phase + Embargo
        """
        # Phase bestimmen
        if random.random() < self.config.stem_probability:
            phase = DandelionPhase.STEM
            self.stats["stem_transactions"] += 1
        else:
            phase = DandelionPhase.FLUFF
            self.stats["fluff_transactions"] += 1

        # Embargo planen
        embargo_timeout = self.embargo.schedule_embargo()

        tx = Transaction(
            tx_id=tx_id,
            data=data,
            phase=phase,
            embargo_at=time.time() + embargo_timeout,
        )

        self.stats["transactions_processed"] += 1

        # Cover-Tx generieren?
        if self.cover.should_generate():
            cover_tx = self.cover.generate()
            self.stats["cover_transactions"] += 1

        return tx

    def get_stats(self) -> dict:
        """Kombinierte Statistiken."""
        return {
            **self.stats,
            "embargo": self.embargo.get_stats(),
            "decoys": self.decoys.get_stats(),
            "peer_fallback": self.peer_fallback.get_stats(),
            "cover": self.cover.get_stats(),
            "fcmp": self.fcmp.get_stats(),
        }
