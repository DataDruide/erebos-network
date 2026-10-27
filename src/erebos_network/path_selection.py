"""Pfad-Auswahl fuer Erebos Network.

Schuetzt gegen Mixnode-Adversaere durch intelligente Pfad-Auswahl.

Basiert auf Nym-Forschung: K-HF, K/W, alpha-SS.
"""

import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MixNode:
    """Ein Mixnode im Netzwerk."""

    node_id: str
    address: str
    reputation: float = 0.5
    total_packets: int = 0
    last_seen: float = field(default_factory=time.time)
    is_adversary: bool = False  # nur fuer Simulation
    role: str = "mix"  # entry | mix | exit (aus peers.json)

    @property
    def is_trusted(self) -> bool:
        return self.reputation >= 0.7


@dataclass
class PathSelectionConfig:
    """Konfiguration fuer Pfad-Auswahl."""

    strategy: str = "alpha_ss"  # random, k_hf, k_over_w, alpha_ss
    num_hops: int = 3
    alpha: float = 0.3
    k: int = 3
    min_reputation: float = 0.3
    avoid_reuse: bool = True


class PathSelector:
    """Pfad-Auswahl mit verschiedenen Strategien.

    Strategien:
    - random: zufaellige Auswahl (Tor-Stil)
    - k_hf: K-Highest-Reputation-First
    - k_over_w: K/W (Reputation/Gewicht)
    - alpha_ss: alpha-Sub-Set (probabilistische Wiederverwendung)
    """

    def __init__(
        self,
        config: Optional[PathSelectionConfig] = None,
    ):
        self.config = config or PathSelectionConfig()
        self._recent_paths: list[list[str]] = []
        self.stats = {
            "paths_selected": 0,
            "adversary_hops": 0,
            "total_hops": 0,
        }

    def select_path(self, nodes: list[MixNode]) -> list[MixNode]:
        """Waehlt einen Pfad aus Mixnodes."""
        if len(nodes) < self.config.num_hops:
            raise ValueError(
                f"Zu wenige Nodes: {len(nodes)} < {self.config.num_hops}"
            )

        # Filtere unzuverlaessige Nodes
        candidates = [
            n for n in nodes if n.reputation >= self.config.min_reputation
        ]
        if len(candidates) < self.config.num_hops:
            candidates = nodes

        # Rollen-basierte Auswahl, falls Rollen definiert sind
        path = self._select_by_roles(candidates)
        if path is not None:
            self._recent_paths.append([n.node_id for n in path])
            if len(self._recent_paths) > 100:
                self._recent_paths.pop(0)
            self.stats["paths_selected"] += 1
            self.stats["total_hops"] += len(path)
            self.stats["adversary_hops"] += sum(1 for n in path if n.is_adversary)
            return path

        if self.config.strategy == "random":
            path = self._select_random(candidates)
        elif self.config.strategy == "k_hf":
            path = self._select_k_hf(candidates)
        elif self.config.strategy == "k_over_w":
            path = self._select_k_over_w(candidates)
        elif self.config.strategy == "alpha_ss":
            path = self._select_alpha_ss(candidates)
        else:
            path = self._select_random(candidates)

        self._recent_paths.append([n.node_id for n in path])
        if len(self._recent_paths) > 100:
            self._recent_paths.pop(0)

        self.stats["paths_selected"] += 1
        self.stats["total_hops"] += len(path)
        self.stats["adversary_hops"] += sum(
            1 for n in path if n.is_adversary
        )

        return path

    def _select_by_roles(self, nodes: list[MixNode]):
        """Wählt Pfad nach Rollen: entry -> mix... -> exit.

        Gibt None zurück, wenn keine Rollen definiert sind oder zu wenige
        Knoten einer Rolle existieren (dann greift die bisherige Strategie).
        """
        entries = [n for n in nodes if n.role == "entry"]
        mixes = [n for n in nodes if n.role == "mix"]
        exits = [n for n in nodes if n.role == "exit"]

        # Keine Rollen definiert -> Fallback auf bisherige Strategie
        if not entries and not exits:
            return None

        needed = self.config.num_hops
        # Für einen 3-Hop-Pfad: 1 entry + (needed-2) mix + 1 exit
        if needed < 2:
            return None
        if not entries or not exits:
            return None
        if len(mixes) < (needed - 2):
            return None

        try:
            path = [random.choice(entries)]
            path.extend(random.sample(mixes, needed - 2))
            path.append(random.choice(exits))
            return path
        except ValueError:
            return None

    def _select_random(self, nodes: list[MixNode]) -> list[MixNode]:
        """Zufaellige Auswahl."""
        return random.sample(nodes, self.config.num_hops)

    def _select_k_hf(self, nodes: list[MixNode]) -> list[MixNode]:
        """K-Highest-Reputation-First.

        Waehlt die K Nodes mit hoechster Reputation,
        dann zufaellig daraus.
        """
        sorted_nodes = sorted(
            nodes, key=lambda n: n.reputation, reverse=True
        )
        top_k = sorted_nodes[: max(self.config.k * 3, self.config.num_hops)]
        return random.sample(top_k, self.config.num_hops)

    def _select_k_over_w(self, nodes: list[MixNode]) -> list[MixNode]:
        """K/W Strategie.

        Waehlt mit Wahrscheinlichkeit proportional zur Reputation.
        """
        selected = []
        available = nodes.copy()

        for _ in range(self.config.num_hops):
            if not available:
                break
            weights = [n.reputation for n in available]
            total = sum(weights)
            if total == 0:
                chosen = random.choice(available)
            else:
                probs = [w / total for w in weights]
                chosen = random.choices(available, weights=probs, k=1)[0]
            selected.append(chosen)
            available.remove(chosen)

        return selected

    def _select_alpha_ss(self, nodes: list[MixNode]) -> list[MixNode]:
        """alpha-SS (Alpha-Sub-Set).

        Probabilistische Wiederverwendung: Mit Wahrscheinlichkeit
        alpha werden bereits verwendete Nodes wiederverwendet.
        """
        if (
            self.config.avoid_reuse
            and self._recent_paths
            and random.random() < self.config.alpha
        ):
            # Wiederverwendung: nimm einen kuerzlich verwendeten Pfad
            recent = random.choice(self._recent_paths)
            return [
                n for n in nodes if n.node_id in recent
            ][: self.config.num_hops]

        # Sonst: K-Highest-Reputation
        return self._select_k_hf(nodes)

    def get_stats(self) -> dict:
        """Statistiken."""
        adversary_ratio = 0.0
        if self.stats["total_hops"] > 0:
            adversary_ratio = (
                self.stats["adversary_hops"] / self.stats["total_hops"]
            )
        return {
            **self.stats,
            "adversary_ratio": round(adversary_ratio, 4),
            "recent_paths": len(self._recent_paths),
            "strategy": self.config.strategy,
        }
