#!/bin/bash
# Startet die Erebos Service App (GUI)
cd "$(dirname "$0")/.."
source .venv/bin/activate
python scripts/erebos_service_app.py
