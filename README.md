# Axis IP Utility

Findet **Axis-Netzwerkkameras** im lokalen Netz per Zeroconf/mDNS
(`_axis-video._tcp.local.`) und zeigt sie mit folgenden Spalten an:

| Spalte | Inhalt |
|---|---|
| Name | Gerätename |
| IP Adresse: Zeroconfig | Link-Local-/Zeroconf-Adresse (`169.254.x.x`) |
| IP Adresse: Konfiguriert | konfigurierte (reguläre) IP-Adresse |
| Port | HTTP-Port |
| Hostname | mDNS-Hostname |
| MAC-Adresse/Seriennummer | MAC bzw. Seriennummer |

Das Projekt enthält zwei Oberflächen mit **identischem Funktionsumfang**:

- **GUI** (`axis_discovery_gui.py`) – grafische Tkinter-Oberfläche
- **CLI** (`axis_discovery_cli.py`) – Kommandozeilen-Werkzeug

Beide lassen sich als **eigenständiges AppImage** bündeln, das ein komplettes
Python 3.13 inklusive **Tcl/Tk 9** sowie alle Abhängigkeiten mitbringt und damit
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
| Kamera-IP ändern (DHCP/fest, Mehrfachauswahl) | „Kamera Einstellungen" | – |
| Benutzer/ONVIF-Benutzer anlegen oder Passwort ändern | „Kamera Einstellungen" | – |
| Dark Mode (heller/dunkler Modus) | Einstellungen → Checkbox „Dark Mode" | – |
| Version anzeigen | im Fenstertitel | `--version/-v` |

---

## Voraussetzungen

- **Nutzung des AppImage:** keine – nur Linux x86_64 (FUSE2 empfohlen).
- **Direkt aus dem Quellcode:** Python 3 mit den Paketen `zeroconf` und
  `prettytable` sowie Tkinter (`python3-tk`).
- **AppImage selbst bauen:** C-Compiler (`gcc`/`make`), X11- und
  Xft-/fontconfig-/freetype-Dev-Header sowie Internetzugang. Tcl 9, Tk 9 und
  Python 3.13 werden aus dem Quellcode kompiliert (dauert einige Minuten).

---

## Schnellstart (AppImage)

```bash
# Bauen (Tcl/Tk 9 + Python 3.13 aus Quellcode)
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
- **Spaltenbreiten** passen sich nach jeder Suche automatisch an den breitesten
  Inhalt (inkl. Überschrift) an.
- **Klick auf eine Spaltenüberschrift** – sortiert die Tabelle nach dieser
  Spalte; erneuter Klick kehrt die Richtung um (auf-/absteigend, Pfeil ▲/▼).
  Port wird numerisch, IP-Adressen werden nach Oktetten sortiert.
- **Doppelklick** auf eine Zeile – öffnet `http://<IP>` (Weboberfläche der
  Kamera) im Browser.
- **Exportieren…** – speichert die Ergebnisse als CSV oder Texttabelle
  (Format folgt der gewählten Dateiendung).
