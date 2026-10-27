#!/usr/bin/env python3
"""Startet den Chat-Hidden-Service (Port 8081) mit eigener .erebos-Adresse.

Nutzt dieselbe HiddenServiceRuntime wie der Forum-Service, aber:
- eigener HS-Key (hs_key_8081.pem)
- eigener HTTP-Port (8081)
- gleiche Rendezvous/DHT-Peers (peer1/2/3)
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# .env laden, bevor erebos_network importiert wird
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from erebos_network.hidden_service_runtime import HiddenServiceRuntime
from erebos_network import chat as _chat



async def _cleanup_loop():
    """Ruft alle CLEANUP_INTERVAL_SEC chat.cleanup_old_rooms() auf."""
    import asyncio
    while True:
        try:
            await asyncio.sleep(_chat.CLEANUP_INTERVAL_SEC)
            n = _chat.cleanup_old_rooms()
            if n > 0:
                logging.info(f"Chat-Cleanup: {n} alte Rooms geloescht")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Chat-Cleanup-Fehler: {e}")



def main() -> int:
    parser = argparse.ArgumentParser(description="Erebos Chat Hidden Service")
    parser.add_argument("--rendezvous-host", default="127.0.0.1")
    parser.add_argument("--rendezvous-port", type=int, default=9999)
    parser.add_argument("--http-host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8081)
    parser.add_argument("--bind-host", default="0.0.0.0")
    parser.add_argument("--bind-port", type=int, default=8081)
    parser.add_argument(
        "--dht-peers", default="127.0.0.1:9999,127.0.0.1:9998,127.0.0.1:9997"
    )
    parser.add_argument(
        "--intro-points",
        default="peer1:127.0.0.1:9999,peer2:127.0.0.1:9998,peer3:127.0.0.1:9997",
    )
    parser.add_argument("--ttl", type=int, default=3600)
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

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
        dht_peers=[
            (int(p) if ":" not in p else p) for p in args.dht_peers.split(",")
        ],
        ttl_seconds=args.ttl,
        bind_host=args.bind_host,
        bind_port=args.bind_port,
    )

    async def _run_with_cleanup():
        import asyncio
        cleanup_task = asyncio.create_task(_cleanup_loop())
        try:
            await runtime.run()
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    try:
        asyncio.run(_run_with_cleanup())
    except KeyboardInterrupt:
        runtime.stop()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
