#!/usr/bin/env bash
#
# Baut ein eigenstaendiges AppImage von Axis_Kamera_Discovery mit Tcl/Tk 9.
#
# Da kein Basis-Image mit Tk 9 existiert, werden Tcl 9, Tk 9 und Python 3.14
# aus dem Quellcode gebaut (Tcl/Tk 9 wird offiziell ab Python 3.13 unterstuetzt).
# libffi wird ebenfalls gebaut (fuer _ctypes -> ifaddr/zeroconf),
# OpenSSL fuer das ssl-Modul (HTTPS-Zugriff auf die Kameras / VAPIX).
# Die reinen Laufzeit-Pakete kommen als fertige cp314-Wheels (curl + entpacken),
# damit kein pip noetig ist.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/.tk9build"
SRC="$BUILD/src"
APPDIR="$BUILD/AppDir"
PREFIX="$APPDIR/usr"
JOBS="$(nproc)"

TCL_VER=9.0.4
TK_VER=9.0.4
PY_VER=3.14.7
PY_XY=3.14
FFI_VER=3.8.0
SSL_VER=3.5.7

mkdir -p "$SRC"
rm -rf "$APPDIR"
mkdir -p "$PREFIX"

dl() {  # dl <url> <zieldatei>
    local url="$1" out="$2"
    [ -f "$out" ] || { echo ">> download $(basename "$out")"; curl -fSL "$url" -o "$out"; }
}

# --------------------------------------------------------------- 1. Quellen
# Die Dateinamen tragen die Version, sonst wuerde der Cache-Treffer in dl()
# nach einem Versionswechsel den alten Tarball weiterverwenden.
dl "https://downloads.sourceforge.net/project/tcl/Tcl/$TCL_VER/tcl$TCL_VER-src.tar.gz" "$SRC/tcl-$TCL_VER.tar.gz"
dl "https://downloads.sourceforge.net/project/tcl/Tcl/$TK_VER/tk$TK_VER-src.tar.gz"    "$SRC/tk-$TK_VER.tar.gz"
dl "https://www.python.org/ftp/python/$PY_VER/Python-$PY_VER.tgz"                       "$SRC/python-$PY_VER.tgz"
dl "https://github.com/libffi/libffi/releases/download/v$FFI_VER/libffi-$FFI_VER.tar.gz" "$SRC/libffi-$FFI_VER.tar.gz"
dl "https://github.com/openssl/openssl/releases/download/openssl-$SSL_VER/openssl-$SSL_VER.tar.gz" "$SRC/openssl-$SSL_VER.tar.gz"

cd "$SRC"
rm -rf "tcl$TCL_VER" "tk$TK_VER" "Python-$PY_VER" "libffi-$FFI_VER" "openssl-$SSL_VER"
tar xf "tcl-$TCL_VER.tar.gz"; tar xf "tk-$TK_VER.tar.gz"; tar xf "python-$PY_VER.tgz"
tar xf "libffi-$FFI_VER.tar.gz"; tar xf "openssl-$SSL_VER.tar.gz"

export PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig"
export LD_LIBRARY_PATH="$PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# --------------------------------------------------------------- 2. libffi
echo "==== libffi $FFI_VER ===="
cd "$SRC/libffi-$FFI_VER"
./configure --prefix="$PREFIX" --disable-static --disable-docs >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null

# --------------------------------------------------------------- 2b. OpenSSL
# Wird fuer das Python-ssl-Modul benoetigt (HTTPS-Zugriff auf die Kameras).
# install_sw: nur Bibliotheken/Header, keine Doku. rpath, damit libssl seine
# libcrypto im selben lib/-Verzeichnis findet.
echo "==== OpenSSL $SSL_VER ===="
cd "$SRC/openssl-$SSL_VER"
./Configure --prefix="$PREFIX" --libdir=lib --openssldir="$PREFIX/ssl" \
            shared -Wl,-rpath,'$ORIGIN/../lib' >/dev/null
make -j"$JOBS" >/dev/null
make install_sw >/dev/null

# --------------------------------------------------------------- 3. Tcl 9
echo "==== Tcl $TCL_VER ===="
cd "$SRC/tcl$TCL_VER/unix"
./configure --prefix="$PREFIX" --enable-shared --enable-64bit >/dev/null
# Die mitgelieferten Pakete (tdbc, thread) werden mit dem gerade gebauten tclsh
# konfiguriert; das findet libtcl9.0.so nur ueber das Build-Verzeichnis.
LD_LIBRARY_PATH="$PWD:$LD_LIBRARY_PATH" make -j"$JOBS" >/dev/null
LD_LIBRARY_PATH="$PWD:$LD_LIBRARY_PATH" make install >/dev/null
# tclsh-Symlink fuer Tk-configure
ln -sf "$PREFIX/bin/tclsh$TCL_VER" "$PREFIX/bin/tclsh${TCL_VER%.*}" 2>/dev/null || true

# --------------------------------------------------------------- 4. Tk 9
echo "==== Tk $TK_VER ===="
cd "$SRC/tk$TK_VER/unix"
./configure --prefix="$PREFIX" --with-tcl="$PREFIX/lib" \
            --enable-shared --enable-64bit --enable-xft >/dev/null
make -j"$JOBS" >/dev/null
make install >/dev/null

# --------------------------------------------------------------- 5. Python
echo "==== Python $PY_VER (gegen Tcl/Tk 9) ===="
cd "$SRC/Python-$PY_VER"
./configure \
    --prefix="$PREFIX" \
    --enable-shared \
    --with-ensurepip=no \
    --with-openssl="$PREFIX" \
    --with-openssl-rpath=auto \
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
echo ">> OpenSSL-Version im neuen Python:"
"$PYBIN" -c "import ssl; print('  ', ssl.OPENSSL_VERSION)"

