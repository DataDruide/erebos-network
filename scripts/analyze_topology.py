#!/usr/bin/env python3
"""Erebos Topology Analysis.

Berechnet Betweenness Centrality und Degree-Verteilung für die
Peer-Topologie. Warnt bei kritischen Brücken-Peers (SPOF).

Usage:
    python scripts/analyze_topology.py
    python scripts/analyze_topology.py --peer-file custom.txt
    python scripts/analyze_topology.py --fail-above 0.9
    python scripts/analyze_topology.py --synthetic
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False

# Beispiel-Topologie (3-Hop-Onion + Redundanz-Peers)
# 6 Peers, 7 Kanten — reproduzierbar und deterministisch.
SYNTHETIC_EDGES = [
    ("peer1", "peer2"),
    ("peer2", "peer3"),
    ("peer1", "peer4"),
    ("peer2", "peer4"),
    ("peer3", "peer5"),
    ("peer3", "peer6"),
    ("peer4", "peer5"),
]


def load_topology(path: Path, synthetic: bool = False) -> "nx.Graph":
    """Lädt Peer-Topologie aus Datei oder Beispiel.

    Args:
        path: Pfad zu peer_list.txt (Format: 'peer_a peer_b' pro Zeile).
        synthetic: Bei True wird die Beispiel-Topologie erzwungen.

    Returns:
        Ungerichteter networkx-Graph.
    """
    G = nx.Graph()

    if synthetic or not path.exists():
        if not synthetic:
            print(f"[!] {path} nicht gefunden, nutze Beispiel-Topologie.")
        else:
            print(f"[*] Nutze synthetische Topologie.")
        G.add_edges_from(SYNTHETIC_EDGES)
        return G

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            G.add_edge(parts[0], parts[1])
    return G


def simulate_topology(
    pool: list[str],
    strategy: str = "random",
    iterations: int = 1000,
) -> "nx.Graph":
    """Simuliert die ECHTE Topologie mit gegebener Peer-Auswahl-Strategie.

    Jede Iteration wählt 3 Hops aus dem Pool und fügt die Kanten hinzu.
    Ergebnis: Netzwerk-Graph, wie er in echter Nutzung entsteht.

    Args:
        pool: Liste von Peer-Namen.
        strategy: "first" | "random" | "round_robin"
        iterations: Anzahl simulierter Verbindungen.

    Returns:
        networkx-Graph (Multi-Edge auf denselben Peer wird dedupliziert).
    """
    from erebos_network.proxy import select_three_hops

    G = nx.Graph()
    for peer in pool:
        G.add_node(peer)
    for i in range(iterations):
        offset = i if strategy == "round_robin" else 0
        hops = select_three_hops(pool, strategy, offset)
        G.add_edge(hops[0], hops[1])
        G.add_edge(hops[1], hops[2])
    return G


def simulate_usage(
    pool: list[str],
    strategy: str = "random",
    iterations: int = 1000,
) -> dict:
    """Simuliert die NUTZUNG (nicht nur den Graph).

    Zählt, wie oft jeder Peer als Entry/Relay/Exit dient.
    Das ist das echte Maß für SPOF in der Nutzung.

    Returns:
        Dict mit entry_counts, relay_counts, exit_counts, edge_counts.
    """
    from erebos_network.proxy import select_three_hops
    from collections import Counter

    entries: Counter = Counter()
    relays: Counter = Counter()
    exits: Counter = Counter()
    edges: Counter = Counter()

    for i in range(iterations):
        offset = i if strategy == "round_robin" else 0
        hops = select_three_hops(pool, strategy, offset)
        entries[hops[0]] += 1
        relays[hops[1]] += 1
        exits[hops[2]] += 1
        edges[(hops[0], hops[1])] += 1
        edges[(hops[1], hops[2])] += 1

    return {
        "entry_counts": dict(entries),
        "relay_counts": dict(relays),
        "exit_counts": dict(exits),
        "edge_counts": dict(edges),
        "iterations": iterations,
        "strategy": strategy,
        "pool": list(pool),
    }


def analyze_usage(usage: dict, warn_above: float = 0.5) -> dict:
    """Analysiert Nutzungsverteilung.

    Metrik: max Entry-Anteil (Single Point of Failure).
    warn_above: Schwellwert für Warnung (Default: 0.5 = 50%).
    """
    pool = usage["pool"]
    iterations = usage["iterations"]
    entries = usage["entry_counts"]

    print(f"[*] Nutzungs-Simulation: {len(pool)} Peers, "
          f"{iterations} Verbindungen, strategy={usage['strategy']}")
    print()
    print("[!] Entry-Verteilung (SPOF-Maß):")
    critical = []
    for peer in pool:
        count = entries.get(peer, 0)
        ratio = count / iterations if iterations else 0.0
        marker = "  <-- SPOF" if ratio > warn_above else ""
        bar = "#" * int(ratio * 40)
        print(f"    {peer}: {ratio:6.2%} {bar}{marker}")
        if ratio > warn_above:
            critical.append(peer)

    # Relay + Exit kurz
    print()
    print("[*] Relay-Verteilung (Top 3):")
    for peer, count in sorted(
        usage["relay_counts"].items(), key=lambda x: x[1], reverse=True
    )[:3]:
        ratio = count / iterations if iterations else 0.0
        print(f"    {peer}: {ratio:6.2%}")

    return {
        "entry_counts": entries,
        "relay_counts": usage["relay_counts"],
        "exit_counts": usage["exit_counts"],
        "critical": critical,
        "warn_above": warn_above,
        "iterations": iterations,
        "pool": pool,
        "strategy": usage["strategy"],
    }


def analyze(G: "nx.Graph", warn_above: float = 0.3) -> dict:
    """Analysiert Topologie.

    Args:
        G: networkx-Graph
        warn_above: BC-Schwellwert für Warnung.

    Returns:
        Dict mit betweenness, degree, critical, warn.
    """
    print(f"[*] Topologie: {G.number_of_nodes()} Peers, "
          f"{G.number_of_edges()} Verbindungen")

    bc = nx.betweenness_centrality(G, normalized=True)
    print("\n[!] Kritische Peers (Betweenness Centrality):")
    critical = []
    for peer, score in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:10]:
        marker = "  <-- KRITISCH" if score > warn_above else ""
        print(f"    {peer}: {score:.4f}{marker}")
        if score > warn_above:
            critical.append(peer)

    print("\n[*] Degree-Verteilung (Top 5):")
    degrees = {}
    for peer, deg in sorted(G.degree(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"    {peer}: {deg} Verbindungen")
        degrees[peer] = deg

    return {
        "betweenness": bc,
        "degrees": degrees,
        "critical": critical,
        "warn_above": warn_above,
    }


def write_github_summary(metrics: dict) -> None:
    """Schreibt Markdown-Summary in $GITHUB_STEP_SUMMARY."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with open(summary_path, "a") as f:
        f.write("## Erebos Topology Analysis\n\n")
        f.write(f"**Kritische Peers (BC > {metrics['warn_above']}):** "
                f"{len(metrics['critical'])}\n\n")
        f.write("| Peer | BC |\n|---|---|\n")
        for peer, bc in sorted(
            metrics["betweenness"].items(), key=lambda x: x[1], reverse=True
        )[:10]:
            marker = " ⚠️" if bc > metrics["warn_above"] else ""
            f.write(f"| {peer} | {bc:.4f}{marker} |\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--peer-file",
        type=Path,
        default=Path("peer_list.txt"),
        help="Peer-Topologie-Datei (Default: peer_list.txt)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Erzwingt synthetische Topologie",
    )
    parser.add_argument(
        "--warn-above",
        type=float,
        default=0.3,
        help="BC-Schwellwert für Warnung (Default: 0.3)",
    )
    parser.add_argument(
        "--fail-above",
        type=float,
        default=None,
        help="Exit-Code 1, wenn ein Peer BC > fail-above hat",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Simuliert echte Nutzung statt Datei zu lesen",
    )
    parser.add_argument(
        "--pool",
        type=str,
        default="peer1,peer2,peer3,peer4,peer5",
        help="Komma-separierte Peer-Liste für --simulate",
    )
    parser.add_argument(
        "--strategy",
        choices=["first", "random", "round_robin"],
        default="random",
        help="Pfad-Auswahl-Strategie für --simulate",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="Anzahl simulierter Verbindungen (Default: 1000)",
    )
    args = parser.parse_args()

    if not _HAS_NX:
        raise SystemExit("networkx fehlt: python3 -m pip install networkx")

    if args.simulate:
        pool = [p.strip() for p in args.pool.split(",") if p.strip()]
        usage = simulate_usage(pool, args.strategy, args.iterations)
        metrics = analyze_usage(usage, warn_above=args.warn_above)

        if metrics["critical"]:
            print(f"\n[!] WARNUNG: {len(metrics['critical'])} SPOF-Peers.")
            print("    Härtung: entry_strategy='random' oder 'round_robin' setzen.")

        if args.fail_above is not None:
            worst = max(
                (c / metrics["iterations"]) for c in metrics["entry_counts"].values()
            ) if metrics["iterations"] else 0.0
            if worst > args.fail_above:
                print(f"\n[✗] FAIL: Entry max = {worst:.4f} > {args.fail_above}")
                return 1
            print(f"\n[✓] OK: Entry max = {worst:.4f} <= {args.fail_above}")
        return 0

    # Statische Analyse (Datei)
    G = load_topology(args.peer_file, synthetic=args.synthetic)
    metrics = analyze(G, warn_above=args.warn_above)
    write_github_summary(metrics)

    if metrics["critical"]:
        print(f"\n[!] WARNUNG: {len(metrics['critical'])} kritische Brücken-Peers.")
        print("    Härtung: Redundante Pfade aufbauen, dynamische Peer-Rotation.")

    if args.fail_above is not None:
        worst = max(metrics["betweenness"].values()) if metrics["betweenness"] else 0.0
        if worst > args.fail_above:
            print(f"\n[✗] FAIL: BC max = {worst:.4f} > {args.fail_above}")
            return 1
        print(f"\n[✓] OK: BC max = {worst:.4f} <= {args.fail_above}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
