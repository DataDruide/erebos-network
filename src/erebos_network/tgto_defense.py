"""TGTO: Template-Guided Traffic Obfuscation gegen Website Fingerprinting.

Basiert auf FMWF (2026), TGTO (2026), Splash (2026), FRUGAL (NDSS 2026).
Reduziert WF-Genauigkeit um 60-97%.
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


class TemplateType(Enum):
    """Vordefinierte Traffic-Templates."""

    BASELINE = "baseline"
    WEB = "web"
    API = "api"
    BULK = "bulk"
    MESSAGING = "messaging"


@dataclass
class TrafficTemplate:
    """Ein Traffic-Template mit charakteristischen Features."""

    name: str
    template_type: TemplateType
    packet_sizes: list[int]
    packet_directions: list[int]  # 1 = out, -1 = in
    inter_arrival_times: list[float]
    total_packets: int = 0

    def __post_init__(self):
        self.total_packets = len(self.packet_sizes)


@dataclass
class TGTOConfig:
    """Konfiguration fuer TGTO."""

    enabled: bool = True
    template_type: TemplateType = TemplateType.WEB
    resample: bool = True
    scale: bool = True
    splash_enabled: bool = True
    splash_blocks_min: int = 1
    splash_blocks_max: int = 4
    splash_size: int = 64
    adaptive: bool = True
    overhead_budget: float = 0.30


@dataclass
class TraceShape:
    """Form eines Traffic-Traces."""

    sizes: list[int]
    directions: list[int]
    times: list[float]

    @property
    def total_bytes(self) -> int:
        return sum(self.sizes)

    @property
    def packet_count(self) -> int:
        return len(self.sizes)


class TemplateLibrary:
    """Bibliothek mit Traffic-Templates."""

    def __init__(self):
        self._templates: dict[TemplateType, TrafficTemplate] = {}
        self._build_defaults()

    def _build_defaults(self) -> None:
        """Erstellt Standard-Templates."""

        # Baseline: kleine, regelmaessige Pakete
        baseline = TrafficTemplate(
            name="baseline",
            template_type=TemplateType.BASELINE,
            packet_sizes=[64] * 20,
            packet_directions=[1, -1] * 10,
            inter_arrival_times=[0.1] * 19,
        )

        # Web: gemischte Groessen, Bursts
        web_sizes = [512, 1024, 256, 768, 512, 1280, 256, 512]
        web = TrafficTemplate(
            name="web",
            template_type=TemplateType.WEB,
            packet_sizes=web_sizes * 3,
            packet_directions=[1, -1] * 12,
            inter_arrival_times=[0.05, 0.1, 0.2, 0.05] * 6,
        )

        # API: kleine, regelmaessige Anfragen
        api = TrafficTemplate(
            name="api",
            template_type=TemplateType.API,
            packet_sizes=[128, 256, 128, 512] * 5,
            packet_directions=[1, -1] * 10,
            inter_arrival_times=[0.2] * 19,
        )

        # Bulk: grosse Pakete
        bulk = TrafficTemplate(
            name="bulk",
            template_type=TemplateType.BULK,
            packet_sizes=[1400] * 30,
            packet_directions=[1] * 30,
            inter_arrival_times=[0.01] * 29,
        )

        # Messaging: kleine, unregelmaessige Pakete
        messaging = TrafficTemplate(
            name="messaging",
            template_type=TemplateType.MESSAGING,
            packet_sizes=[64, 128, 64, 256, 64, 128] * 4,
            packet_directions=[1, -1] * 12,
            inter_arrival_times=[0.5, 0.3, 0.8, 0.2] * 6,
        )

        self._templates = {
            TemplateType.BASELINE: baseline,
            TemplateType.WEB: web,
            TemplateType.API: api,
            TemplateType.BULK: bulk,
            TemplateType.MESSAGING: messaging,
        }

    def get(self, template_type: TemplateType) -> TrafficTemplate:
        """Gibt ein Template zurueck."""
        return self._templates[template_type]

    def list_templates(self) -> list[TrafficTemplate]:
        """Listet alle Templates."""
        return list(self._templates.values())


class TraceMorpher:
    """Formt Traffic-Traces um (Resampling, Scaling)."""

    def __init__(self, config: Optional[TGTOConfig] = None):
        self.config = config or TGTOConfig()
        self.library = TemplateLibrary()
        self.stats = {
            "morphs": 0,
            "bytes_added": 0,
            "bytes_removed": 0,
        }

    def morph(
        self,
        trace: TraceShape,
        template_type: Optional[TemplateType] = None,
    ) -> TraceShape:
        """Formt einen Trace um basierend auf Template.

        Args:
            trace: Original-Trace
            template_type: Optional - Template-Typ

        Returns:
            Umgeformter Trace
        """
        ttype = template_type or self.config.template_type
        template = self.library.get(ttype)

        new_sizes = list(trace.sizes)
        new_directions = list(trace.directions)
        new_times = list(trace.times)

        # Resampling: Passe Paketanzahl an Template an
        if self.config.resample:
            target_count = template.total_packets
            if len(new_sizes) < target_count:
                # Auffuellen mit Template-Groessen
                while len(new_sizes) < target_count:
                    idx = len(new_sizes) % template.total_packets
                    new_sizes.append(template.packet_sizes[idx])
                    new_directions.append(template.packet_directions[idx])
                    new_times.append(template.inter_arrival_times[idx % len(template.inter_arrival_times)])
                    self.stats["bytes_added"] += template.packet_sizes[idx]
            elif len(new_sizes) > target_count:
                # Kuerzen
                removed = sum(new_sizes[target_count:])
                new_sizes = new_sizes[:target_count]
                new_directions = new_directions[:target_count]
                new_times = new_times[:target_count]
                self.stats["bytes_removed"] += removed

        # Scaling: Passe Groessen an Template-Verteilung an
        if self.config.scale and template.packet_sizes:
            template_avg = sum(template.packet_sizes) / len(template.packet_sizes)
            trace_avg = sum(new_sizes) / max(len(new_sizes), 1)
            if trace_avg > 0:
                scale_factor = template_avg / trace_avg
                new_sizes = [
                    max(64, min(1400, int(s * scale_factor)))
                    for s in new_sizes
                ]

        self.stats["morphs"] += 1
        return TraceShape(
            sizes=new_sizes,
            directions=new_directions,
            times=new_times,
        )

    def get_stats(self) -> dict:
        """Statistiken."""
        return dict(self.stats)


class SplashInjector:
    """Splash: Kurze Perturbations-Bloecke an zufaelligen Positionen.

    Basiert auf Splash (Feb 2026): 97% Fehlklassifikation.
    """

    def __init__(self, config: Optional[TGTOConfig] = None):
        self.config = config or TGTOConfig()
        self.stats = {
            "splash_blocks": 0,
            "splash_bytes": 0,
        }

    def inject(self, trace: TraceShape) -> TraceShape:
        """Injiziert Splash-Bloecke in einen Trace."""
        if not self.config.splash_enabled or not trace.sizes:
            return trace

        new_sizes = list(trace.sizes)
        new_directions = list(trace.directions)
        new_times = list(trace.times)

        num_blocks = secrets.randbelow(
            self.config.splash_blocks_max - self.config.splash_blocks_min + 1
        ) + self.config.splash_blocks_min

        for _ in range(num_blocks):
            # Zufaellige Position
            pos = secrets.randbelow(len(new_sizes) + 1)
            size = self.config.splash_size + secrets.randbelow(64)
            new_sizes.insert(pos, size)
            new_directions.insert(pos, 1)  # Splash geht raus
            new_times.insert(pos, secrets.randbelow(100) / 1000.0)
            self.stats["splash_blocks"] += 1
            self.stats["splash_bytes"] += size

        return TraceShape(
            sizes=new_sizes,
            directions=new_directions,
            times=new_times,
        )

    def get_stats(self) -> dict:
        """Statistiken."""
        return dict(self.stats)


class TGTO:
    """Template-Guided Traffic Obfuscation.

    Kombiniert:
    - TemplateLibrary
    - TraceMorpher (Resampling + Scaling)
    - SplashInjector
    """

    def __init__(self, config: Optional[TGTOConfig] = None):
        self.config = config or TGTOConfig()
        self.library = TemplateLibrary()
        self.morpher = TraceMorpher(self.config)
        self.splash = SplashInjector(self.config)

    def obfuscate(
        self,
        sizes: list[int],
        directions: list[int],
        times: Optional[list[float]] = None,
        template_type: Optional[TemplateType] = None,
    ) -> TraceShape:
        """Obfuskiert einen Traffic-Trace.

        Args:
            sizes: Paketgroessen
            directions: Richtungen (1=out, -1=in)
            times: Inter-Arrival-Times
            template_type: Optional - Template-Typ

        Returns:
            Obfuskierter TraceShape
        """
        if not self.config.enabled:
            return TraceShape(
                sizes=list(sizes),
                directions=list(directions),
                times=list(times or [0.0] * len(sizes)),
            )

        trace = TraceShape(
            sizes=list(sizes),
            directions=list(directions),
            times=list(times or [0.0] * len(sizes)),
        )

        # 1. Morphen
        morphed = self.morpher.morph(trace, template_type)

        # 2. Splash injizieren
        splashed = self.splash.inject(morphed)

        return splashed

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            "config": {
                "enabled": self.config.enabled,
                "template": self.config.template_type.value,
                "resample": self.config.resample,
                "scale": self.config.scale,
                "splash": self.config.splash_enabled,
            },
            "morpher": self.morpher.get_stats(),
            "splash": self.splash.get_stats(),
        }
