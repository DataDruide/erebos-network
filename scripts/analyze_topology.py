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
    args = parser.parse_args()

    if not _HAS_NX:
        raise SystemExit("networkx fehlt: python3 -m pip install networkx")

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
