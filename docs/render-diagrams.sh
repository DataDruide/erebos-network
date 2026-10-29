#!/bin/bash
# Rendert alle .mmd-Dateien in docs/images/ als PNG.
# Voraussetzung: mermaid-cli (npm i -g @mermaid-js/mermaid-cli)
# Hinweis: -w/--width wird von neueren mermaid-cli-Versionen nicht mehr
# unterstuetzt. Wir lassen die Groesse weg (natuerliche Diagrammgroesse).
set -e
cd "$(dirname "$0")/images"
CONFIG=/tmp/puppeteer-config.json
if [ ! -f "$CONFIG" ]; then
  echo '{"args":["--no-sandbox"]}' > "$CONFIG"
fi
for f in *.mmd; do
  out="${f%.mmd}.png"
  echo "→ $f → $out"
  mmdc -i "$f" -o "$out" -b transparent -p "$CONFIG"
done
echo "✅ Fertig. PNGs liegen in docs/images/"
