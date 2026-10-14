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


# ---------------------------------------------------------------------------
# Simulation (echte Nutzung mit Pfad-Rotation)
# ---------------------------------------------------------------------------

def test_select_three_hops_pure_function_first():
    """Freie Funktion: 'first' liefert pool[:3]."""
    from erebos_network.topology_utils import select_three_hops
    assert select_three_hops(["a", "b", "c", "d"], "first") == ["a", "b", "c"]


def test_select_three_hops_pure_function_random():
    """Freie Funktion: 'random' liefert 3 unterschiedliche Peers."""
    from erebos_network.topology_utils import select_three_hops
    hops = select_three_hops(["a", "b", "c", "d", "e"], "random")
    assert len(hops) == 3
    assert len(set(hops)) == 3


def test_select_three_hops_pure_function_round_robin():
    """Freie Funktion: 'round_robin' rotiert deterministisch."""
    from erebos_network.topology_utils import select_three_hops
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 0) == ["a", "b", "c"]
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 1) == ["b", "c", "d"]
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 3) == ["d", "a", "b"]


def test_simulate_topology_5peers():
    """Simulation erzeugt Graph mit 5 Peers."""
    from analyze_topology import simulate_topology
    pool = ["a", "b", "c", "d", "e"]
    G = simulate_topology(pool, "random", iterations=100)
    assert G.number_of_nodes() == 5
    assert G.number_of_edges() >= 5  # mind. so viele wie nötig


def test_simulate_random_bc_below_threshold():
    """Random-Rotation: BC max < 0.5."""
    from analyze_topology import simulate_topology, analyze
    pool = ["a", "b", "c", "d", "e"]
    G = simulate_topology(pool, "random", iterations=1000)
    metrics = analyze(G, warn_above=0.3)
    worst = max(metrics["betweenness"].values())
    assert worst < 0.5, f"BC max = {worst:.4f} (erwartet < 0.5)"


def test_simulate_first_creates_entry_spof():
    """'first' ohne Rotation: peer1 ist IMMER Entry (SPOF).

    Hinweis: BC auf ungewichtetem Graph ist hier nicht das richtige Maß,
    weil networkx identische Kanten dedupliziert. Stattdessen messen wir
    die Entry-Verteilung — das ist der echte SPOF.
    """
    from collections import Counter
    from erebos_network.topology_utils import select_three_hops

    pool = ["a", "b", "c", "d", "e"]
    entries = Counter()
    for _ in range(1000):
        hops = select_three_hops(pool, "first")
        entries[hops[0]] += 1

    # 'a' ist IMMER Entry -> Single Point of Failure
    assert entries["a"] == 1000
    assert entries["b"] == 0
    assert entries["c"] == 0
    assert entries["d"] == 0
    assert entries["e"] == 0


def test_simulate_random_balances_entries():
    """'random' mit 5-Peer-Pool: alle Peers ~20% als Entry."""
    from collections import Counter
    from erebos_network.topology_utils import select_three_hops

    pool = ["a", "b", "c", "d", "e"]
    entries = Counter()
    for _ in range(1000):
        hops = select_three_hops(pool, "random")
        entries[hops[0]] += 1

    # Jeder Peer sollte zwischen 10% und 30% als Entry dienen
    for name in pool:
        ratio = entries[name] / 1000
        assert 0.10 < ratio < 0.30, (
            f"Peer {name}: {ratio:.2%} als Entry (erwartet 10-30%)"
        )


def test_simulate_round_robin_balances_entries():
    """'round_robin' rotiert deterministisch."""
    from collections import Counter
    from erebos_network.topology_utils import select_three_hops

    pool = ["a", "b", "c", "d", "e"]
    entries = Counter()
    for i in range(1000):
        hops = select_three_hops(pool, "round_robin", offset=i)
        entries[hops[0]] += 1

    # Perfekte Balance: jeder Peer genau 200 mal
    for name in pool:
        assert entries[name] == 200, (
            f"Peer {name}: {entries[name]} (erwartet 200)"
        )


def test_simulate_usage_first_creates_entry_spof():
    """'first': peer1 ist IMMER Entry -> SPOF."""
    from analyze_topology import simulate_usage, analyze_usage
    pool = ["a", "b", "c", "d", "e"]
    usage = simulate_usage(pool, "first", iterations=100)
    metrics = analyze_usage(usage, warn_above=0.5)
    # 'a' ist in 100% der Fälle Entry -> SPOF
    assert metrics["entry_counts"]["a"] == 100
    assert metrics["critical"] == ["a"]


def test_simulate_usage_random_balanced():
    """'random': jeder Peer ~20% als Entry, kein SPOF."""
    from analyze_topology import simulate_usage, analyze_usage
    pool = ["a", "b", "c", "d", "e"]
    usage = simulate_usage(pool, "random", iterations=1000)
    metrics = analyze_usage(usage, warn_above=0.5)
    # Kein Peer > 50% Entry -> kein SPOF
    assert metrics["critical"] == []
    # Alle Peers 10-30%
    for peer in pool:
        ratio = metrics["entry_counts"][peer] / 1000
        assert 0.10 < ratio < 0.30


def test_simulate_usage_round_robin_perfect():
    """'round_robin': perfekte Balance."""
    from analyze_topology import simulate_usage, analyze_usage
    pool = ["a", "b", "c", "d", "e"]
    usage = simulate_usage(pool, "round_robin", iterations=1000)
    metrics = analyze_usage(usage, warn_above=0.5)
    # Jeder Peer genau 200 mal Entry
    for peer in pool:
        assert metrics["entry_counts"][peer] == 200
