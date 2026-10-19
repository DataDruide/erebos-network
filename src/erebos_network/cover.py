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
    # Kalibriert aus echten HTTP-Burst-Daten (v0.4.2):
    #   Frame-Groessen: p10=27B, p90=7008B, Median=2928B
    #   Burst-Groessen: Median=4, p95=86
    #   Burst-Pausen: Median=108ms
    #   Intra-Burst: Median=0.24ms (wir runden auf 1ms fuer asyncio)
    min_size: int = 64         # p10 (auf 64 gerundet)
    max_size: int = 7008       # p90
    constant: bool = False
    mode: str = "poisson"
    burst_size: int = 4        # Median frames/burst
    burst_pause_seconds: float = 0.108  # Median inter-burst pause
    inter_packet_ms: int = 1   # Intra-Burst-Intervall (Median=0.24ms, gerundet)

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

    @classmethod
    def for_profile(cls, profile: str) -> "CoverConfig":
        """Erzeugt eine CoverConfig fuer ein Traffic-Profil.

        Profile basieren auf drei Messungen (siehe SECURITY.md):
          - "web":   Text/Nachrichten (S1: 4 Frames/Burst, 7008 B p90)
          - "video": Video/Social   (S2: 10 Frames/Burst, 4048 B p90)
          - "api":   HTTP-only/curl (S3: 3 Frames/Burst, 8609 B p90)

        Raises:
            ValueError: bei unbekanntem Profil.
        """
        profiles = {
            "web": dict(
                mode="burst",
                burst_size=4,
                burst_pause_seconds=0.108,
                min_size=64,
                max_size=7008,
                inter_packet_ms=1,
                reactive_window_ms=276,
                reactive_max_match=86,
                reactive_size_jitter=0.5,
            ),
            "video": dict(
                mode="burst",
                burst_size=10,
                burst_pause_seconds=0.073,
                min_size=64,
                max_size=4048,
                inter_packet_ms=1,
                reactive_window_ms=468,
                reactive_max_match=207,
                reactive_size_jitter=0.5,
            ),
            "api": dict(
                mode="burst",
                burst_size=3,
                burst_pause_seconds=0.156,
                min_size=64,
                max_size=8609,
                inter_packet_ms=1,
                reactive_window_ms=74,
                reactive_max_match=20,
                reactive_size_jitter=0.5,
            ),
        }
        if profile not in profiles:
            raise ValueError(
                f"Unbekanntes Profil: {profile!r}. "
                f"Bekannt: {sorted(profiles)}"
            )
        return cls(**profiles[profile])

    # Reactive Drop-Cover (P1.3 / Nym-Lehre):
    # Zusaetzlicher Cover-Burst als Reaktion auf Downlink-Traffic.
    # Ziel: Downlink-Uplink-Asymmetrie verwischen, damit ein Beobachter,
    # der beide Seiten sieht, nicht "Stille = Client" ableiten kann.
    reactive: bool = False
    reactive_window_ms: int = 276     # 2x mittlere Burst-Dauer (138ms)
    reactive_max_match: int = 86      # p95 frames/burst
    reactive_size_jitter: float = 0.5 # aus p90/Median-Verhaeltnis


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

class CoverProfileDetector:
    """Erkennt das Traffic-Profil anhand von Downlink-Frame-Groessen.

    Heuristik (aus den drei Messungen S1/S2/S3):
      - video: median_size < 1500 B (viele kleine Frames)
      - api:   median_size > 3000 B (wenige grosse Frames)
      - web:   sonst (mittlere Frames)

    Defensiv: Bei weniger als 10 Frames wird "web" zurueckgegeben.
    """

    def __init__(self, window_size: int = 50):
        from collections import deque
        self._sizes = deque(maxlen=window_size)
        self._last_detected = None

    def notify_downlink(self, size: int) -> None:
        """Meldet einen Downlink-Frame (Groesse in Bytes)."""
        self._sizes.append(size)

    def detect(self) -> str:
        """Gibt das erkannte Profil zurueck: 'web', 'video' oder 'api'.

        Schwellen (angepasst nach example.com-Test, 933 B -> web):
          - video: < 800 B
          - web:   800-2000 B
          - api:   > 2000 B
        """
        from statistics import median as _median
        if len(self._sizes) < 10:
            changed = False  # Kein Wechsel, solange zu wenig Daten
            self._last_detected = "web"
            return "web", changed
        m = _median(self._sizes)
        if m < 800:
            result = "video"
        elif m > 2000:
            result = "api"
        else:
            result = "web"
        changed = (result != self._last_detected)
        self._last_detected = result
        return result, changed

    def last_detected(self) -> str:
        """Gibt das zuletzt erkannte Profil zurueck (oder 'web')."""
        return self._last_detected or "web"

    def stats(self) -> dict:
        from statistics import median as _median
        return {
            "window_size": len(self._sizes),
            "median_size": int(_median(self._sizes)) if self._sizes else 0,
            "detected": self.detect()[0],
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
        auto_profile: bool = False,
        detector=None,
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
        self.auto_profile = auto_profile
        self._detector = detector or (CoverProfileDetector() if auto_profile else None)
        if self._detector is not None:
            self._current_profile = self._detector.last_detected()
        else:
            self._current_profile = "web"
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
            await asyncio.sleep(self.config.inter_packet_ms / 1000.0)

        # Window leeren, damit der naechste Burst nicht doppelt reagiert
        self._downlink_events.clear()
        self.stats["reactive_bursts"] += 1

    async def _run_loop(self) -> None:
        mode = self.config.mode
        try:
            while self._running:
                # Auto-Profil-Erkennung (experimentell):
                # Wenn --auto-profile gesetzt ist, pruefen wir bei jedem
                # Zyklus, ob der Detector ein anderes Profil erkennt.
                if self._detector is not None:
                    detected, changed = self._detector.detect()
                    if changed:
                        logger.info(
                            f"Auto-Profil gewechselt: {detected} "
                            f"(window={self._detector.stats()['window_size']}, "
                            f"median={self._detector.stats()['median_size']}B)"
                        )
                        profile_cfg = CoverConfig.for_profile(detected)
                        self.config.burst_size = profile_cfg.burst_size
                        self.config.burst_pause_seconds = profile_cfg.burst_pause_seconds
                        self.config.min_size = profile_cfg.min_size
                        self.config.max_size = profile_cfg.max_size
                        self.config.reactive_max_match = profile_cfg.reactive_max_match
                        self.stats["auto_profile_changes"] = (
                            self.stats.get("auto_profile_changes", 0) + 1
                        )

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
                        await asyncio.sleep(self.config.inter_packet_ms / 1000.0)
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
        if self._detector is not None:
            self._detector.notify_downlink(size)

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
            "auto_profile": self.auto_profile,
            "auto_profile_current": self._current_profile,
            "auto_profile_changes": self.stats.get("auto_profile_changes", 0),
            "anonymity_set_size": self._current_anonymity_set_size(),
            "anonymity_threshold": self.config.anonymity_threshold,
            "seconds_since_real_traffic": (
                round(time.time() - self._last_real_traffic_at, 2)
                if self._last_real_traffic_at > 0
                else None
            ),
        }

