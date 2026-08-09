# Windows-Build (.exe)

Die Windows-Version ist **funktionsgleich** zur Linux-Version – es werden
dieselben Python-Module gebündelt. Statt eines AppImage entstehen zwei
eigenständige One-File-Programme:

Die Dateinamen enthalten die Versionsnummer (z. B. bei 26.07.10):

- `Axis_Kamera_Discovery_26.07.10.exe` – grafische Oberfläche (ohne Konsolenfenster)
- `Axis_Kamera_Discovery_cli_26.07.10.exe` – Kommandozeile (mit allen Unterbefehlen)

> Unterschied zum Linux-AppImage nur beim Start: Dort wählt *eine* Datei per
> Argument GUI/CLI; unter Windows gibt es dafür zwei Exes. Der Funktionsumfang
> ist identisch.

## Lokal bauen (auf einem Windows-11-Rechner)

Voraussetzung: **Python 3.14** (vom python.org-Installer – enthält Tkinter und
`ssl`).

PyInstaller baut die `.exe` immer für **genau den Interpreter, mit dem es
aufgerufen wird**. Sind mehrere Python-Versionen installiert, greifen die blanken
Befehle `pip` / `pyinstaller` auf das erstbeste Python im `PATH` zu – dann
entsteht trotz aller Einstellungen im Projekt eine `.exe` gegen die alte Version.
Deshalb den Interpreter über den Python-Launcher `py` explizit wählen:

```powershell
py -0p                 # zeigt alle installierten Versionen und ihre Pfade
py -3.14 -V            # muss "Python 3.14.x" ausgeben

py -3.14 -m pip install --upgrade "pyinstaller>=6.11" zeroconf prettytable ifaddr sv-ttk
py -3.14 -m PyInstaller --noconfirm Axis_Kamera_Discovery.spec
```

> **Wichtig – PyInstaller aktuell halten:** Python 3.14 bringt **Tcl/Tk 9** mit.
> Nur ein **aktuelles** PyInstaller (≥ 6.11, am besten das neueste) bündelt dessen
> Datenverzeichnis korrekt. Eine ältere, bereits installierte Version bricht sonst
> beim Start der Exe ab mit
> `FileNotFoundError: Tcl data directory "...\_tcl_data" not found`. Deshalb
> unbedingt mit **`--upgrade`** installieren (ein blankes `pip install` lässt eine
> vorhandene alte Version stehen). `pip` wählt automatisch das neueste PyInstaller,
> das Python 3.14 unterstützt.

PyInstaller schreibt die verwendete Version zu Beginn ins Log
(`INFO: Python: 3.14.x`) – dort lässt sich prüfen, ob wirklich 3.14 gebaut wurde.
Die fertigen Exes liegen danach in `dist\`.

Bequemer geht es mit dem mitgelieferten Skript, das Python 3.14 selbst sucht
(über den `py`-Launcher), die Abhängigkeiten installiert und den Build startet:

```powershell
.\build_windows.ps1              # optional: -Clean, -ForceReinstall
.\build_windows.ps1 -PythonPath "C:\Pfad\zu\Python314\python.exe"
```

Findet es kein Python 3.14, bricht es mit einer Meldung ab, statt still mit einer
älteren Version zu bauen.

> Der Build nimmt **nicht** die Version aus `windows-build.yml` – die gilt nur
> für den CI-Runner. Lokal zählt allein das aufgerufene Python.

Aus dem Quellcode starten (ohne Build) geht ebenso:

```powershell
pip install zeroconf prettytable sv-ttk
python axis_kamera_discovery_gui.py
```

## Automatisch bauen (CI)

`.github/workflows/windows-build.yml` baut die Exes auf einem **Windows-Runner**
(GitHub Actions *oder* Forgejo/Gitea Actions – beide lesen `.github/workflows`).
Auslösen: manuell („Run workflow") oder durch einen Versions-Tag `v*`. Das
Ergebnis liegt als Artefakt `Axis_Kamera_Discovery-windows` (die `.exe`-Dateien).

> Forgejo: Actions müssen aktiviert und ein **Windows-Runner** registriert sein.
> PyInstaller kann nicht cross-kompilieren – der Build muss auf Windows laufen.

## Hinweise

- **Windows-Firewall**: Beim ersten Start fragt Windows nach Freigabe für die
  Netzwerksuche (mDNS/UDP 5353). Für „Private Netzwerke" zulassen, sonst werden
  keine Kameras gefunden.
- **SmartScreen**: Unsignierte Exes lösen beim ersten Start eine Warnung aus
  („Weitere Informationen" → „Trotzdem ausführen"). Optional per Code-Signing
  vermeiden.
- **Einstellungen** werden unter Windows **portabel** neben der EXE abgelegt
  (`settings.json` im selben Verzeichnis wie die `.exe`; im Quellbetrieb neben
  dem Skript). So bleibt die Konfiguration bei einem mitgeführten Programmordner
  (z. B. USB-Stick) erhalten. Unter Linux unverändert in
  `~/.config/axis_kamera_discovery/`.
- **Tcl/Tk**: Python 3.14 bringt **Tcl/Tk 9** mit (frühere 3.x brachten Tk 8.6);
  alle genutzten Widgets und das moderne **Sun-Valley-Theme** (`sv-ttk`,
  Hell/Dunkel) funktionieren damit. Fehlt `sv-ttk`, faellt die GUI automatisch auf
  das `clam`-Theme zurueck.
- **Fehler „Tcl data directory … _tcl_data not found"** beim Start der fertigen
  Exe: Das PyInstaller ist zu alt für Tcl/Tk 9. Mit
  `py -3.14 -m pip install --upgrade pyinstaller` aktualisieren und neu bauen
  (siehe oben). Das mitgelieferte `build_windows.ps1` und die CI installieren
  bereits mit `--upgrade`.
