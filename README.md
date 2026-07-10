# Axis_Kamera_Discovery

Findet **Axis-Netzwerkkameras** im lokalen Netz per Zeroconf/mDNS
(`_axis-video._tcp.local.`) und zeigt sie mit folgenden Spalten an:

| Spalte | Inhalt |
|---|---|
| Name | Kameratyp/Modell (ohne Seriennummer) |
| IP Adresse: Zeroconfig | Link-Local-/Zeroconf-Adresse (`169.254.x.x`) |
| IP Adresse: Konfiguriert | konfigurierte (reguläre) IP-Adresse |
| Port | HTTP-Port |
| Hostname | mDNS-Hostname |
| MAC-Adresse/Seriennummer | MAC bzw. Seriennummer |

Das Projekt enthält zwei Oberflächen mit **identischem Funktionsumfang**:

- **GUI** (`axis_kamera_discovery_gui.py`) – grafische Tkinter-Oberfläche
- **CLI** (`axis_kamera_discovery_cli.py`) – Kommandozeilen-Werkzeug

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
| Export (nur sichtbare Spalten) | immer (GUI: nur eingeblendete Spalten) | immer (CLI: alle Spalten) |
| Wiederholte Suche (Auto-Refresh) | Checkbox + Intervall | `--watch/-w SEKUNDEN` |
| Kamera-Weboberfläche im Browser öffnen | Doppelklick auf Zeile | `--open` |
| Kamera-IP ändern (DHCP/fest, Mehrfachauswahl) | „Kamera Einstellungen" | `set-ip` / `set-dhcp` |
| Benutzer/ONVIF-Benutzer anlegen oder Passwort ändern | „Kamera Einstellungen" | `user-add`/`user-passwd`/`onvif-add`/`onvif-passwd` |
| Benutzer/ONVIF-Benutzer aus Textdatei importieren (Stapel) | „Kamera Einstellungen" | `user-import`/`onvif-import` |
| Firmware-Update (Mehrfachauswahl) | „Kamera Einstellungen" | `firmware` |
| ADM-Konfigurationsdatei anwenden | „Kamera Einstellungen" | `config` |
| Konfiguration auslesen & als ADM-`.cfg` speichern | „Kamera Einstellungen" | `config-export` |
| Dark Mode (heller/dunkler Modus) | Einstellungen → Checkbox „Dark Mode" | – |
| Sprache (Deutsch/Englisch) | Einstellungen → Radiobuttons | – |
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
./Axis_Kamera_Discovery-x86_64.AppImage
```

Beim Build entstehen:

- `Axis_Kamera_Discovery-<version>-x86_64.AppImage` – versioniertes Artefakt
- `Axis_Kamera_Discovery-x86_64.AppImage` – Symlink auf die aktuelle Version

### Windows (.exe)

Für Windows 11 gibt es eine **funktionsgleiche** Variante (zwei One-File-Exes:
GUI + CLI), gebaut mit PyInstaller. Anleitung und CI-Workflow:
siehe [`BUILD_WINDOWS.md`](BUILD_WINDOWS.md).

---

## GUI

Start ohne Argumente öffnet das Fenster:

```bash
./Axis_Kamera_Discovery-x86_64.AppImage
# oder direkt aus dem Quellcode:
python3 axis_kamera_discovery_gui.py
```

Bedienung:

- **Suchen** – startet die Suche im Hintergrund (Fenster bleibt bedienbar).
- **Dauer (s)** – Suchdauer (1–60 s, Standard 10).
- **Auto-Refresh** + **alle (s)** – wiederholt die Suche automatisch im
  eingestellten Intervall (5–3600 s).
- **Hinweis in Rot** – "Nutzung des Programms auf eigene Gefahr" (zwischen Auto-Refresh und Progressbar). Auto-Refresh-Status, Intervall und
  Such-Dauer werden gespeichert (`settings.json`) und beim nächsten Start wieder
  hergestellt; war Auto-Refresh aktiv, läuft die Suche automatisch weiter.
- **Spaltenbreiten** passen sich nach jeder Suche automatisch an den breitesten
  Inhalt (inkl. Überschrift) an.
- **Klick auf eine Spaltenüberschrift** – sortiert die Tabelle nach dieser
  Spalte; erneuter Klick kehrt die Richtung um (auf-/absteigend, Pfeil ▲/▼).
  Port wird numerisch, IP-Adressen werden nach Oktetten sortiert.
- **Doppelklick** auf eine Zeile – öffnet `http://<IP>` (Weboberfläche der
  Kamera) im Browser.
