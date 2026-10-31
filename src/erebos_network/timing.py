"""Timing-Recorder fuer den Tunnel-Aufbau (Onboarding-Visualisierung)."""

import time
import threading
from typing import Dict, List, Optional


class TimingRecorder:
    """Zeichnet Schritte mit Zeitstempeln auf (thread-safe)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._start: Optional[float] = None
        self._steps: List[Dict] = []

    def start(self) -> None:
        with self._lock:
            self._start = time.perf_counter()
            self._steps = []

    def mark(self, name: str, detail: str = "") -> float:
        """Zeichnet einen Schritt auf. Gibt die relative Zeit (ms) zurueck."""
        with self._lock:
            if self._start is None:
                self._start = time.perf_counter()
            t = (time.perf_counter() - self._start) * 1000.0
            self._steps.append({
                "name": name,
                "detail": detail,
                "ms": round(t, 2),
            })
            return t

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "total_ms": self._steps[-1]["ms"] if self._steps else 0,
                "steps": list(self._steps),
            }

    def reset(self) -> None:
        with self._lock:
            self._start = None
            self._steps = []


# Globale Instanz (vom Proxy + Hidden-Service genutzt)
_recorder = TimingRecorder()


def get_recorder() -> TimingRecorder:
    return _recorder
