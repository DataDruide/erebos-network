"""Konfigurierbare Peer-Adressen fuer Erebos.

Standard: 127.0.0.1 (Loopback, wie bisher).
Fuer Docker / echte Peers: Umgebungsvariable EREBOS_PEER_HOSTS setzen.

Format EREBOS_PEER_HOSTS:
    peer1=172.20.0.10,peer2=172.20.0.11,peer3=172.20.0.12

Beispiel:
    export EREBOS_PEER_HOSTS="peer1=172.20.0.10,peer2=172.20.0.11,peer3=172.20.0.12"
    ./scripts/start_all.sh

Wenn die Variable nicht gesetzt ist, wird 127.0.0.1 fuer alle Peers
verwendet (Verhalten wie vorher).
"""

import os
from typing import Dict

DEFAULT_HOST = "127.0.0.1"

# Peer -> (Port) — feste Ports, aenderbar falls noetig.
PEER_PORTS: Dict[str, int] = {
    "peer1": 9999,
    "peer2": 9998,
    "peer3": 9997,
    "peer4": 9996,
    "peer5": 9995,
}


def _parse_env() -> Dict[str, str]:
    """Liest EREBOS_PEER_HOSTS und gibt {peer: host} zurueck."""
    raw = os.environ.get("EREBOS_PEER_HOSTS", "").strip()
    if not raw:
        return {}
    result: Dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, host = item.split("=", 1)
        result[name.strip()] = host.strip()
    return result


_HOSTS = _parse_env()


def peer_host(peer_name: str) -> str:
    """Gibt den Host fuer einen Peer zurueck (Default: 127.0.0.1)."""
    return _HOSTS.get(peer_name, DEFAULT_HOST)


def peer_address(peer_name: str) -> str:
    """Gibt "host:port" fuer einen Peer zurueck."""
    port = PEER_PORTS.get(peer_name)
    if port is None:
        raise ValueError(f"Unbekannter Peer: {peer_name}")
    return f"{peer_host(peer_name)}:{port}"


def all_peer_hosts() -> Dict[str, str]:
    """Gibt {peer: host} fuer alle konfigurierten Peers zurueck."""
    return {name: peer_host(name) for name in PEER_PORTS}


def rendezvous_address() -> str:
    """Adresse des Rendezvous-Punkts (peer1)."""
    return peer_address("peer1")
