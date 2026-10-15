#!/usr/bin/env python3
"""Exportiert die aktuelle Peer-Topologie aus der DHT.

Dieses Skript verbindet sich über Bootstrap-Peers mit dem Netzwerk,
liest die Routing-Tabelle aus und schreibt die Kantenliste in eine
Datei, die von analyze_topology.py gelesen werden kann.

Usage:
    python scripts/dump_topology.py --output peer_list.txt
    python scripts/dump_topology.py --bootstrap 127.0.0.1:9999
    python scripts/dump_topology.py --use-addresses
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# src/ zum sys.path hinzufügen (auch ohne pip install -e .)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from erebos_network.discovery import DiscoveryConfig, PeerDiscovery


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("peer_list.txt"),
        help="Ausgabedatei (Default: peer_list.txt)",
    )
    parser.add_argument(
        "--bootstrap", action="append", default=[],
        help="Bootstrap-Peer (mehrfach angebbar)",
    )
    parser.add_argument(
        "--use-addresses", action="store_true",
        help="Peer-Adressen statt Peer-IDs nutzen",
    )
    parser.add_argument(
        "--own-address", default="127.0.0.1:9999",
        help="Eigene Adresse (Default: 127.0.0.1:9999)",
    )
    args = parser.parse_args()

    discovery = PeerDiscovery(
        own_address=args.own_address,
        config=DiscoveryConfig(bootstrap_peers=args.bootstrap),
    )
    added = discovery.bootstrap()
    print(f"Bootstrap: {added} Peers hinzugefügt")

    edges = discovery.export_topology(use_addresses=args.use_addresses)
    print(f"Exportiere {len(edges)} Kanten nach {args.output}")

    if not edges:
        print("[!] Keine Peers — schreibe leere Topologie")
        args.output.write_text("# leere Topologie\n")
        return 0

    lines = ["# Erebos Peer-Topologie (exportiert)"]
    for a, b in edges:
        lines.append(f"{a} {b}")
    args.output.write_text("\n".join(lines) + "\n")
    print(f"OK: {len(edges)} Kanten geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