- **Exportieren…** – speichert die Ergebnisse als CSV oder Texttabelle
  (Format folgt der gewählten Dateiendung). **Nur die aktuell eingeblendeten
  Spalten werden exportiert** (über "Spalten…" einstellbar).
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

    Über *Benutzerliste wählen und anlegen…* lassen sich außerdem **mehrere
    Benutzer auf einmal aus einer Textdatei importieren**. Eine Zeile je
    Benutzer: `Name,Passwort,Rolle` – die Rolle ist optional (Standard
    `viewer`), gültig sind `administrator`/`operator`/`viewer`. Passwörter mit
    Komma in `"…"` setzen, Zeilen mit `#` sind Kommentare. Die angehakte Option
    *Auslieferungszustand* gilt auch für den Import (legt dann als Administrator
    an). Jeder Benutzer wird auf allen markierten Kameras angelegt; das Ergebnis
    wird je Kamera/Benutzer protokolliert.
  - **ONVIF-Benutzer** – ONVIF-Benutzer *anlegen* (Stufe
    Administrator/Operator/User) oder *Passwort ändern*. Auch hier ist über
    *Benutzerliste wählen und anlegen…* ein **Stapel-Import aus einer Textdatei**
    möglich (`Name,Passwort,Stufe`; Stufe optional, Standard `User`; gültig
    `Administrator`/`Operator`/`User`).

  - **Firmware** – spielt eine Firmware-Datei (`.bin`) auf die markierten
    Kameras (moderne JSON-API `firmwaremanagement.cgi`, mit Rückfall auf das
    ältere `firmwareupgrade.cgi`). ⚠️ Die Firmware muss zum Kameramodell passen;
    nur Kameras gleichen Modells gemeinsam auswählen. Der Vorgang dauert einige
    Minuten, danach startet die Kamera neu. Optional „factory default".

  - **Konfiguration** – wendet eine Konfigurationsdatei (`.cfg`) aus dem Axis
    Device Manager an. Nach der Auswahl zeigt der Dialog Modell, Firmware und
    Anzahl der enthaltenen Parameter/Profile (und ob eine **Bewegungserkennung
    (VMD4)** enthalten ist). Die enthaltenen Parameter werden per `param.cgi`
    gesetzt; optional werden auch die **Stream-Profile** übernommen (einheitlich
    über `param.cgi`): gleichnamige vorhandene Profile werden **überschrieben**,
    neue angelegt. Schreibgeschützte `Properties.*`-Parameter werden dabei
    automatisch übersprungen (neuere Firmware wies sonst den gesamten Batch ab).
    Enthält die Datei eine **Bewegungserkennung (VMD4)**, wird diese über die
    VMD4-Steuer-API mit angewendet (die VMD-Anwendung wird bei Bedarf zuvor
    gestartet). Die Datei sollte zum Modell passen.

    Im selben Reiter lässt sich umgekehrt die **Konfiguration einer Kamera
    auslesen und als ADM-`.cfg` speichern**: „Aus Kamera auslesen und
    speichern…" liest die komplette Parameterliste der **ersten markierten**
    Kamera. Anschließend öffnet sich ein Auswahl-Dialog, in dem die zu
    speichernden Parameter per Häkchen an-/abgewählt und über ein **Suchfeld**
    gefiltert werden können („Alle/Keine (gefiltert)" wirkt auf die aktuell
    angezeigten Treffer); optional werden die **Stream-Profile** und – falls auf
    der Kamera vorhanden – die **Bewegungserkennung (VMD4)** mitgespeichert.
    ⚠️ Ein vollständiger Export enthält auch geräte­spezifische bzw. nur lesbare
    Werte (z. B. Seriennummer/MAC) – für die Übertragung auf **andere** Kameras
    nur passende Parameter auswählen. Die erzeugte Datei ist wieder über
    „Konfiguration" anwendbar.

  Die Aufrufe laufen über die Axis-VAPIX-API bzw. den ONVIF-Dienst (HTTPS mit
  selbstsignierten Zertifikaten wird unterstützt); das Ergebnis wird je Kamera
  angezeigt.
