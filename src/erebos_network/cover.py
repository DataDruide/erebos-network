"""Cover-Traffic fuer Erebos Network.

Erzeugt Dummy-Nachrichten, um echten Traffic zu verschleiern.

Erweitert um konstanten Cover-Traffic (Unobservability).
"""

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CoverConfig:
    """Konfiguration fuer Cover-Traffic.

    mode:
      - "poisson": exponentialverteilte Intervalle (Standard)
      - "burst":   kurze Bursts mit Pausen (bessere WF-Resistenz)
      - "constant": konstantes Intervall (max. Unobservability, hoher Overhead)
    """

    enabled: bool = True
    rate_per_second: float = 0.5
    min_size: int = 256
    max_size: int = 1024
    constant: bool = False
    mode: str = "poisson"
    burst_size: int = 5
    burst_pause_seconds: float = 2.0

    # Adaptive Steuerung (P1.2)
    adaptive: bool = False
    # Nach echtem Traffic: drosseln statt pausieren (Beobachter darf
    # keinen "Traffic = Stille"-Zusammenhang erkennen)
    quiet_seconds_after_real: float = 3.0
    quiet_rate_factor: float = 0.2  # 20% der Basisrate während Quiet-Phase
    # Nach langer Idle-Phase: leicht beschleunigen
    boost_when_idle_seconds: float = 10.0
    boost_factor: float = 2.0  # max. 2.0 — höher wäre selbst ein Fingerprint
    # Anonymitaets-Schwelle: unter dieser Menge laeuft Cover immer im Boost
    # (Quiet-Phase waere selbst ein Signal — siehe Zcash-Erfahrung)
    anonymity_threshold: int = 10

    # Reactive Drop-Cover (P1.3 / Nym-Lehre):
    # Zusaetzlicher Cover-Burst als Reaktion auf Downlink-Traffic.
    # Ziel: Downlink-Uplink-Asymmetrie verwischen, damit ein Beobachter,
    # der beide Seiten sieht, nicht "Stille = Client" ableiten kann.
    reactive: bool = False
    reactive_window_ms: int = 100     # Sliding Window fuer Downlink-Events
    reactive_max_match: int = 10      # max Cover-Frames pro Downlink-Burst
    reactive_size_jitter: float = 0.3 # +/-30% Groessenabweichung erlaubt


def generate_cover_message(
    min_size: int = 256,
    max_size: int = 1024,
) -> bytes:
    """Erzeugt eine zufaellige Cover-Nachricht."""
    size = random.randint(min_size, max_size)
    return secrets.token_bytes(size)


def generate_cover_batch(
    count: int,
    min_size: int = 256,
    max_size: int = 1024,
) -> list[bytes]:
    """Erzeugt mehrere Cover-Nachrichten."""
    return [generate_cover_message(min_size, max_size) for _ in range(count)]


def should_send_cover(config: CoverConfig, elapsed_seconds: float) -> bool:
    """Entscheidet, ob Cover-Traffic gesendet werden soll."""
    if not config.enabled:
        return False

    expected = config.rate_per_second * elapsed_seconds
    return random.random() < expected


