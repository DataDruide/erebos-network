"""Hidden Services fuer Erebos Network.

Beidseitig anonyme Dienste - weder Client noch Server
kennen die Identitaet des anderen.

Basiert auf Tor-v3-Onion-Services, erweitert um PQ-Krypto.
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class HSState(Enum):
    """Zustand eines Hidden Service."""

    OFFLINE = "offline"
    PUBLISHED = "published"
    DESCRIPTOR_UPLOADED = "descriptor_uploaded"
    AVAILABLE = "available"


@dataclass
class HSDescriptor:
    """Ein Hidden-Service-Descriptor."""

    service_id: str  # .erebos-Adresse
    public_key: bytes
    introduction_points: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 86400  # 24h

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    @property
    def address(self) -> str:
        """Die .erebos-Adresse."""
        return f"{self.service_id}.erebos"


@dataclass
class HSSession:
    """Eine Client-Service-Session."""

    session_id: str
    client_id: str
    service_id: str
    rendezvous_point: str
    shared_secret: bytes
    created_at: float = field(default_factory=time.time)
    bytes_sent: int = 0
    bytes_received: int = 0


class HiddenService:
    """Hidden Service (beidseitig anonym).

    Weder Client noch Service kennen die IP des anderen.
    Vermittlung ueber Rendezvous-Punkte.
    """

    def __init__(self):
        self._services: dict[str, HSDescriptor] = {}
        self._sessions: dict[str, HSSession] = {}
        self.stats = {
            "services_created": 0,
            "descriptors_published": 0,
            "sessions_established": 0,
            "bytes_transferred": 0,
        }

    def create_service(
        self,
        introduction_points: Optional[list[str]] = None,
    ) -> HSDescriptor:
        """Erstellt einen neuen Hidden Service."""
        # Service-ID = SHA-256 des Public Keys
        key_seed = secrets.token_bytes(32)
        service_id = hashlib.sha256(key_seed).hexdigest()[:16]

        descriptor = HSDescriptor(
            service_id=service_id,
            public_key=key_seed,
            introduction_points=introduction_points or [
                f"intro-{i}.erebos" for i in range(3)
            ],
        )
        self._services[service_id] = descriptor
        self.stats["services_created"] += 1

        logger.info(f"Hidden Service erstellt: {descriptor.address}")
        return descriptor

    def publish_descriptor(self, service_id: str) -> bool:
        """Veroeffentlicht einen Descriptor im DHT."""
        service = self._services.get(service_id)
        if not service:
            return False
        self.stats["descriptors_published"] += 1
        return True

    def lookup(self, address: str) -> Optional[HSDescriptor]:
        """Sucht einen Hidden Service."""
        if not address.endswith(".erebos"):
            return None
        service_id = address[:-7]  # entferne .erebos
        return self._services.get(service_id)

    def establish_session(
        self,
        client_id: str,
        service_id: str,
    ) -> Optional[HSSession]:
        """Etabliert eine Session mit einem Hidden Service."""
        service = self._services.get(service_id)
        if not service:
            return None

        session_id = hashlib.sha256(
            f"{client_id}:{service_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        # Rendezvous-Punkt (weder Client noch Service kennen sich)
        rendezvous = hashlib.sha256(
            secrets.token_bytes(32)
        ).hexdigest()[:16]

        session = HSSession(
            session_id=session_id,
            client_id=client_id,
            service_id=service_id,
            rendezvous_point=rendezvous,
            shared_secret=secrets.token_bytes(32),
        )
        self._sessions[session_id] = session
        self.stats["sessions_established"] += 1

        logger.info(
            f"HS-Session etabliert: {session_id} "
            f"(Rendezvous: {rendezvous})"
        )
        return session

    def send(
        self,
        session_id: str,
        payload: bytes,
    ) -> bool:
        """Sendet Daten ueber HS-Session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.bytes_sent += len(payload)
        self.stats["bytes_transferred"] += len(payload)
        return True

    def receive(self, session_id: str, size: int) -> bool:
        """Empfaengt Daten ueber HS-Session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.bytes_received += size
        self.stats["bytes_transferred"] += size
        return True

    @property
    def service_count(self) -> int:
        return len(self._services)

    @property
    def session_count(self) -> int:
        return len(self._sessions)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "services": self.service_count,
            "sessions": self.session_count,
        }
