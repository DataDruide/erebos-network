"""Predictive Perturbation Defense gegen ML-Correlation.

Schuetzt gegen ML-basierte Traffic-Correlation (RECTor).
Basiert auf Augur (2025): Transformer-basierte Perturbation.

F1-Score sinkt von 0.9756 auf 0.0114 bei 0.07% Overhead.
"""

import hashlib
import logging
import math
import random
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AugurConfig:
    """Konfiguration fuer Predictive Perturbation."""

    window_size: int = 32
    prediction_horizon: int = 8
    perturbation_rate: float = 0.07
    max_perturbation_size: int = 1024
    min_perturbation_size: int = 64
    rate_limit_per_second: float = 10.0
    history_size: int = 256
    # Timing-Obfuskation (Härtung gegen Traffic-Fingerprinting)
    jitter_enabled: bool = False
    jitter_ratio: float = 0.3  # +/- 30% um Basisverzögerung


@dataclass
class TrafficSample:
    """Ein Traffic-Sample (Groesse, Richtung, Zeit)."""

    size: int
    direction: int  # 1 = out, -1 = in
    timestamp: float = field(default_factory=time.time)


class TrafficPredictor:
    """Leichtgewichtiger Traffic-Predictor.

    Nutzt ein einfaches Markov-Modell (Prototyp).
    In Produktion: Transformer (Augur).
    """

    def __init__(self, window_size: int = 32):
        self.window_size = window_size
        self._history: deque = deque(maxlen=window_size)
        self._transition_counts: dict[tuple[int, int], int] = {}
        self._last_size: int = 0
        self.stats = {
            "predictions": 0,
            "correct": 0,
        }

    def update(self, sample: TrafficSample) -> None:
        """Fuegt ein Sample hinzu und aktualisiert das Modell."""
        if self._last_size > 0:
            key = (self._last_size, sample.size)
            self._transition_counts[key] = (
                self._transition_counts.get(key, 0) + 1
            )
        self._last_size = sample.size
        self._history.append(sample)

    def predict_next_size(self) -> int:
        """Sagt die naechste Paketgroesse voraus."""
        self.stats["predictions"] += 1
        if not self._history or self._last_size == 0:
            return secrets.randbelow(1024) + 64

        # Finde wahrscheinlichste Transition
        candidates = {
            k: v for k, v in self._transition_counts.items()
            if k[0] == self._last_size
        }
        if not candidates:
            return secrets.randbelow(1024) + 64

        best = max(candidates, key=candidates.get)
        return best[1]

    def predict_direction(self) -> int:
        """Sagt die naechste Richtung voraus."""
        if not self._history:
            return 1
        # Einfach: Richtung wechselt oft
        return -self._history[-1].direction if self._history else 1

    @property
    def sample_count(self) -> int:
        return len(self._history)


