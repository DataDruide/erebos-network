"""Pure helpers for path selection.

Diese Funktionen sind bewusst krypto-frei. Sie können auch in
Umgebungen importiert werden, in denen `cryptography` nicht
installiert ist — z.B. im Topology-CI-Job, der nur `networkx`
braucht.

Kein Import aus `proxy`, `tunnel`, `onion` oder `crypto`.
"""
from __future__ import annotations

import random
from typing import List


def select_three_hops(
    pool: List[str],
    strategy: str = "random",
    offset: int = 0,
) -> List[str]:
    """Wählt 3 Peers aus dem Pool (pure function, ohne Keys).

    Args:
        pool: Liste von Peer-Namen (mind. 3 für sinnvolle Auswahl).
        strategy: "first" | "random" | "round_robin"
        offset: Nur für "round_robin" (aktuelle Position).

    Returns:
        Liste mit genau 3 Peer-Namen.

    Bei strategy="first" oder Pool < 3 wird pool[:3] zurückgegeben
    (Backward-Compat-Verhalten).
    """
    if strategy == "first" or len(pool) < 3:
        return pool[:3]
    if strategy == "random":
        return random.sample(pool, 3)
    if strategy == "round_robin":
        return [pool[(offset + i) % len(pool)] for i in range(3)]
    # Unbekannte Strategie: Fallback auf "first"
    return pool[:3]


__all__ = ["select_three_hops"]
