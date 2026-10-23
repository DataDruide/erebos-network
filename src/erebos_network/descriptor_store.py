"""Einfacher In-Memory-Store für Hidden-Service-Descriptors.

Dieser Store ist ein Platzhalter für eine echte verteilte DHT.
Er unterstützt put/get für Descriptors, die mit dem SHA-256-Hash
der .erebos-Adresse als Schlüssel gespeichert werden.
"""

from typing import Optional


class DescriptorStore:
    """In-Memory-Store für Hidden-Service-Descriptors."""

    def __init__(self):
        self._store = {}

    def put(self, key: bytes, value: dict) -> None:
        """Speichert einen Descriptor unter einem Schlüssel."""
        self._store[key] = value

    def get(self, key: bytes) -> Optional[dict]:
        """Holt einen Descriptor unter einem Schlüssel."""
        return self._store.get(key)

    def remove(self, key: bytes) -> bool:
        """Entfernt einen Descriptor."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        """Leert den Store."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Anzahl der gespeicherten Descriptors."""
        return len(self._store)
