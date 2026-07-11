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

```powershell
pip install pyinstaller zeroconf prettytable ifaddr
pyinstaller --noconfirm Axis_Kamera_Discovery.spec
```

Die fertigen Exes liegen danach in `dist\`.

Aus dem Quellcode starten (ohne Build) geht ebenso:

```powershell
pip install zeroconf prettytable
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
- **Tcl/Tk**: Windows-Python bringt Tk 8.6 mit; alle genutzten Widgets und das
  `clam`-Theme (Dark Mode) funktionieren damit.
