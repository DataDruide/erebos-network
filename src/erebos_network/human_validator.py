"""Custom Human Extension Validator (PoW + human.json Signal)."""

import hashlib
import os
import time
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class HumanValidator:
    def __init__(self, base_difficulty: int = 4, challenge_ttl: int = 120):
        self.base_difficulty = base_difficulty
        self.challenge_ttl = challenge_ttl
        # Speichert aktive Challenges: nonce -> (timestamp, difficulty)
        self.active_challenges: Dict[str, tuple] = {}
        # Rate-Limit-Tracking: ip -> [timestamps]
        self.ip_requests: Dict[str, list] = {}
        self.rate_window = 60  # Sekunden
        self.max_requests_per_window = 30

    def _cleanup(self):
        """Räumt abgelaufene Challenges und alte Rate-Limit-Einträge auf."""
        now = time.time()
        # Abgelaufene Challenges löschen
        expired = [n for n, (ts, _) in self.active_challenges.items() if now - ts > self.challenge_ttl]
        for n in expired:
            del self.active_challenges[n]
        
        # Alte Rate-Limit-Einträge löschen
        for ip in list(self.ip_requests.keys()):
            self.ip_requests[ip] = [t for t in self.ip_requests[ip] if now - t < self.rate_window]
            if not self.ip_requests[ip]:
                del self.ip_requests[ip]

    def issue_challenge(self, client_ip: str) -> dict:
        """Stellt eine neue PoW-Challenge aus und passt die Schwierigkeit dynamisch an."""
        self._cleanup()
        
        # Rate-Limit prüfen (DDoS-Schutz)
        now = time.time()
        self.ip_requests.setdefault(client_ip, []).append(now)
        recent = len(self.ip_requests[client_ip])
        
        # Wenn zu viele Anfragen: Schwierigkeit erhöhen
        difficulty = self.base_difficulty
        if recent > self.max_requests_per_window:
            difficulty += 1  # Jede weitere Anfrage macht es schwerer

        nonce = os.urandom(16).hex()
        self.active_challenges[nonce] = (now, difficulty)
        
        logger.info(f"PoW-Challenge ausgestellt für {client_ip}: nonce={nonce[:8]}..., difficulty={difficulty}")
        return {"nonce": nonce, "difficulty": difficulty}

    def verify_solution(self, nonce: str, solution: str) -> bool:
        """Prüft, ob der Client die Aufgabe gelöst hat."""
        self._cleanup()
        if nonce not in self.active_challenges:
            logger.warning(f"Unbekannte oder abgelaufene Challenge: {nonce[:8]}...")
            return False
        
        timestamp, difficulty = self.active_challenges[nonce]
        
        # Prüfe den Hash: sha256(nonce + solution) muss mit `difficulty` Nullen beginnen
        test_hash = hashlib.sha256((nonce + solution).encode()).hexdigest()
        if test_hash.startswith("0" * difficulty):
            del self.active_challenges[nonce]  # Challenge ist verbraucht
            logger.info(f"PoW erfolgreich gelöst für {nonce[:8]}...")
            return True
        
        logger.warning(f"PoW ungültig für {nonce[:8]}...")
        return False

    def check_human_json(self, headers: dict) -> bool:
        """
        Custom-Erweiterung: Prüft, ob der Client ein 'human.json'-Signal sendet.
        In der Praxis: Ein Browser-Add-on setzt diesen Header, wenn der Nutzer
        über eine vertrauenswürdige Kette verifiziert wurde.
        """
        # Platzhalter für deine Logik (z.B. JWT-Validierung)
        # return headers.get("X-Erebos-Human-Proof") == "valid_token"
        return False
