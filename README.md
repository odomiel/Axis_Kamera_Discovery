# Axis IP Utility

Findet **Axis-Netzwerkkameras** im lokalen Netz per Zeroconf/mDNS
(`_axis-video._tcp.local.`) und zeigt Name, IP-Adresse(n), Port, Hostname und
MAC-Adresse/Seriennummer an.

Das Projekt enthält zwei Oberflächen mit **identischem Funktionsumfang**:

- **GUI** (`axis_discovery_gui.py`) – grafische Tkinter-Oberfläche
- **CLI** (`axis_discovery_cli.py`) – Kommandozeilen-Werkzeug

Beide lassen sich als **eigenständiges AppImage** bündeln, das ein komplettes
Python inklusive Tkinter/Tcl-Tk sowie alle Abhängigkeiten mitbringt und damit
**unabhängig von der System-Installation** läuft.

---

## Funktionen

| Funktion | GUI | CLI |
|---|---|---|
| Kamera-Suche per Zeroconf/mDNS | „Suchen"-Button | Standardaktion |
| Such-Dauer einstellbar | Feld „Dauer (s)" | `--timeout/-t` |
| Ergebnis-Tabelle anzeigen | immer | `--show/-s` |
| Export als Texttabelle | Dialog (`.txt`) | `-o datei.txt` |
| Export als CSV | Dialog (`.csv`) | `-o datei.csv` / `--format csv` |
| Wiederholte Suche (Auto-Refresh) | Checkbox + Intervall | `--watch/-w SEKUNDEN` |
| Kamera-Weboberfläche im Browser öffnen | Doppelklick auf Zeile | `--open` |
| Version anzeigen | im Fenstertitel | `--version/-v` |

---

## Voraussetzungen

- **Nutzung des AppImage:** keine – nur Linux x86_64 (FUSE2 empfohlen).
- **Direkt aus dem Quellcode:** Python 3 mit den Paketen `zeroconf` und
  `prettytable` sowie Tkinter (`python3-tk`).
- **AppImage selbst bauen:** Python 3 mit `venv`/`ensurepip` und Internetzugang
  (lädt das eigenständige Python und `python-appimage`).

---

## Schnellstart (AppImage)

```bash
# Bauen
./build_appimage.sh

# GUI starten (oder im Dateimanager doppelklicken)
./AxisDiscovery-x86_64.AppImage
```

Beim Build entstehen:

- `AxisDiscovery-<version>-x86_64.AppImage` – versioniertes Artefakt
- `AxisDiscovery-x86_64.AppImage` – Symlink auf die aktuelle Version

---

## GUI

Start ohne Argumente öffnet das Fenster:

```bash
./AxisDiscovery-x86_64.AppImage
# oder direkt aus dem Quellcode:
python3 axis_discovery_gui.py
```

Bedienung:

- **Suchen** – startet die Suche im Hintergrund (Fenster bleibt bedienbar).
- **Dauer (s)** – Suchdauer (1–60 s, Standard 10).
- **Auto-Refresh** + **alle (s)** – wiederholt die Suche automatisch im
  eingestellten Intervall (5–3600 s).
- **Doppelklick** auf eine Zeile – öffnet `http://<IP>` (Weboberfläche der
  Kamera) im Browser.
- **Exportieren…** – speichert die Ergebnisse als CSV oder Texttabelle
  (Format folgt der gewählten Dateiendung).

---

## CLI

Über das AppImage wird das CLI mit dem Schlüsselwort `cli` **oder** einfach
durch Angabe eines Flags aufgerufen:

```bash
./AxisDiscovery-x86_64.AppImage cli --help
./AxisDiscovery-x86_64.AppImage --show          # Flag genügt -> CLI

# Direkt aus dem Quellcode:
python3 axis_discovery_cli.py --help
```

### Optionen

| Option | Beschreibung |
|---|---|
| `-o, --output DATEI` | Ergebnisse in Datei exportieren |
| `-f, --format {txt,csv}` | Exportformat erzwingen (sonst aus Dateiendung, Standard `txt`) |
| `-t, --timeout SEKUNDEN` | Such-Dauer (Standard 10) |
| `-w, --watch SEKUNDEN` | Suche im Intervall wiederholen (Abbruch mit `Ctrl+C`) |
| `--open` | gefundene Kameras im Browser öffnen (je IP einmal) |
| `-s, --show` | Ergebnis-Tabelle in der Konsole anzeigen |
| `-v, --version` | Version anzeigen |
| `-h, --help` | Hilfe anzeigen |

### Beispiele

```bash
# Einmalige Suche, Tabelle in der Konsole
python3 axis_discovery_cli.py --show

# 15 Sekunden suchen und als CSV exportieren
python3 axis_discovery_cli.py -t 15 -o kameras.csv

# Als Texttabelle exportieren (Format per Flag erzwungen)
python3 axis_discovery_cli.py -o kameras.txt -f txt

# Alle 30 Sekunden suchen und Ergebnis anzeigen
python3 axis_discovery_cli.py --watch 30 --show

# Gefundene Kameras im Browser öffnen
python3 axis_discovery_cli.py --open

# Über das AppImage
./AxisDiscovery-x86_64.AppImage cli -t 20 -o kameras.csv
```

---

## Versionsschema

Format **`JJ.MM.TT`** (zweistelliges Jahr). Erscheinen an einem Tag mehrere
Releases, wird ein hochzählendes Suffix `b1`, `b2`, … angehängt
(z. B. `26.06.20`, dann `26.06.20b1`, `26.06.20b2`).

Gepflegt wird die Version über `bump_version.py`:

```bash
python3 bump_version.py --print     # aktuelle Version anzeigen
python3 bump_version.py --dry-run   # nächste Version berechnen (nicht schreiben)
python3 bump_version.py             # nächste Version setzen und in den Code schreiben

# Beim Build automatisch hochzählen:
./build_appimage.sh --bump
```

---

## Projektstruktur

```
axis_IP_Utility/
├── axis_discovery_cli.py        # Discovery-Kernlogik + CLI
├── axis_discovery_gui.py        # Tkinter-GUI (nutzt die Kernlogik)
├── bump_version.py              # Versionsverwaltung (JJ.MM.TT + bN)
├── build_appimage.sh            # Build-Skript für das AppImage
├── appimage/AxisDiscovery/      # AppImage-Rezept
│   ├── AxisDiscovery.desktop    #   Desktop-Eintrag
│   ├── AxisDiscovery.png        #   Icon
│   ├── entrypoint.sh            #   Starter-Weiche GUI/CLI
│   └── requirements.txt         #   gebündelte Pakete (zeroconf, prettytable)
└── README.md
```

> Hinweis: `.buildenv/`, `*.AppImage` und `__pycache__/` sind per `.gitignore`
> vom Repository ausgeschlossen.
