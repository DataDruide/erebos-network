#!/usr/bin/env python3
"""Erebos Topology Analysis: Betweenness Centrality & Degree-Verteilung."""
from pathlib import Path

try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    _HAS_NX = False

PEER_FILE = Path("peer_list.txt")


def load_topology(path: Path) -> "nx.Graph":
    G = nx.Graph()
    if not path.exists():
        print(f"[!] {path} nicht gefunden. Nutze Beispiel-Topologie.")
        G.add_edges_from([
            ("peer1", "peer2"), ("peer1", "peer3"), ("peer1", "peer4"),
            ("peer2", "peer5"), ("peer3", "peer6"),
        ])
        return G
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            parts = line.split()
            if len(parts) >= 2:
                G.add_edge(parts[0], parts[1])
    return G


def analyze(G: "nx.Graph") -> dict:
    print(f"[*] Topologie: {G.number_of_nodes()} Peers, {G.number_of_edges()} Verbindungen")
    bc = nx.betweenness_centrality(G, normalized=True)
    print("\n[!] Kritische Peers (Betweenness Centrality):")
    critical = []
    for peer, score in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:10]:
        marker = "  <-- KRITISCH" if score > 0.3 else ""
        print(f"    {peer}: {score:.4f}{marker}")
        if score > 0.3:
            critical.append(peer)
    print("\n[*] Degree-Verteilung (Top 5):")
    for peer, deg in sorted(G.degree(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"    {peer}: {deg} Verbindungen")
    if critical:
        print(f"\n[!] WARNUNG: {len(critical)} kritische Brücken-Peers.")
        print("    Härtung: Redundante Pfade aufbauen, dynamische Peer-Rotation.")
    return {"betweenness": bc, "critical": critical}


if __name__ == "__main__":
    if not _HAS_NX:
        raise SystemExit("networkx fehlt: python3 -m pip install networkx")
    analyze(load_topology(PEER_FILE))
