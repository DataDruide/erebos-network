"""Zentrale Konfiguration fuer Erebos Network.

Alle Werte koennen via Environment-Variablen ueberschrieben werden.
Defaults sind auf produktionsnahe Werte gesetzt.
"""

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (ValueError, TypeError):
        return default


# Mail-Key-Expiry
# Wie lange ein Mail-Key-Satz gueltig ist, bis er als "abgelaufen" gilt.
# Standard: 90 Tage. Nach Ablauf wird die Signatur als VERIFIED_EXPIRED
# markiert (orange), aber nicht als ungueltig.
MAIL_KEY_VALIDITY_DAYS = _env_int("EREBOS_MAIL_KEY_VALIDITY_DAYS", 90)
MAIL_KEY_VALIDITY_SECONDS = MAIL_KEY_VALIDITY_DAYS * 24 * 60 * 60


# Rate-Limit fuer Key-Rotation
# Wie oft eine UUID ihre Keys hoechstens rotieren darf (pro Zeitfenster).
# Standard: 1x pro Stunde.
ROTATE_RATE_LIMIT_SECONDS = _env_int("EREBOS_ROTATE_RATE_LIMIT_SECONDS", 3600)
