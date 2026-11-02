"""Minimaler Hidden-Service-Starter – nur Hetzner-Peer, keine Fallbacks."""
import asyncio
import sys
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '/root/erebos-network/src')

from erebos_network.hidden_service_runtime import HiddenServiceRuntime

async def main():
    runtime = HiddenServiceRuntime(
        rendezvous_host='167.233.111.144',
        rendezvous_port=9996,
        http_backend_host='127.0.0.1',
        http_backend_port=8080,
        intro_points=[('hetzner', '167.233.111.144:9996')],
        dht_peers=['167.233.111.144:9996'],
        ttl_seconds=3600,
        bind_host='0.0.0.0',
        bind_port=8080,
    )
    await runtime.run()

if __name__ == '__main__':
    asyncio.run(main())
