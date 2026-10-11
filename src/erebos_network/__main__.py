"""Erebos Network - CLI-Einstiegspunkt."""

import argparse
import asyncio
import logging
import sys

from .proxy import ErebosProxy
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


async def demo() -> None:
    """Demo: Zeigt Router-Entscheidungen."""
    router = ErebosRouter()
    proxy = ErebosProxy(router)
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
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose-Logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.demo:
        asyncio.run(demo())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
