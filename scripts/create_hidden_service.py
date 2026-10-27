#!/usr/bin/env python3
"""Generischer Hidden-Service-Starter für Erebos.

Rendert statische HTML-Dateien aus einem Verzeichnis.
Nutzt http_request_handler (nicht render_page-Monkeypatch).
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

from erebos_network.hidden_service_runtime import HiddenServiceRuntime
from erebos_network.http_utils import parse_http_request, http_response
from erebos_network.template_engine import render_template, is_template


async def _static_handler(reader, writer, pages_dir: Path):
    """Liest HTTP-Request, rendert statische Datei aus pages_dir."""
    try:
        raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
        if not raw:
            return
        method, path, headers, body = parse_http_request(raw)

        rel = path.lstrip("/") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        file_path = pages_dir / rel
        if not file_path.exists() or not file_path.is_file():
            file_path = pages_dir / "index.html"
        if not file_path.exists():
            resp = http_response(404, "text/plain", b"404 Not Found")
            writer.write(resp)
            await writer.drain()
            return

        content = file_path.read_bytes()
        ctype = "text/html; charset=utf-8"
        if file_path.suffix == ".css":
            ctype = "text/css"
        elif file_path.suffix == ".js":
            ctype = "application/javascript"
        elif file_path.suffix == ".json":
            ctype = "application/json"

        # Template-Erkennung: Wenn .html und {{ ... }} drin → rendern
        if file_path.suffix == ".html":
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = None
            if text is not None and is_template(text):
                import time as _time
                context = {
                    "name": pages_dir.name,
                    "service_name": pages_dir.name,
                    "time": _time.strftime("%H:%M:%S"),
                    "date": _time.strftime("%Y-%m-%d"),
                    "address": "",
                    "client_id": "",
                    "path": path,
                    # Demo-Listen (können später durch echte Daten ersetzt werden)
                    "items": [
                        {"title": "Erster Eintrag", "body": "Hallo Welt"},
                        {"title": "Zweiter Eintrag", "body": "Noch ein Eintrag"},
                    ],
                    "admin": False,
                    "logged_in": False,
                }
                text = render_template(text, context)
                content = text.encode("utf-8")

        resp = http_response(200, ctype, content)
        writer.write(resp)
        await writer.drain()
    except Exception as e:
        logging.error(f"Static-Handler-Fehler: {e}")
    finally:
        writer.close()


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

    intro_points = []
    for item in args.intro_points.split(","):
        peer_id, addr = item.split(":", 1)
        intro_points.append((peer_id, addr))

    # Wrapper: _static_handler braucht pages_dir
    async def handler(reader, writer):
        await _static_handler(reader, writer, pages_dir)

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
        http_request_handler=handler,
    )

    try:
        asyncio.run(runtime.run())
    except KeyboardInterrupt:
        runtime.stop()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
