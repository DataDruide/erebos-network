#!/bin/bash
# Hilfsskript, das von AppleScript aufgerufen wird
# $1 = Titel, $2 = Befehl

TITLE="$1"
CMD="$2"
PROJECT_DIR="$HOME/Projects/erebos-network"
VENV_PATH="$PROJECT_DIR/.venv/bin/activate"

# Terminal-Titel setzen und Befehl ausführen
echo -ne "\033]0;${TITLE}\007"
cd "$PROJECT_DIR"
source "$VENV_PATH"
set -a
. ./.env
set +a
eval "$CMD"
