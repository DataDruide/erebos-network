#!/bin/bash
# Startet den Erebos-Browser mit der richtigen Onboard-URL
BROWSER="/Users/marcelzimmermann/Projects/mullvad-browser/obj-aarch64-apple-darwin/dist/Erebos.app"
URL="http://7og2zplgthz36a3w6u5j37bwa5xf7lb4kwmzmklq5gonfettzvgq.erebos/onboard"

# Browser starten
open -a "$BROWSER" "$URL"
