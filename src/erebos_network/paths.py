"""Zentrale Pfad-Aufloesung fuer Erebos Network.

Liest EREBOS_APP_DIR aus der Umgebung, faellt auf das Projekt-Root
zurueck (das Verzeichnis, in dem pyproject.toml liegt).

Docker setzt EREBOS_APP_DIR=/app (siehe docker-compose.yml).
Lokal laeuft es ohne Env -> Projekt-Root.
"""

import os
from pathlib import Path


def app_dir() -> Path:
    """Liefert das App-Verzeichnis (Env EREBOS_APP_DIR oder Projekt-Root)."""
    env = os.environ.get("EREBOS_APP_DIR")
    if env:
        return Path(env)
    # Fallback: von dieser Datei drei Ebenen hoch
    # (src/erebos_network/paths.py -> src/erebos_network -> src -> Projekt-Root)
    return Path(__file__).resolve().parent.parent.parent


def app_file(name: str) -> Path:
    """Liefert eine Datei unter app_dir()."""
    return app_dir() / name