class PredictivePerturbation:
    """Predictive Perturbation Layer.

    Injiziert kontextbewusste Dummy-Pakete basierend auf
    Traffic-Vorhersage. Basiert auf Augur (2025).
    """

    def __init__(self, config: Optional[AugurConfig] = None):
        self.config = config or AugurConfig()
        self.predictor = TrafficPredictor(
            window_size=self.config.window_size
        )
        self._history: deque = deque(maxlen=self.config.history_size)
        self._last_perturbation = 0.0
        self.stats = {
            "samples_processed": 0,
            "perturbations_injected": 0,
            "bytes_injected": 0,
            "predictions_made": 0,
        }

    def process_outgoing(
        self, data: bytes, timestamp: Optional[float] = None
    ) -> list[bytes]:
        """Verarbeitet ausgehende Daten.

        Returns:
            Liste von Paketen (Original + Perturbationen)
        """
        now = timestamp or time.time()
        sample = TrafficSample(size=len(data), direction=1, timestamp=now)
        self._history.append(sample)
        self.predictor.update(sample)
        self.stats["samples_processed"] += 1

        # Original-Paket
        packets = [data]

        # Perturbation basierend auf Vorhersage
        perturbation = self._generate_perturbation(now)
        if perturbation:
            packets.append(perturbation)
            self.stats["perturbations_injected"] += 1
            self.stats["bytes_injected"] += len(perturbation)

        return packets

    def _generate_perturbation(self, now: float) -> Optional[bytes]:
        """Generiert eine kontextbewusste Perturbation."""
        # Rate-Limit
        elapsed = now - self._last_perturbation
        if elapsed < (1.0 / self.config.rate_limit_per_second):
            return None

        # Entscheide ob Perturbation
        if random.random() > self.config.perturbation_rate:
            return None

        # Vorhergesagte Groesse
        predicted_size = self.predictor.predict_next_size()
        self.stats["predictions_made"] += 1

        # Perturbation mit passender Groesse
        size = max(
            self.config.min_perturbation_size,
            min(predicted_size, self.config.max_perturbation_size),
        )
        self._last_perturbation = now
        return secrets.token_bytes(size)

    def process_incoming(self, data: bytes) -> bytes:
        """Verarbeitet eingehende Daten (nur Logging)."""
        sample = TrafficSample(size=len(data), direction=-1)
        self._history.append(sample)
        self.predictor.update(sample)
        return data

    def get_traffic_shape(self) -> dict:
        """Gibt die aktuelle Traffic-Form zurueck (für Tests)."""
        if not self._history:
            return {"sizes": [], "directions": [], "count": 0}
        return {
            "sizes": [s.size for s in self._history],
            "directions": [s.direction for s in self._history],
            "count": len(self._history),
        }

    def get_stats(self) -> dict:
        """Statistiken."""
        overhead = 0.0
        if self.stats["samples_processed"] > 0:
            overhead = (
                self.stats["bytes_injected"]
                / max(1, self.stats["samples_processed"] * 512)
            ) * 100
        return {
            **self.stats,
            "predictor": {
                "samples": self.predictor.sample_count,
                "predictions": self.predictor.stats["predictions"],
            },
            "overhead_percent": round(overhead, 3),
            "config": {
                "perturbation_rate": self.config.perturbation_rate,
                "window_size": self.config.window_size,
            },
        }


class RateShaper:
    """Rate-Shaper gegen Shape-Analyse.

    Verhindert Traffic-Peaks (Nym-Schwachstelle).
    Basiert auf "Shift Your Shape" (2025).
    """

    def __init__(
        self,
        target_rate_per_second: float = 10.0,
        jitter_enabled: bool = False,
        jitter_ratio: float = 0.3,
    ):
        self.target_rate = target_rate_per_second
        self.jitter_enabled = jitter_enabled
        self.jitter_ratio = max(0.0, min(1.0, jitter_ratio))
        self._tokens = 0.0
        self._last_refill = time.time()
        self._max_tokens = target_rate_per_second * 2
        self.stats = {
            "packets_shaped": 0,
            "packets_delayed": 0,
            "total_delay_ms": 0.0,
        }

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._max_tokens, self._tokens + elapsed * self.target_rate
        )
        self._last_refill = now

    def allow(self) -> bool:
        """Prueft, ob ein Paket erlaubt ist (Token-Bucket)."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            self.stats["packets_shaped"] += 1
            return True
        self.stats["packets_delayed"] += 1
        return False

    def delay_for_next(self) -> float:
        """Berechnet die Verzoegerung bis zum naechsten Token.

        Bei aktiviertem Jitter wird die Basisverzoegerung um
        +/- jitter_ratio gestreut. Das erschwert Timing-Fingerprinting
        (konstante Intervallmuster verraten sonst den Client).
        """
        self._refill()
        if self._tokens >= 1.0:
            base = 0.0
        else:
            base = (1.0 - self._tokens) / self.target_rate

        if not self.jitter_enabled or base == 0.0:
            return base

        # Jitter proportional zur erwarteten Rate
        expected_gap = 1.0 / self.target_rate
        jitter = random.uniform(-self.jitter_ratio, self.jitter_ratio) * expected_gap
        return max(0.0, base + jitter)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "tokens": round(self._tokens, 2),
            "target_rate": self.target_rate,
            "jitter_enabled": self.jitter_enabled,
            "jitter_ratio": self.jitter_ratio,
        }
