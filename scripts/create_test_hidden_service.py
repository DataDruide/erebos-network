"""CLI-Wrapper für den produktiven Erebos Hidden-Service.

Dieser Test-Treiber startet einen HiddenServiceRuntime mit
Standard-Parametern, die zum Test-Setup passen (Peers auf 9997/9998/9999,
HTTP-Backend auf 8080).

Für den produktiven Einsatz: siehe erebos_network.hidden_service_runtime.
"""

import argparse
import asyncio
import logging
import sys

from erebos_network.hidden_service_runtime import HiddenServiceRuntime


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Erebos Test-Hidden-Service")
    p.add_argument("--rendezvous-host", default="127.0.0.1")
    p.add_argument("--rendezvous-port", type=int, default=9999)
    p.add_argument("--http-host", default="127.0.0.1")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--bind-host", default="127.0.0.1")
    p.add_argument("--bind-port", type=int, default=8080)
    p.add_argument("--ttl", type=int, default=3600)
    p.add_argument("--dht-peers", default="9997,9998,9999",
                   help="Komma-getrennte Peer-Ports für DHT-Publish")
    p.add_argument("--intro-points", default="peer1:127.0.0.1:9997",
                   help="Komma-getrennt, Format: peer_id:host:port")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    intro_points = []
    for item in args.intro_points.split(","):
        peer_id, addr = item.split(":", 1)
        intro_points.append((peer_id, addr))

    runtime = HiddenServiceRuntime(
        rendezvous_host=args.rendezvous_host,
        rendezvous_port=args.rendezvous_port,
        http_backend_host=args.http_host,
        http_backend_port=args.http_port,
        intro_points=intro_points,
        dht_peers=[int(p) for p in args.dht_peers.split(",")],
        ttl_seconds=args.ttl,
        bind_host=args.bind_host,
        bind_port=args.bind_port,
    )

    try:
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        runtime.stop()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
