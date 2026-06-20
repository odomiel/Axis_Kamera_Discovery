#!/usr/bin/env bash
#
# Baut ein eigenstaendiges AppImage der Axis-Discovery-GUI.
# Das gebuendelte Python (inkl. Tkinter/Tcl-Tk, zeroconf, prettytable) macht
# das Programm unabhaengig von der System-Python-Installation.
#
# Benoetigt nur: python3 (mit venv/ensurepip) und Internetzugang beim Build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYVER="${PYVER:-3.12}"
BUILDENV="$ROOT/.buildenv"

# Optional: --bump erhoeht die Version (JJJJ.MM.TT, bei mehreren Releases/Tag bN)
BUMP=0
for arg in "$@"; do
    [ "$arg" = "--bump" ] && BUMP=1
done

# 1. Build-Umgebung mit python-appimage vorbereiten
if [ ! -d "$BUILDENV" ]; then
    echo ">> Lege Build-venv an..."
    python3 -m venv "$BUILDENV"
fi
# shellcheck disable=SC1091
source "$BUILDENV/bin/activate"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet python-appimage

# 2. Version bestimmen (optional hochzaehlen)
if [ "$BUMP" = "1" ]; then
    VERSION="$(python3 "$ROOT/bump_version.py")"
    echo ">> Version erhoeht auf $VERSION"
else
    VERSION="$(python3 "$ROOT/bump_version.py" --print)"
fi

# 3. AppImage bauen; Quellcode wird per --extra-data eingebettet
echo ">> Baue AppImage $VERSION (Python $PYVER)..."
python-appimage build app \
    -p "$PYVER" \
    "$ROOT/appimage/AxisDiscovery" \
    -x "$ROOT/axis_discovery_gui.py" "$ROOT/axis_discovery_cli.py"

# 4. Versioniertes Ergebnis bereitstellen (+ unversionierter Symlink)
ARCH="$(uname -m)"
SRC="$ROOT/AxisDiscovery-${ARCH}.AppImage"
DEST="$ROOT/AxisDiscovery-${VERSION}-${ARCH}.AppImage"
if [ -f "$SRC" ] && [ "$SRC" != "$DEST" ]; then
    mv -f "$SRC" "$DEST"
    ln -sfn "$(basename "$DEST")" "$SRC"
fi

echo ">> Fertig:"
ls -1 "$ROOT"/*.AppImage
