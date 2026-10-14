"""Tests für scripts/analyze_topology.py."""
import sys
from pathlib import Path

import pytest

# scripts/ zum Import-Pfad hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

pytestmark = pytest.mark.skipif(not HAS_NX, reason="networkx fehlt")


def test_load_synthetic_topology():
    """Synthetische Topologie lädt 6 Peers, 7 Kanten."""
    from analyze_topology import load_topology
    G = load_topology(Path("/nonexistent"), synthetic=True)
    assert G.number_of_nodes() == 6
    assert G.number_of_edges() == 7


def test_load_peer_file(tmp_path):
    """peer_list.txt wird korrekt geparst."""
    from analyze_topology import load_topology
    peer_file = tmp_path / "peers.txt"
    peer_file.write_text(
        "# Kommentar\n"
        "a b\n"
        "b c\n"
        "\n"
        "c d\n"
    )
    G = load_topology(peer_file)
    assert G.number_of_nodes() == 4
    assert G.number_of_edges() == 3


def test_missing_file_falls_back(tmp_path):
    """Fehlende Datei → Beispiel-Topologie."""
    from analyze_topology import load_topology
    G = load_topology(tmp_path / "missing.txt")
    assert G.number_of_nodes() == 6


def test_analyze_detects_spof():
    """Stern-Topologie: Zentrum hat BC=1.0."""
    from analyze_topology import analyze
    G = nx.Graph()
    G.add_edges_from([("hub", "a"), ("hub", "b"), ("hub", "c")])
    metrics = analyze(G, warn_above=0.5)
    assert "hub" in metrics["critical"]
    assert metrics["betweenness"]["hub"] == 1.0


def test_analyze_no_critical_simple_edge():
    """Zwei Peers: BC=0 für beide."""
    from analyze_topology import analyze
    G = nx.Graph()
    G.add_edge("a", "b")
    metrics = analyze(G, warn_above=0.3)
    assert metrics["critical"] == []


def test_analyze_degree_distribution():
    """Degree-Verteilung korrekt."""
    from analyze_topology import analyze
    G = nx.Graph()
    G.add_edges_from([("hub", "a"), ("hub", "b"), ("hub", "c")])
    metrics = analyze(G, warn_above=0.5)
    assert metrics["degrees"]["hub"] == 3
    assert metrics["degrees"]["a"] == 1


def test_peer_list_baseline_loaded():
    """Die eingecheckte peer_list.txt wird geladen."""
    from analyze_topology import load_topology
    peer_file = Path(__file__).parent.parent / "peer_list.txt"
    assert peer_file.exists(), "peer_list.txt muss eingecheckt sein"
    G = load_topology(peer_file)
    assert G.number_of_nodes() >= 5
    assert G.number_of_edges() >= 5
