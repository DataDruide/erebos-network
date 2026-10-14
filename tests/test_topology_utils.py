"""Tests für src/erebos_network/topology_utils.py."""
import importlib
import sys


def test_select_first():
    from erebos_network.topology_utils import select_three_hops
    assert select_three_hops(["a", "b", "c", "d"], "first") == ["a", "b", "c"]


def test_select_random():
    from erebos_network.topology_utils import select_three_hops
    hops = select_three_hops(["a", "b", "c", "d", "e"], "random")
    assert len(hops) == 3
    assert len(set(hops)) == 3
    assert all(h in {"a", "b", "c", "d", "e"} for h in hops)


def test_select_round_robin():
    from erebos_network.topology_utils import select_three_hops
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 0) == ["a", "b", "c"]
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 1) == ["b", "c", "d"]
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 3) == ["d", "a", "b"]
    assert select_three_hops(["a", "b", "c", "d"], "round_robin", 4) == ["a", "b", "c"]


def test_pool_too_small():
    from erebos_network.topology_utils import select_three_hops
    # Bei Pool < 3: pool[:3] (Backward-Compat)
    assert select_three_hops(["a", "b"], "first") == ["a", "b"]
    assert select_three_hops(["a", "b"], "random") == ["a", "b"]


def test_unknown_strategy_fallback():
    from erebos_network.topology_utils import select_three_hops
    assert select_three_hops(["a", "b", "c", "d"], "unknown") == ["a", "b", "c"]


def test_module_has_no_crypto_deps():
    """topology_utils muss importierbar sein, wenn cryptography fehlt.

    Simuliert das, indem wir 'cryptography' und seine Submodule aus
    sys.modules entfernen und einen ImportError erzwingen.
    """
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError(f"simulated: no {name}")
        return real_import(name, *args, **kwargs)

    # Modul neu laden mit "fehlendem" cryptography
    if "erebos_network.topology_utils" in sys.modules:
        del sys.modules["erebos_network.topology_utils"]

    builtins.__import__ = fake_import
    try:
        fresh = importlib.import_module("erebos_network.topology_utils")
        assert hasattr(fresh, "select_three_hops")
    finally:
        builtins.__import__ = real_import
        if "erebos_network.topology_utils" in sys.modules:
            del sys.modules["erebos_network.topology_utils"]
        importlib.import_module("erebos_network.topology_utils")
