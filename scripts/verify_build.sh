#!/usr/bin/env bash
# Reproduzierbarkeits-Verifikation.
#
# Baut das Wheel zweimal in einer sauberen Umgebung und vergleicht die
# SHA256-Hashes. Wenn identisch: reproduzierbar.
#
# Grenze: liboqs-python lädt liboqs als C-Bibliothek nach. Wenn die
# Systemumgebung (macOS-Version, Compiler, liboqs-Version) unterschiedlich
# ist, kann das Wheel unterschiedlich ausfallen. Wir prüfen hier nur die
# Python-Ebene.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

echo "==> Reproduzierbarkeits-Check"
echo "    Root: $ROOT"

BUILD1="$ROOT/build/verify-1"
BUILD2="$ROOT/build/verify-2"

rm -rf "$BUILD1" "$BUILD2"
mkdir -p "$BUILD1" "$BUILD2"

build_wheel() {
    local outdir="$1"
    local log="$2"
    python3 -m build --wheel --outdir "$outdir" > "$log" 2>&1
    local rc=$?
    if [ $rc -ne 0 ]; then
        echo "    [FEHLER] build fehlgeschlagen, siehe $log"
        tail -20 "$log"
        return 1
    fi
    return 0
}

hash_wheel() {
    local dir="$1"
    local wheel
    wheel=$(ls "$dir"/*.whl 2>/dev/null | head -1)
    if [ -z "$wheel" ]; then
        echo ""
        return 1
    fi
    # SHA256 über den entpackten Inhalt, nicht über die .whl-Datei
    # (Timestamps in der .whl selbst sind nicht deterministisch).
    local tmp
    tmp=$(mktemp -d)
    (cd "$tmp" && unzip -q "$wheel" && \
        find . -type f ! -name 'RECORD' ! -name '*.pyc' -print0 | \
        sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')
    local rc=$?
    rm -rf "$tmp"
    return $rc
}

echo ""
echo "==> Build 1"
if ! build_wheel "$BUILD1" "$ROOT/build/verify-1.log"; then
    exit 1
fi
H1=$(hash_wheel "$BUILD1")
echo "    Hash: $H1"

echo ""
echo "==> Build 2"
if ! build_wheel "$BUILD2" "$ROOT/build/verify-2.log"; then
    exit 1
fi
H2=$(hash_wheel "$BUILD2")
echo "    Hash: $H2"

echo ""
if [ -n "$H1" ] && [ "$H1" = "$H2" ]; then
    echo "==> ERGEBNIS: reproduzierbar"
    echo "    $H1"
    exit 0
else
    echo "==> ERGEBNIS: NICHT reproduzierbar"
    echo "    Build 1: $H1"
    echo "    Build 2: $H2"
    echo ""
    echo "    Diff der Inhalte:"
    TMP1=$(mktemp -d); TMP2=$(mktemp -d)
    (cd "$TMP1" && unzip -q "$BUILD1"/*.whl)
    (cd "$TMP2" && unzip -q "$BUILD2"/*.whl)
    diff -r "$TMP1" "$TMP2" | head -20
    rm -rf "$TMP1" "$TMP2"
    exit 1
fi