class ConstantCoverTraffic:
    """Konstanter Cover-Traffic.

    Sendet kontinuierlich Cover-Nachrichten mit einer festen Rate,
    unabhaengig von echtem Traffic. Das verhindert, dass ein
    Beobachter erkennen kann, wann echte Kommunikation stattfindet.

    Basiert auf Poisson-Prozess (exponentialverteilte Zwischenankunftszeiten).
    """

    def __init__(self, config: Optional[CoverConfig] = None):
        self.config = config or CoverConfig()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.stats = {
            "messages_sent": 0,
            "bytes_sent": 0,
            "started_at": 0.0,
        }

    async def start(self) -> None:
        """Startet konstanten Cover-Traffic."""
        if self._running:
            return
        self._running = True
        self.stats["started_at"] = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Konstanter Cover-Traffic gestartet "
            f"({self.config.rate_per_second}/s)"
        )

    async def stop(self) -> None:
        """Stoppt Cover-Traffic."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Konstanter Cover-Traffic gestoppt")

    async def _run_loop(self) -> None:
        """Haupt-Loop: sendet Cover-Nachrichten mit Poisson-Verteilung."""
        while self._running:
            try:
                # Exponentialverteilte Zwischenankunftszeit
                delay = random.expovariate(self.config.rate_per_second)
                await asyncio.sleep(delay)

                msg = generate_cover_message(
                    self.config.min_size,
                    self.config.max_size,
                )
                self.stats["messages_sent"] += 1
                self.stats["bytes_sent"] += len(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cover-Traffic Fehler: {e}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> float:
        if self.stats["started_at"] == 0:
            return 0.0
        return time.time() - self.stats["started_at"]

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "running": self._running,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "rate_per_second": self.config.rate_per_second,
        }

class TunnelCoverInjector:
    """Sendet echten Cover-Traffic ueber einen ErebosTunnelClient.

    Anders als ConstantCoverTraffic (das nur Bytes erzeugt), sendet
    dieser Injector die Frames wirklich ueber einen bestehenden
    verschluesselten Tunnel. Der Empfaenger erkennt FRAME_COVER und
    verwirft die Payload.

    Modi:
      - poisson: exponentialverteilte Intervalle
      - burst:   N Frames schnell hintereinander, dann Pause
      - constant: konstantes Intervall (1/rate)
    """

    def __init__(
        self,
        tunnel,
        config: Optional[CoverConfig] = None,
        anonymity_provider=None,
    ):
        """
        Args:
            tunnel: ErebosTunnelClient, ueber den gesendet wird.
            config: CoverConfig (Default: neu).
            anonymity_provider: Optional Callable[[], int]. Liefert die
                aktuelle Anonymitaetsmenge. Wenn None oder Exception,
                wird 0 angenommen -> small_set-Phase.
        """
        self.tunnel = tunnel
        self.config = config or CoverConfig()
        self.anonymity_provider = anonymity_provider
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_real_traffic_at = 0.0
        # Downlink-Events fuer reactive Drop-Cover: deque[(timestamp, size)]
        from collections import deque
        self._downlink_events = deque(maxlen=256)
        self.stats = {
            "frames_sent": 0,
            "bytes_sent": 0,
            "errors": 0,
            "started_at": 0.0,
            "quiet_phases": 0,
            "boost_phases": 0,
            "small_set_phases": 0,
            "reactive_frames": 0,
            "reactive_bursts": 0,
        }

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.stats["started_at"] = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"TunnelCoverInjector gestartet "
            f"(mode={self.config.mode}, rate={self.config.rate_per_second}/s)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TunnelCoverInjector gestoppt")

    async def _send_one(self) -> None:
        """Sendet einen einzelnen Cover-Frame."""
        from .tunnel import FRAME_COVER
        msg = generate_cover_message(
            self.config.min_size,
            self.config.max_size,
        )
        await self.tunnel.send_typed(FRAME_COVER, msg)
        self.stats["frames_sent"] += 1
        self.stats["bytes_sent"] += len(msg)

    def _current_anonymity_set_size(self) -> int:
        """Liest die aktuelle Anonymitaetsmenge.

        Fehlt ein Provider oder wirft er, wird 0 zurueckgegeben — das
        bedeutet small_set. Ehrlich: der SOCKS5-Proxy kennt momentan
        nur len(peer_pool) als Proxy fuer die Netzwerkgroesse.
        """
        if self.anonymity_provider is None:
            return 0
        try:
            return max(0, int(self.anonymity_provider()))
        except Exception:
            return 0

    def _effective_rate(self) -> tuple[float, str]:
        """Berechnet die aktuelle Rate je nach adaptivem Zustand.

        Returns:
            (rate, phase) — phase ist "normal", "quiet", "boost"
            oder "small_set".
        """
        if not self.config.adaptive:
            return self.config.rate_per_second, "normal"

        # Anonymitaetsmenge zu klein → kein Quiet-Modus.
        # Bei kleiner Menge waere die Drosselung selbst ein Fingerprint
        # (Zcash-Erfahrung: 20-25% Shielded-Pool reicht fuer Korrelation).
        if self._current_anonymity_set_size() < self.config.anonymity_threshold:
            factor = min(self.config.boost_factor, 2.0)
            return self.config.rate_per_second * factor, "small_set"

        now = time.time()
        if self._last_real_traffic_at == 0.0:
            # Noch nie echter Traffic — normales Verhalten
            return self.config.rate_per_second, "normal"

        since_real = now - self._last_real_traffic_at

        if since_real < self.config.quiet_seconds_after_real:
            # Echter Traffic lief kuerzlich — drosseln, nicht stoppen
            return (
                self.config.rate_per_second * self.config.quiet_rate_factor,
                "quiet",
            )
        if since_real > self.config.boost_when_idle_seconds:
            # Lange idle — beschleunigen (max. boost_factor)
            factor = min(self.config.boost_factor, 2.0)
            return self.config.rate_per_second * factor, "boost"
        return self.config.rate_per_second, "normal"

    async def _send_reactive_burst(self) -> None:
        """Sendet Cover-Frames in Antwort auf einen Downlink-Burst.

        Anzahl und Groesse spiegeln den beobachteten Downlink, begrenzt
        durch reactive_max_match. Groesse mit +/-reactive_size_jitter
        Abweichung, damit kein 1:1-Muster entsteht.
        """
        count, avg_size = self._downlink_burst_stats()
        if count == 0:
            return

        n = min(count, self.config.reactive_max_match)
        jitter = max(0.0, min(1.0, self.config.reactive_size_jitter))

        for _ in range(n):
            # Groesse um avg_size mit Jitter
            lo = max(1, int(avg_size * (1.0 - jitter)))
            hi = max(lo, int(avg_size * (1.0 + jitter)))
            size = random.randint(lo, hi)
            msg = secrets.token_bytes(size)
            try:
                from .tunnel import FRAME_COVER
                await self.tunnel.send_typed(FRAME_COVER, msg)
                self.stats["frames_sent"] += 1
                self.stats["bytes_sent"] += size
                self.stats["reactive_frames"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                logger.debug(f"Reactive cover send error: {e}")
                return
            # 5ms zwischen Reactive-Frames — schneller als Basis-Burst
            await asyncio.sleep(0.005)

        # Window leeren, damit der naechste Burst nicht doppelt reagiert
        self._downlink_events.clear()
        self.stats["reactive_bursts"] += 1

    async def _run_loop(self) -> None:
        mode = self.config.mode
        try:
            while self._running:
                # Reactive Drop-Cover: hat Vorrang vor dem normalen Loop.
                # Wenn Downlink-Burst vorliegt, senden wir die Antwort und
                # fahren dann mit dem normalen Rhythmus fort.
                if self.config.reactive and self._running:
                    cnt, _ = self._downlink_burst_stats()
                    if cnt > 0:
                        await self._send_reactive_burst()

                rate, phase = self._effective_rate()

                if phase == "quiet" and self.config.adaptive:
                    self.stats["quiet_phases"] += 1
                elif phase == "boost" and self.config.adaptive:
                    self.stats["boost_phases"] += 1
                elif phase == "small_set" and self.config.adaptive:
                    self.stats["small_set_phases"] += 1

                if mode == "burst":
                    for _ in range(self.config.burst_size):
                        if not self._running:
                            return
                        try:
                            await self._send_one()
                        except Exception as e:
                            self.stats["errors"] += 1
                            logger.debug(f"Cover send error: {e}")
                            return
                        await asyncio.sleep(0.02)
                    # Pause skaliert invers zur Rate
                    base_pause = self.config.burst_pause_seconds
                    if rate > 0:
                        pause = base_pause * (
                            self.config.rate_per_second / rate
                        )
                    else:
                        pause = base_pause
                    await asyncio.sleep(pause)
                elif mode == "constant":
                    interval = 1.0 / max(rate, 0.001)
                    await asyncio.sleep(interval)
                    try:
                        await self._send_one()
                    except Exception as e:
                        self.stats["errors"] += 1
                        logger.debug(f"Cover send error: {e}")
                        return
                else:  # poisson
                    delay = random.expovariate(max(rate, 0.001))
                    await asyncio.sleep(delay)
                    try:
                        await self._send_one()
                    except Exception as e:
                        self.stats["errors"] += 1
                        logger.debug(f"Cover send error: {e}")
                        return
        except asyncio.CancelledError:
            pass

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime_seconds(self) -> float:
        if self.stats["started_at"] == 0:
            return 0.0
        return time.time() - self.stats["started_at"]

    def notify_real_traffic(self) -> None:
        """Signalisiert echten Traffic — Injector drosselt temporaer.

        Wird vom Proxy nach jedem echten tunnel.send() aufgerufen.
        Im adaptiven Modus fuehrt das zu einer reduzierten Cover-Rate
        (nicht zu Null — sonst waere "Stille" selbst ein Fingerprint).
        """
        self._last_real_traffic_at = time.time()

    def notify_downlink(self, size: int) -> None:
        """Signalisiert eingehenden Downlink-Traffic.

        Wird vom tunnel_to_client-Loop des Proxys nach jedem
        tunnel.receive() aufgerufen. Im reactive-Modus loest das
        einen Cover-Burst aus, der die Downlink-Form spiegelt.
        """
        self._downlink_events.append((time.time(), max(0, int(size))))

    def _trim_downlink_window(self, now: float) -> None:
        """Entfernt Events ausserhalb des Sliding Windows."""
        window_s = self.config.reactive_window_ms / 1000.0
        cutoff = now - window_s
        while self._downlink_events and self._downlink_events[0][0] < cutoff:
            self._downlink_events.popleft()

    def _downlink_burst_stats(self) -> tuple[int, int]:
        """Gibt (count, avg_size) der Downlink-Events im aktuellen Window.

        Leert dabei das Window NICHT — der Aufrufer entscheidet, ob er
        cleart. Fuer den Reactive-Burst nutzen wir den Snapshot und
        leeren danach.
        """
        self._trim_downlink_window(time.time())
        events = list(self._downlink_events)
        if not events:
            return 0, 0
        total_size = sum(s for _, s in events)
        return len(events), total_size // len(events)

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "running": self._running,
            "mode": self.config.mode,
            "adaptive": self.config.adaptive,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "rate_per_second": self.config.rate_per_second,
            "anonymity_set_size": self._current_anonymity_set_size(),
            "anonymity_threshold": self.config.anonymity_threshold,
            "seconds_since_real_traffic": (
                round(time.time() - self._last_real_traffic_at, 2)
                if self._last_real_traffic_at > 0
                else None
            ),
        }

