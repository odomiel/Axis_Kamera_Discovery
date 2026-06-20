#!/usr/bin/env bash
#
# Baut ein eigenstaendiges AppImage der Axis-Discovery-GUI mit Tcl/Tk 9.
#
# Da kein Basis-Image mit Tk 9 existiert, werden Tcl 9, Tk 9 und Python 3.13
# (erste Version mit offizieller Tcl/Tk-9-Unterstuetzung) aus dem Quellcode
# gebaut. libffi wird ebenfalls gebaut (fuer _ctypes -> ifaddr/zeroconf).
# Die reinen Laufzeit-Pakete kommen als fertige cp313-Wheels (curl + entpacken),
# damit kein OpenSSL/pip noetig ist.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/.tk9build"
SRC="$BUILD/src"
APPDIR="$BUILD/AppDir"
PREFIX="$APPDIR/usr"
JOBS="$(nproc)"

TCL_VER=9.0.1
TK_VER=9.0.1
PY_VER=3.13.1
PY_XY=3.13
FFI_VER=3.4.6

mkdir -p "$SRC"
rm -rf "$APPDIR"
mkdir -p "$PREFIX"

dl() {  # dl <url> <zieldatei>
    local url="$1" out="$2"
    [ -f "$out" ] || { echo ">> download $(basename "$out")"; curl -fSL "$url" -o "$out"; }
}

# --------------------------------------------------------------- 1. Quellen
dl "https://downloads.sourceforge.net/project/tcl/Tcl/$TCL_VER/tcl$TCL_VER-src.tar.gz" "$SRC/tcl.tar.gz"
dl "https://downloads.sourceforge.net/project/tcl/Tcl/$TK_VER/tk$TK_VER-src.tar.gz"    "$SRC/tk.tar.gz"
dl "https://www.python.org/ftp/python/$PY_VER/Python-$PY_VER.tgz"                       "$SRC/python.tgz"
dl "https://github.com/libffi/libffi/releases/download/v$FFI_VER/libffi-$FFI_VER.tar.gz" "$SRC/libffi.tar.gz"

cd "$SRC"
rm -rf "tcl$TCL_VER" "tk$TK_VER" "Python-$PY_VER" "libffi-$FFI_VER"
tar xf tcl.tar.gz; tar xf tk.tar.gz; tar xf python.tgz; tar xf libffi.tar.gz

export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export LD_LIBRARY_PATH="$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# --------------------------------------------------------------- 2. libffi
echo "==== libffi $FFI_VER ===="
cd "$SRC/libffi-$FFI_VER"
./configure --prefix="$PREFIX" --disable-static --disable-docs >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null

# --------------------------------------------------------------- 3. Tcl 9
echo "==== Tcl $TCL_VER ===="
cd "$SRC/tcl$TCL_VER/unix"
./configure --prefix="$PREFIX" --enable-shared --enable-64bit >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null
# tclsh-Symlink fuer Tk-configure
ln -sf "$PREFIX/bin/tclsh$TCL_VER" "$PREFIX/bin/tclsh${TCL_VER%.*}" 2>/dev/null || true

# --------------------------------------------------------------- 4. Tk 9
echo "==== Tk $TK_VER ===="
cd "$SRC/tk$TK_VER/unix"
./configure --prefix="$PREFIX" --with-tcl="$PREFIX/lib" \
            --enable-shared --enable-64bit --enable-xft >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null

# --------------------------------------------------------------- 5. Python 3.13
echo "==== Python $PY_VER (gegen Tcl/Tk 9) ===="
cd "$SRC/Python-$PY_VER"
./configure \
    --prefix="$PREFIX" \
    --enable-shared \
    --with-ensurepip=no \
    --with-tcltk-includes="-I$PREFIX/include" \
    --with-tcltk-libs="-L$PREFIX/lib -ltcl9.0 -ltk9.0" \
    CPPFLAGS="-I$PREFIX/include" \
    LDFLAGS="-L$PREFIX/lib -Wl,-rpath,\$\$ORIGIN/../lib" \
    >/dev/null
make -j"$JOBS" >/dev/null 2>&1
make install >/dev/null 2>&1

