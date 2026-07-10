# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Spec fuer Axis_Kamera_Discovery (Windows-.exe).
# Erzeugt zwei eigenstaendige One-File-Programme in dist\ (mit Versionsnummer
# im Dateinamen, z. B. bei 26.07.10):
#   Axis_Kamera_Discovery_26.07.10.exe      - GUI (ohne Konsolenfenster)
#   Axis_Kamera_Discovery_cli_26.07.10.exe  - CLI (Konsolenanwendung)
#
# Bauen (auf Windows):  pyinstaller --noconfirm Axis_Kamera_Discovery.spec
#
# Funktionsgleich zur Linux-Version: dieselben .py-Module werden gebuendelt.
# Unter Linux wird stattdessen das AppImage via build_appimage.sh erzeugt.

import re

from PyInstaller.utils.hooks import collect_submodules

# Versionsnummer aus dem CLI-Modul lesen (einzige Quelle, gepflegt von
# bump_version.py) und an die EXE-Namen anhaengen -> z. B.
#   Axis_Kamera_Discovery_26.07.10.exe
with open("axis_kamera_discovery_cli.py", encoding="utf-8") as _f:
    VERSION = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', _f.read()).group(1)

# README/Lizenzen mit ins Bundle (GUI zeigt sie unter "Hilfe"/"Lizenzen";
# zur Laufzeit ueber sys._MEIPASS gefunden).
datas = [
    ("README.md", "."),
    ("THIRD_PARTY_LICENSES.md", "."),
    ("LICENSE", "."),
]

# zeroconf/ifaddr laden Teile dynamisch -> Submodule explizit einsammeln.
hiddenimports = collect_submodules("zeroconf") + collect_submodules("ifaddr")

ICON = "appimage/Axis_Kamera_Discovery/Axis_Kamera_Discovery.ico"

block_cipher = None


def _exe(entry, name, console):
    a = Analysis(
        [entry],
        pathex=["."],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        runtime_hooks=[],
        excludes=[],
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
    return EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=name,
        console=console,
        icon=ICON,
        upx=False,
        bootloader_ignore_signals=False,
        debug=False,
        strip=False,
        runtime_tmpdir=None,
        disable_windowed_traceback=False,
    )


gui_exe = _exe("axis_kamera_discovery_gui.py", f"Axis_Kamera_Discovery_{VERSION}", console=False)
cli_exe = _exe("axis_kamera_discovery_cli.py", f"Axis_Kamera_Discovery_cli_{VERSION}", console=True)