- **Kamera Einstellungen** (Button links neben „Einstellungen") – ändert
  Einstellungen an den in der Liste **markierten** Kameras (Mehrfachauswahl
  möglich). Öffnet einen Dialog mit Zugangsdaten (Benutzer/Passwort,
  Verbindung `auto`/`https`/`http`, optionaler Port, Timeout) und einem
  „Verbindung testen"-Knopf (lesend, ohne Änderung). Der Dialog hat Reiter für
  die einzelnen Aktionen:
  - **IP-Adresse** ändern in drei Varianten: *Auf DHCP umstellen*,
    *Feste IP ab Start-IP fortlaufend* (vergibt fortlaufende Adressen) oder
    *Pro Kamera einzeln* (je Kamera ein eigenes IP-Feld).
  - **Benutzer** – regulären Axis-Benutzer *anlegen* (mit Rolle
    Administrator/Operator/Viewer) oder *Passwort ändern*. Ist die Kamera noch
    im **Auslieferungszustand**, hilft die Checkbox *Auslieferungszustand*: Sie
    probiert für den Zugriff zuerst „ohne Anmeldung" (moderne werksneue Geräte)
    und dann gängige **Standard-Zugangsdaten** (root/pass, root/root, …; ältere
    Geräte wie die M7001 antworten auf root/pass). Der (Erst-)Benutzer wird in
    diesem Fall als **Administrator** angelegt; im Ergebnis steht, welcher Zugang
    funktioniert hat. Das gilt auch für *Passwort ändern* (z. B. das
    Standard-Passwort von `root` ersetzen). Zur **Ersteinstellung** genügt für
    **alle** Kameratypen derselbe Ablauf: Checkbox *Auslieferungszustand*
    anhaken, *Benutzer anlegen* mit Benutzer `root` + Passwort. Das Tool wählt
    automatisch den passenden Weg:
    - **Moderne Kameras** (AXIS OS, kein Standardkonto): legt den Erstadmin
      unauthentifiziert als Administrator an (intern `grp=root`, ohne `comment`,
      wie von AXIS OS gefordert).
    - **Ältere Kameras** (z. B. M7001, antworten auf `root/pass`): da `root`
      bereits existiert, wird stattdessen automatisch dessen Passwort gesetzt.
  - **ONVIF-Benutzer** – ONVIF-Benutzer *anlegen* (Stufe
    Administrator/Operator/User) oder *Passwort ändern*.

  Die Aufrufe laufen über die Axis-VAPIX-API bzw. den ONVIF-Dienst (HTTPS mit
  selbstsignierten Zertifikaten wird unterstützt); das Ergebnis wird je Kamera
  angezeigt. *(Weitere Funktionen wie Firmware-Update und Konfigurationsdateien
  sind in Entwicklung.)*
- **Einstellungen** (Menü-Button rechts neben „Exportieren") mit den Einträgen:
  - **Dark Mode** – Checkbox; angehakt schaltet die Oberfläche auf den dunklen
    Modus um, ohne Haken gilt der helle Modus. Die Einstellung bleibt über
    Neustarts erhalten – sie wird in der gemeinsamen Einstellungsdatei
    `~/.config/axis_ip_utility/settings.json` (bzw. `$XDG_CONFIG_HOME`) abgelegt,
    in der auch künftige Einstellungen gespeichert werden.
  - **Info** – Programmname und Version
  - **Hilfe** – zeigt diese README in einem Fenster
  - **Lizenzen** – zeigt `THIRD_PARTY_LICENSES.md` (Lizenzen der gebündelten
    Komponenten) in einem Fenster

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
├── build_appimage.sh            # Build (Tcl/Tk 9 + Python 3.13 aus Quellcode)
├── appimage/AxisDiscovery/
│   └── AxisDiscovery.png        # Icon für das AppImage
├── THIRD_PARTY_LICENSES.md      # Lizenzen der gebündelten Komponenten
├── LICENSE                      # GPL-3.0 Lizenztext
└── README.md
```

> Hinweis: `.tk9build/`, `*.AppImage` und `__pycache__/` sind per `.gitignore`
> vom Repository ausgeschlossen. Der Build erzeugt `AppRun` und den
> `.desktop`-Eintrag selbst.

---

## Lizenz

Dieses Programm steht unter der **GNU General Public License v3.0 oder später
(GPL-3.0-or-later)** – siehe [LICENSE](LICENSE).

Copyright (C) 2026 Mirik

Die im AppImage gebündelten Drittanbieter-Komponenten behalten ihre jeweils
eigenen Lizenzen, dokumentiert in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

> **Hinweis:** Dieses Programm wurde mit Hilfe von KI (Claude Opus 4.8,
> Anthropic) entwickelt.