PYBIN="$PREFIX/bin/python$PY_XY"
echo ">> Tcl/Tk-Version im neuen Python:"
"$PYBIN" -c "import tkinter; r=tkinter.Tk(); print('  Tcl/Tk', r.tk.call('info','patchlevel')); r.destroy()"

# --------------------------------------------------------------- 6. Wheels vendoren
echo "==== Laufzeit-Pakete (cp313-Wheels) ===="
SITE="$PREFIX/lib/python$PY_XY/site-packages"
mkdir -p "$SITE"
wheel() {  # wheel <pypi-paket> <filter>
    local pkg="$1" filt="$2"
    local url
    url=$(curl -s "https://pypi.org/pypi/$pkg/json" | "$PYBIN" -c "
import json,sys
d=json.load(sys.stdin); v=d['info']['version']
for f in d['releases'][v]:
    n=f['filename']
    if $filt:
        print(f['url']); break
")
    echo ">> $pkg: $(basename "$url")"
    curl -fsSL "$url" -o "$BUILD/$pkg.whl"
    "$PYBIN" -m zipfile -e "$BUILD/$pkg.whl" "$SITE/"
}
wheel zeroconf    "'cp313' in n and 'manylinux' in n and 'x86_64' in n"
wheel ifaddr      "n.endswith('.whl')"
wheel prettytable "n.endswith('.whl')"
# wcwidth (Abhaengigkeit von prettytable)
wheel wcwidth     "n.endswith('.whl')"

# --------------------------------------------------------------- 7. App + AppDir
echo "==== AppDir zusammenstellen ===="
mkdir -p "$APPDIR/app"
cp "$ROOT/axis_discovery_gui.py" "$ROOT/axis_discovery_cli.py" \
   "$ROOT/README.md" "$ROOT/THIRD_PARTY_LICENSES.md" "$ROOT/LICENSE" "$APPDIR/app/"

# Desktop + Icon (fuer appimagetool im AppDir-Wurzelverzeichnis)
cp "$ROOT/appimage/AxisDiscovery/AxisDiscovery.png" "$APPDIR/AxisDiscovery.png"
cat > "$APPDIR/AxisDiscovery.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=AxisDiscovery
GenericName=Axis Kamera Discovery
Comment=Findet Axis-Kameras im lokalen Netzwerk per Zeroconf
Exec=AppRun %u
Icon=AxisDiscovery
Categories=Network;Utility;
Terminal=false
DESKTOP

# AppRun: setzt eigenstaendige Python/Tcl/Tk-Umgebung und waehlt GUI/CLI
cat > "$APPDIR/AppRun" <<APPRUN
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\$0")")"
export APPDIR="\$HERE"
export PYTHONHOME="\$HERE/usr"
export PYTHONDONTWRITEBYTECODE=1
export LD_LIBRARY_PATH="\$HERE/usr/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
# Tcl/Tk 9 betten ihre Script-Library per zipfs in die .so ein -> kein
# TCL_LIBRARY/TK_LIBRARY noetig (waere sogar fehleranfaellig).
PY="\$HERE/usr/bin/python$PY_XY"
case "\${1:-}" in
    cli) shift; exec "\$PY" "\$HERE/app/axis_discovery_cli.py" "\$@" ;;
    -*)  exec "\$PY" "\$HERE/app/axis_discovery_cli.py" "\$@" ;;
    *)   exec "\$PY" "\$HERE/app/axis_discovery_gui.py" "\$@" ;;
esac
APPRUN
chmod +x "$APPDIR/AppRun"

# Build-Reste verschlanken
rm -rf "$PREFIX/lib/python$PY_XY/test" "$PREFIX/lib/python$PY_XY/"*/test 2>/dev/null || true
find "$PREFIX" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --------------------------------------------------------------- 8. AppImage packen
echo "==== AppImage packen ===="
AIT="$BUILD/appimagetool-x86_64.AppImage"
dl "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" "$AIT"
chmod +x "$AIT"

VERSION="$(python3 "$ROOT/bump_version.py" --print)"
OUT="$ROOT/AxisDiscovery-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$AIT" --appimage-extract-and-run "$APPDIR" "$OUT" 2>&1 | tail -5
ln -sfn "$(basename "$OUT")" "$ROOT/AxisDiscovery-x86_64.AppImage"

echo ">> Fertig: $OUT"
