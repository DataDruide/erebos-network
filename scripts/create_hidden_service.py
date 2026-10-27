#!/usr/bin/env python3
"""Generischer Hidden-Service-Starter für Erebos."""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from erebos_network.hidden_service_runtime import HiddenServiceRuntime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--bind-host", default="0.0.0.0")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--rendezvous-host", default="127.0.0.1")
    parser.add_argument("--rendezvous-port", type=int, default=9999)
    parser.add_argument("--dht-peers", default="127.0.0.1:9999,127.0.0.1:9998,127.0.0.1:9997")
    parser.add_argument("--intro-points", default="peer1:127.0.0.1:9999,peer2:127.0.0.1:9998,peer3:127.0.0.1:9997")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    pages_dir = Path(args.pages).resolve()
    key_file = Path(args.key_file)
    key_file.parent.mkdir(parents=True, exist_ok=True)

    def render_static(path, address, request_line, method="GET", **kwargs):
        rel = path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        file_path = pages_dir / rel
        if not file_path.exists() or not file_path.is_file():
            file_path = pages_dir / "index.html"
        if not file_path.exists():
            return b"404 Not Found"
        content = file_path.read_bytes()
        ctype = "text/html; charset=utf-8"
        if file_path.suffix == ".css":
            ctype = "text/css"
        elif file_path.suffix == ".js":
            ctype = "application/javascript"
        elif file_path.suffix == ".json":
            ctype = "application/json"
        return b"CONTENT_TYPE:" + ctype.encode() + b"\n" + content

    import erebos_network.landing_pages as lp
    lp.render_page = render_static

    intro_points = []
    for item in args.intro_points.split(","):
        peer_id, addr = item.split(":", 1)
        intro_points.append((peer_id, addr))

    runtime = HiddenServiceRuntime(
        rendezvous_host=args.rendezvous_host,
        rendezvous_port=args.rendezvous_port,
        http_backend_host="127.0.0.1",
        http_backend_port=args.port,
        intro_points=intro_points,
        dht_peers=[(int(p) if ":" not in p else p) for p in args.dht_peers.split(",")],
        ttl_seconds=3600,
        bind_host=args.bind_host,
        bind_port=args.port,
    )

    try:
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        runtime.stop()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