# --------------------------------------------------------------- 6. Wheels vendoren
echo "==== Laufzeit-Pakete (cp314-Wheels) ===="
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
# 'cp314-cp314-' statt nur 'cp314': es gibt auch ein cp314t-Wheel (free-threaded
# ABI), das zu diesem Interpreter nicht passt.
wheel zeroconf    "'cp314-cp314-' in n and 'manylinux' in n and 'x86_64' in n"
wheel ifaddr      "n.endswith('.whl')"
wheel prettytable "n.endswith('.whl')"
# wcwidth (Abhaengigkeit von prettytable)
wheel wcwidth     "n.endswith('.whl')"
# Modernes Sun-Valley-Theme (reines py3-none-any-Wheel inkl. Tcl-Dateien)
wheel sv-ttk      "n.endswith('.whl')"

# --------------------------------------------------------------- 7. App + AppDir
echo "==== AppDir zusammenstellen ===="
mkdir -p "$APPDIR/app"
cp "$ROOT/axis_kamera_discovery_gui.py" "$ROOT/axis_kamera_discovery_cli.py" \
   "$ROOT/axis_kamera_discovery_vapix.py" \
   "$ROOT/README.md" "$ROOT/THIRD_PARTY_LICENSES.md" "$ROOT/LICENSE" "$APPDIR/app/"

# Desktop + Icon (fuer appimagetool im AppDir-Wurzelverzeichnis)
cp "$ROOT/appimage/Axis_Kamera_Discovery/Axis_Kamera_Discovery.png" "$APPDIR/Axis_Kamera_Discovery.png"
cat > "$APPDIR/Axis_Kamera_Discovery.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Axis_Kamera_Discovery
GenericName=Axis_Kamera_Discovery
Comment=Findet Axis-Kameras im lokalen Netzwerk per Zeroconf
Exec=AppRun %u
Icon=Axis_Kamera_Discovery
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
    cli) shift; exec "\$PY" "\$HERE/app/axis_kamera_discovery_cli.py" "\$@" ;;
    -*)  exec "\$PY" "\$HERE/app/axis_kamera_discovery_cli.py" "\$@" ;;
    *)   exec "\$PY" "\$HERE/app/axis_kamera_discovery_gui.py" "\$@" ;;
esac
APPRUN
chmod +x "$APPDIR/AppRun"

# --------------------------------------------------------------- Verschlanken
# Alles entfernen, was zur Laufzeit nicht gebraucht wird: die App vendort fertige
# Wheels und kompiliert nichts nach. Das drueckt das AppImage grob von ~58 MB auf
# ~20 MB.
echo "==== AppDir verschlanken ===="
PYLIB="$PREFIX/lib/python$PY_XY"

# (a) Statische Bibliotheken + C-Header -- nur zum Kompilieren noetig
#     (u. a. das 69-MB-libpython3.14.a im config-Verzeichnis).
find "$PREFIX" -name '*.a' -delete 2>/dev/null || true
rm -rf "$PREFIX/include" 2>/dev/null || true

# (b) Handbuchseiten/Doku.
rm -rf "$PREFIX/share/man" "$PREFIX/share/doc" 2>/dev/null || true

# (c) Ungenutzte Stdlib-Teile: IDLE-IDE, pip-Bootstrap, pydoc-Daten, turtle-Demo,
#     tkinter-Tests und alle Testsuiten.
rm -rf "$PYLIB/idlelib" "$PYLIB/ensurepip" "$PYLIB/pydoc_data" \
       "$PYLIB/turtledemo" "$PYLIB/tkinter/test" 2>/dev/null || true
rm -rf "$PYLIB/test" "$PYLIB/"*/test "$PYLIB/"*/tests 2>/dev/null || true

# (d) Test-/Beispiel-C-Extensions in lib-dynload.
find "$PYLIB/lib-dynload" \( -name '_test*' -o -name '_xxtest*' \
       -o -name 'xxlimited*' -o -name '_ctypes_test*' \) -delete 2>/dev/null || true

# (e) Tcl-Erweiterungen ohne Tk-Bezug (DB-Connectivity, incrTcl, Thread-Paket).
rm -rf "$PREFIX"/lib/itcl* "$PREFIX"/lib/tdbc* \
       "$PREFIX"/lib/sqlite* "$PREFIX"/lib/thread* 2>/dev/null || true

# (f) Debug-Symbole aus allen ELF-Objekten strippen (--strip-unneeded behaelt die
#     dynamischen Symbole -> Laufzeit unveraendert). AUSNAHME: libtcl*/libtk* --
#     Tcl 9 haengt seine Script-Library als zipfs an die .so an; strip wuerde
#     diese Daten abschneiden ("Cannot find a usable init.tcl").
find "$PREFIX" \( -name '*.so' -o -name '*.so.*' \) \
     ! -name '*tcl*' ! -name '*tk*' \
     -exec strip --strip-unneeded {} + 2>/dev/null || true
strip --strip-unneeded "$PREFIX/bin/python$PY_XY" 2>/dev/null || true

find "$PREFIX" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true

# --------------------------------------------------------------- 8. AppImage packen
echo "==== AppImage packen ===="
AIT="$BUILD/appimagetool-x86_64.AppImage"
dl "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" "$AIT"
chmod +x "$AIT"

VERSION="$(python3 "$ROOT/bump_version.py" --print)"
OUT="$ROOT/Axis_Kamera_Discovery-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "$AIT" --appimage-extract-and-run "$APPDIR" "$OUT" 2>&1 | tail -5
ln -sfn "$(basename "$OUT")" "$ROOT/Axis_Kamera_Discovery-x86_64.AppImage"

echo ">> Fertig: $OUT"
