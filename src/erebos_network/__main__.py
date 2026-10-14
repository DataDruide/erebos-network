"""Erebos Network - CLI-Einstiegspunkt."""

import argparse
import asyncio
import logging
import sys

from .api import run_server
from .proxy import ErebosProxy, ErebosSocks5Server, Socks5Config
from .router import ErebosRouter
from .sectors import SectorType, list_sectors


def setup_logging(verbose: bool = False) -> None:
    """Konfiguriert Logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def demo(traffic_shaping: bool = False) -> None:
    """Demo: Zeigt Router-Entscheidungen.

    Args:
        traffic_shaping: Aktiviert RateShaper + Jitter im Proxy.
    """
    router = ErebosRouter()
    proxy = ErebosProxy(router, traffic_shaping=traffic_shaping)
    await proxy.start()

    print("\n" + "=" * 60)
    print("EREBOS NETWORK - DEMO")
    print("=" * 60)

    print("\nVerfügbare Sektoren:")
    for sector in list_sectors():
        print(f"  - {sector}")

    print("\nRouting-Demos:")
    targets = [
        "https://example.com",
        "http://stats.i2p",
        "http://forum.i2p",
        "http://my-service.erebos",
    ]

    for target in targets:
        result = await proxy.handle_request(target)
        print(f"\n  Ziel: {target}")
        print(f"    Typ: {result.get('route_type')}")
        print(f"    Sektor: {result.get('sector')}")
        print(f"    Hops: {result.get('hops')}")
        print(f"    Proxy: {result.get('proxy')}")
        print(f"    Grund: {result.get('reason')}")

    print("\n" + "=" * 60)
    print("STATISTIKEN")
    print("=" * 60)
    stats = proxy.get_stats()
    print(f"  Requests total: {stats['requests_total']}")
    print(f"  Requests routed: {stats['requests_routed']}")
    print(f"  Traffic-Shaping: {stats['traffic_shaping']}")
    if stats["shaper"] is not None:
        print(f"  Shaped requests: {stats['shaped_requests']}")
        print(f"  Shaper: {stats['shaper']}")
    print(f"  Router stats: {stats['router']}")

    await proxy.stop()
    print("\n✅ Demo abgeschlossen")


def main() -> int:
    """Hauptfunktion."""
    parser = argparse.ArgumentParser(
        description="Erebos Network - Anonymes Netzwerk mit adaptiven Sektoren"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Startet die Demo",
    )
    parser.add_argument(
        "--sector",
        choices=[s.value for s in SectorType],
        default="standard",
        help="Standard-Sektor",
    )
    parser.add_argument(
        "--peer",
        action="store_true",
        help="Startet den Peer-Server",
    )
    parser.add_argument(
        "--peer-port",
        type=int,
        default=9999,
        help="Port fuer den Peer-Server (default: 9999)",
    )
    parser.add_argument(
        "--proxy",
        action="store_true",
        help="Startet den SOCKS5-Proxy auf 127.0.0.1:4447",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        default=4447,
        help="Port fuer den SOCKS5-Proxy",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Startet den HTTP-API-Server auf 127.0.0.1:9050",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9050,
        help="Port für den API-Server",
    )
    parser.add_argument(
        "--traffic-shaping",
        action="store_true",
        help="Aktiviert RateShaper + Jitter (Opt-In)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose-Logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.peer:
        from .tunnel import run_peer_server
        try:
            asyncio.run(run_peer_server(port=args.peer_port))
        except KeyboardInterrupt:
            print("\nPeer beendet.")
        return 0

    if args.proxy:
        async def run_proxy():
            proxy = ErebosProxy(traffic_shaping=args.traffic_shaping)
            server = ErebosSocks5Server(
                proxy,
                port=args.proxy_port,
                config=Socks5Config(),
            )
            await server.start()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await server.stop()

        try:
            asyncio.run(run_proxy())
        except KeyboardInterrupt:
            print("\nProxy beendet.")
        return 0

    if args.serve:
        run_server(port=args.port)
        return 0

    if args.demo:
        asyncio.run(demo(traffic_shaping=args.traffic_shaping))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