- **Einstellungen** (Menü-Button rechts neben „Exportieren") mit den Einträgen:
  - **Spalten…** – öffnet einen Dialog mit einer Checkbox je Tabellenspalte;
    abgewählte Spalten werden ausgeblendet. Die Auswahl wird in `settings.json`
    gespeichert (mindestens eine Spalte bleibt sichtbar).
  - **Dark Mode** – Checkbox; angehakt schaltet die Oberfläche auf den dunklen
    Modus um, ohne Haken gilt der helle Modus.
  - **Sprache** – Radiobuttons für „Deutsch" und „Englisch"; die Auswahl wird
    in `settings.json` gespeichert und beim nächsten Start wiederhergestellt. Die Einstellung bleibt über
    Neustarts erhalten – sie wird in der gemeinsamen Einstellungsdatei
    `~/.config/axis_kamera_discovery/settings.json` (bzw. `$XDG_CONFIG_HOME`) abgelegt,
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
./Axis_Kamera_Discovery-x86_64.AppImage cli --help
./Axis_Kamera_Discovery-x86_64.AppImage --show          # Flag genügt -> CLI

# Direkt aus dem Quellcode:
python3 axis_kamera_discovery_cli.py --help
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
python3 axis_kamera_discovery_cli.py --show

# 15 Sekunden suchen und als CSV exportieren
python3 axis_kamera_discovery_cli.py -t 15 -o kameras.csv

# Als Texttabelle exportieren (Format per Flag erzwungen)
python3 axis_kamera_discovery_cli.py -o kameras.txt -f txt

# Alle 30 Sekunden suchen und Ergebnis anzeigen
python3 axis_kamera_discovery_cli.py --watch 30 --show

# Gefundene Kameras im Browser öffnen
python3 axis_kamera_discovery_cli.py --open

# Über das AppImage
./Axis_Kamera_Discovery-x86_64.AppImage cli -t 20 -o kameras.csv
```

### Kamera-Konfiguration (Unterbefehle)

Dieselben Aktionen wie im GUI-Dialog „Kamera Einstellungen" stehen als
Unterbefehle bereit. Jeder nimmt **eine oder mehrere Ziel-IPs** und gemeinsame
Verbindungsoptionen: `-u/--user` (Standard `root`), `-p/--password` (ohne Angabe
wird interaktiv gefragt), `--scheme {auto,https,http}`, `--port`, `--conn-timeout`.

| Unterbefehl | Zweck | Wichtige Optionen |
|---|---|---|
| `set-ip` | feste IP setzen | `--new-ip` (Pflicht), `--mask`, `--gateway` |
| `set-dhcp` | auf DHCP umstellen | – |
| `user-add` | Benutzer anlegen | `--name`, `--new-password`, `--role`, `--factory` |
| `user-passwd` | Benutzer-Passwort ändern | `--name`, `--new-password` |
| `user-import` | Benutzer aus Textdatei anlegen | `--file` (Name,Passwort[,Rolle]), `--factory` |
| `onvif-add` | ONVIF-Benutzer anlegen | `--name`, `--new-password`, `--level` |
| `onvif-passwd` | ONVIF-Passwort ändern | `--name`, `--new-password`, `--level` |
| `onvif-import` | ONVIF-Benutzer aus Textdatei anlegen | `--file` (Name,Passwort[,Stufe]) |
| `firmware` | Firmware aufspielen | `--file` (.bin), `--factory-default` |
| `config` | ADM-Konfiguration anwenden | `--file` (.cfg), `--no-profiles` |
| `config-export` | Konfiguration auslesen & als ADM-`.cfg` speichern | `--output`/`-o` (.cfg, Pflicht), `--grep` (Namens-Regex), `--no-profiles`, `--no-vmd4` |

```bash
# IP zweier Kameras (Passwort wird abgefragt)
python3 axis_kamera_discovery_cli.py set-ip 192.168.0.90 --new-ip 192.168.0.50 --gateway 192.168.0.1

# Erstbenutzer auf werksneuer Kamera (ohne Anmeldung / Standard-Zugangsdaten)
python3 axis_kamera_discovery_cli.py user-add 192.168.0.90 --name root --new-password 'Geheim123' --factory

# Mehrere Benutzer aus einer Textdatei anlegen (Name,Passwort[,Rolle] je Zeile)
python3 axis_kamera_discovery_cli.py user-import 192.168.0.50 192.168.0.51 --file benutzer.txt -p pw
# ONVIF-Benutzer als Stapel (Name,Passwort[,Stufe])
python3 axis_kamera_discovery_cli.py onvif-import 192.168.0.50 --file onvif.txt -p pw

# Firmware auf mehrere Kameras gleichen Modells
./Axis_Kamera_Discovery-x86_64.AppImage cli firmware 192.168.0.50 192.168.0.51 --file fw.bin -u root -p pw

# ADM-Konfiguration anwenden (inkl. Stream-Profile)
./Axis_Kamera_Discovery-x86_64.AppImage cli config 192.168.0.50 --file Konfig.cfg -p pw

# Konfiguration einer Kamera auslesen und als .cfg speichern
./Axis_Kamera_Discovery-x86_64.AppImage cli config-export 192.168.0.50 -o Konfig.cfg -p pw
# nur Netzwerk-Parameter exportieren (Namens-Regex), ohne Stream-Profile
./Axis_Kamera_Discovery-x86_64.AppImage cli config-export 192.168.0.50 -o Net.cfg -p pw --grep '^Network\.' --no-profiles
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
├── axis_kamera_discovery_cli.py        # Discovery-Kernlogik + CLI
├── axis_kamera_discovery_gui.py        # Tkinter-GUI (nutzt die Kernlogik)
├── bump_version.py              # Versionsverwaltung (JJ.MM.TT + bN)
├── build_appimage.sh            # Build (Tcl/Tk 9 + Python 3.13 aus Quellcode)
├── appimage/Axis_Kamera_Discovery/
│   └── Axis_Kamera_Discovery.png        # Icon für das AppImage
├── THIRD_PARTY_LICENSES.md      # Lizenzen der gebündelten Komponenten
├── LICENSE                      # GPL-3.0 Lizenztext
└── README.md
```

> Hinweis: `.tk9build/`, `*.AppImage` und `__pycache__/` sind per `.gitignore`
> vom Repository ausgeschlossen. Der Build erzeugt `AppRun` und den
> `.desktop`-Eintrag selbst.

---

## Changelog

| Version | Änderungen |
|---|---|
| 26.07.11 | Konfiguration: **Bewegungserkennung (VMD4)** wird beim Auslesen mit exportiert und beim Anwenden mit übernommen (eigene VMD4-Steuer-API, GUI-Schalter + CLI `--no-vmd4`); schreibgeschützte `Properties.*`-Parameter werden beim Anwenden übersprungen (neuere Firmware wies sonst den gesamten Batch ab) |
| 26.07.10 | Windows: Einstellungen (`settings.json`) werden portabel neben der EXE gespeichert statt in `%APPDATA%` |
| 26.06.29b1 | Stapel-Import: reguläre Benutzer und ONVIF-Benutzer aus einer Textdatei anlegen (GUI-Buttons + CLI `user-import`/`onvif-import`) |
| 26.06.29 | Konfiguration einer Kamera auslesen und als ADM-`.cfg` speichern – mit Parameter-Auswahl und Suche (GUI) bzw. CLI `config-export` |
| 26.06.28b9 | UI: Fensterbreite auf 1250x550 + leere Endlos-Spalte; Bug #11 (Kamera-Suche) behoben |
| 26.06.28b8 | Refactor: Sprachmenü mit Untermenü für Deutsch/Englisch; SESSION.md aktualisiert |
| 26.06.28b7 | Fix: Spracheinstellung wird nach Neustart beachtet (Einstellungen/Kamera Einstellungen-Buttons) |
| 26.06.28b5 | – |
| 26.06.28b4 | Sprachauswahl (Deutsch/Englisch) implementiert |
| 26.06.28b3 | Dokumentation aktualisiert |
| 26.06.28b2 | Export orientiert sich an eingeblendeten Spalten (nur GUI); Disclaimer-Hinweis in Toolbar |
| 26.06.28b1 | Disclaimer-Hinweis in Toolbar hinzugefügt |
| 26.06.28 | Fix: Einstellungen-Dropdown zeigt keine Artefakte mehr an (0,0) |
| 26.06.21b29 | Windows-.exe vorbereiten (PyInstaller) |

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
