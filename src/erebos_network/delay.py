"""Delay fuer Erebos Network.

Fuegt zufaellige Verzoegerungen hinzu, um Timing-Korrelation zu verhindern.

Erweitert um Poisson-Mixing (Exponentialverteilung).
"""

import asyncio
import random
import secrets
from dataclasses import dataclass


@dataclass
class DelayConfig:
    """Konfiguration fuer Verzoegerungen."""

    min_ms: int = 0
    max_ms: int = 500
    distribution: str = "uniform"  # uniform, exponential, normal, poisson

    def sample(self) -> float:
        """Zieht eine zufaellige Verzoegerung in Sekunden."""
        if self.distribution == "uniform":
            delay_ms = random.uniform(self.min_ms, self.max_ms)
        elif self.distribution in ("exponential", "poisson"):
            # Poisson-Prozess: exponentialverteilte Zwischenankunftszeiten
            mean = (self.min_ms + self.max_ms) / 2
            delay_ms = random.expovariate(1.0 / mean)
            delay_ms = min(delay_ms, self.max_ms)
        elif self.distribution == "normal":
            mean = (self.min_ms + self.max_ms) / 2
            std = (self.max_ms - self.min_ms) / 4
            delay_ms = max(self.min_ms, min(random.gauss(mean, std), self.max_ms))
        else:
            delay_ms = random.uniform(self.min_ms, self.max_ms)

        return delay_ms / 1000.0


# Vordefinierte Konfigurationen
DELAY_CONFIGS = {
    "none": DelayConfig(min_ms=0, max_ms=0, distribution="uniform"),
    "fast": DelayConfig(min_ms=0, max_ms=50, distribution="uniform"),
    "standard": DelayConfig(min_ms=0, max_ms=200, distribution="uniform"),
    "high": DelayConfig(min_ms=50, max_ms=500, distribution="uniform"),
    "mixnet": DelayConfig(min_ms=100, max_ms=500, distribution="poisson"),
}


async def apply_delay(config: DelayConfig) -> float:
    """Wendet eine Verzoegerung an."""
    delay = config.sample()
    if delay > 0:
        await asyncio.sleep(delay)
    return delay


def get_delay_config(name: str) -> DelayConfig:
    """Gibt eine Delay-Konfiguration zurueck."""
    return DELAY_CONFIGS.get(name, DELAY_CONFIGS["standard"])


def poisson_inter_arrival(rate_per_second: float) -> float:
    """Zieht eine exponentialverteilte Zwischenankunftszeit.

    Fuer Poisson-Prozesse: Die Zeit zwischen zwei Ereignissen
    ist exponentialverteilt mit Parameter lambda = rate.

    Args:
        rate_per_second: Ereignisrate pro Sekunde

    Returns:
        Zeit bis zum naechsten Ereignis in Sekunden
    """
    if rate_per_second <= 0:
        return float("inf")
    return random.expovariate(rate_per_second)
