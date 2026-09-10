#!/usr/bin/env python3
"""Grafische Oberflaeche fuer die Axis-Kamera-Suche.

Verwendet die Discovery-Logik aus axis_kamera_discovery_cli.py wieder und stellt
sie ueber eine Tkinter-Oberflaeche bereit. Die Suche laeuft in einem
Hintergrund-Thread, damit das Fenster waehrend der ~10 Sekunden nicht
einfriert.
"""

# Axis_Kamera_Discovery - findet Axis-Netzwerkkameras per Zeroconf/mDNS.
# Copyright (C) 2026 Mirik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import ipaddress
import json
import os
import platform
import queue
import re
import sys
import threading
import webbrowser
from importlib import metadata

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk

from axis_kamera_discovery_cli import (
    AxisDiscovery,
    export_results,
    get_first_ip,
    FIELD_NAMES,
    __version__,
)
import axis_kamera_discovery_vapix as vapix

COLUMNS = FIELD_NAMES
# Treeview-Spalten inkl. leerer Endlos-Spalte für bessere Optik
TREE_COLUMNS = list(COLUMNS) + [""]

# Speicherort fuer benutzerdefinierte Einstellungen (z. B. Dark Mode).
# Windows: portabel neben der EXE (bzw. neben dem Skript im Quellbetrieb);
#          sonst XDG ($XDG_CONFIG_HOME) bzw. ~/.config
if os.name == "nt":
    # Als PyInstaller-EXE zeigt sys.executable auf die .exe -> Konfig daneben
    # ablegen (portabler Betrieb). Im Quellbetrieb neben das Skript.
    if getattr(sys, "frozen", False):
        CONFIG_DIR = os.path.dirname(os.path.abspath(sys.executable))
    else:
        CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    CONFIG_DIR = os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
        "axis_kamera_discovery",
    )
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")

# Standardwerte aller persistenten Einstellungen. Die settings.json ist ein
# einfaches JSON-Objekt {schluessel: wert}. Eine neue Einstellung wird allein
# durch einen Eintrag hier verfuegbar: sie wird automatisch mit Default geladen,
# ueber get_setting/set_setting gelesen/geschrieben und in der Datei gespeichert.
# Beim Laden bleiben auch unbekannte (z. B. von einer neueren Version geschriebene)
# Schluessel erhalten, sodass die Datei vorwaerts-/rueckwaertskompatibel bleibt.
DEFAULT_SETTINGS = {
    "dark_mode": False,
    "search_duration": 10,   # "Dauer (s)"
    "autorefresh": False,    # Auto-Refresh aktiv
    "refresh_interval": 30,  # "alle (s)"
    "hidden_columns": [],    # ausgeblendete Tabellenspalten
    "language": "de",         # Sprache: "de" oder "en"
    "update_check": True,     # beim Start auf neue GitHub-Version pruefen
}

# GitHub-Projekt: Quelle fuer die Update-Pruefung und "Projektseite" im Info-Dialog.
GITHUB_REPO_SLUG = "odomiel/Axis_Kamera_Discovery"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO_SLUG}/releases"
_GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}/releases?per_page=10"
_VERSION_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})(?:b(\d+))?$")

def _parse_version(v):
    """'26.09.10b4' -> (26, 9, 10, 4). Ohne bN-Suffix -> b=0 (erstes Release des
    Tages, also aelter als b1). Nicht parsbar -> None."""
    m = _VERSION_RE.match((v or "").strip().lstrip("v"))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)) if m.group(4) else 0)


def _verified_ssl_context():
    """SSL-Kontext MIT Zertifikatspruefung fuer die GitHub-Abfrage. Der im AppImage
    gebuendelte OpenSSL bringt oft kein CA-Bundle mit (Kamera-Verbindungen laufen
    bewusst unverifiziert) -> bei Bedarf bekannte System-/Bundle-Pfade nachladen."""
    import ssl
    ctx = ssl.create_default_context()
    try:
        has_ca = ctx.cert_store_stats().get("x509", 0) > 0
    except Exception:
        has_ca = False
    if not has_ca:
        for path in (os.path.join(sys.prefix, "ssl", "cert.pem"),   # AppImage-Bundle
                     "/etc/ssl/certs/ca-certificates.crt",          # Debian/Ubuntu
                     "/etc/pki/tls/certs/ca-bundle.crt",            # Fedora/RHEL
                     "/etc/ssl/cert.pem"):                          # Alpine/BSD/macOS
            try:
                ctx.load_verify_locations(path)
                break
            except (OSError, ssl.SSLError):
                continue
    return ctx

# ===================================================================
# Uebersetzungen / Internationalisierung (i18n)
# ===================================================================
# Dictionary-basiertes Uebersetzungssystem. _() gibt den Text in der aktuellen
# Sprache zurueck (Default: Deutsch).
#
#Usage: _("text_key") oder self._("text_key") in Methoden

TRANSLATIONS = {
    "de": {
        # GUI-Titel und Fenster
        "window_title": "Axis Kamera Discovery",
        
        # Toolbar
        "btn_search": "Suchen",
        "menu_add_manual": "Kamera manuell hinzufügen…",
        "manual_add_title": "Kamera manuell hinzufügen",
        "manual_add_hint": "Fügt eine Kamera über ihre IP-Adresse hinzu, die die "
            "Suche nicht gefunden hat (z. B. in einem anderen Subnetz). Der Eintrag "
            "bleibt auch nach einer erneuten Suche erhalten.",
        "manual_add_name": "Name:",
        "manual_add_ip": "IP-Adresse:",
        "manual_add_port": "Port:",
        "manual_add_hostname": "Hostname:",
        "manual_add_add": "Hinzufügen",
        "manual_add_cancel": "Abbrechen",
        "manual_add_ip_required": "Bitte eine IP-Adresse eingeben.",
        "manual_add_ip_invalid": "„{ip}“ ist keine gültige IP-Adresse.",
        "manual_add_duplicate": "Eine Kamera mit der IP-Adresse {ip} ist bereits in der Liste.",
        "manual_add_default_name": "(manuell hinzugefügt)",
        "label_duration": "Dauer (s):",
        "label_every": "alle (s):",
        "btn_autorefresh": "Auto-Refresh",
        "btn_export": "Exportieren...",
        "btn_camera_settings": "Kamera Einstellungen",
        "btn_settings": "Einstellungen",
        
        # Einstellungen-Menü
        "menu_dark_mode": "Dark Mode",
        "menu_update_check": "Beim Start auf Updates pruefen",
        "menu_check_updates": "Nach Updates suchen",
        "menu_columns": "Spalten...",
        "menu_language": "Sprache",
        "menu_language_de": "Deutsch",
        "menu_language_en": "Englisch",
        "menu_info": "Info",
        "menu_help": "Hilfe",
        "menu_licenses": "Lizenzen",
        "update_title": "Update-Pruefung",
        "update_available": "Eine neue Version ist verfuegbar:\n\n"
            "    Aktuell:  {current}\n    Neu:      {new}\n\n"
            "Moechten Sie die Downloadseite auf GitHub oeffnen?",
        "update_none": "Sie verwenden bereits die neueste Version ({current}).",
        "update_error": "Die Update-Pruefung ist fehlgeschlagen:\n{error}",
        
        # Disclaimer
        "disclaimer": "Nutzung des Programms auf eigene Gefahr",
        
        # Spalten-Dialog
        "columns_dialog_title": "Spalten",
        "columns_dialog_label": "Sichtbare Spalten:",
        "btn_close": "Schliessen",
        
        # Info-Dialog
        "info_title": "Info",
        "info_body": "Axis_Kamera_Discovery\nVersion {version}\n\n"
        "Findet Axis-Kameras im lokalen Netzwerk per Zeroconf/mDNS.\n\n"
        "Projektseite: https://github.com/odomiel/Axis_Kamera_Discovery\n\n"
        "Komponenten:\n{components}\n\n"
        "Lizenz: GPL-3.0-or-later\n"
        "Copyright (C) 2026 Mirik\n"
        "Co-Autor: Claude Opus 4.8 (Anthropic) - KI-gestuetzte Entwicklung",
        "cs_select_first_title": "Kamera Einstellungen",
        "cs_select_first": "Bitte zuerst eine oder mehrere Kameras in der Liste auswaehlen.",

        # Hilfe-Dialog
        "help_title": "Hilfe - README",

        # Lizenzen-Dialog
        "licenses_title": "Lizenzen",
        "file_not_found": "{filename} wurde nicht gefunden.",
        
        # Kamera Einstellungen Dialog
        "camera_settings_title": "Kamera Einstellungen",
        "camera_settings_cameras_selected": "{count} Kamera(s) ausgewaehlt",
        "camera_settings_credentials": "Zugangsdaten",
        "camera_settings_user": "Benutzer:",
        "camera_settings_password": "Passwort:",
        "camera_settings_connection": "Verbindung:",
        "camera_settings_port": "Port (optional):",
        "camera_settings_timeout": "Timeout (s):",
        "camera_settings_test_connection": "Verbindung testen",
        "camera_settings_ip_tab": "IP-Adresse",
        "camera_settings_ipv6_tab": "IPv6-Adresse",
        "camera_settings_users_tab": "Benutzer",
        "camera_settings_onvif_tab": "ONVIF-Benutzer",
        "camera_settings_firmware_tab": "Firmware",
        "camera_settings_config_tab": "Konfiguration",
        "cs_apply": "Anwenden",
        "cs_close": "Schliessen",
        "cs_result": "Ergebnis:",
        # IP-Reiter
        "cs_ip_dhcp": "Auf DHCP umstellen",
        "cs_ip_range": "Feste IP ab Start-IP fortlaufend",
        "cs_ip_each": "Pro Kamera einzeln",
        "cs_subnet": "Subnetzmaske:",
        "cs_gateway_opt": "Gateway (optional):",
        "cs_start_ip": "Start-IP:",
        "cs_range_hint": "(wird fortlaufend an die Kameras in Listenreihenfolge vergeben)",
        # IPv6-Reiter
        "cs_ipv6_auto": "Automatisch (Router Advertisement / SLAAC)",
        "cs_ipv6_manual": "Feste IPv6-Adresse",
        "cs_ipv6_off": "IPv6 deaktivieren",
        "cs_ipv6_addr_label": "IPv6-Adresse (mit Praefix, z. B. 2001:db8::10/64):",
        "cs_ipv6_read_btn": "Aktuelle IPv6-Konfiguration auslesen",
        "cs_ipv6_help": "Stellt die IPv6-Einstellungen der markierten Kamera(s) ueber "
        "param.cgi (Network.IPv6) ein. 'Automatisch' uebernimmt per SLAAC/Router-"
        "Advertisement vergebene Adressen; 'Feste IPv6-Adresse' setzt eine "
        "manuelle Adresse inkl. Praefixlaenge. Die aktuell vergebenen Adressen "
        "lassen sich zuvor auslesen (rein lesend).",
        # Zeitzone-Reiter (Time API)
        "camera_settings_timezone_tab": "Zeitzone",
        "cs_tz_label": "Zeitzone (IANA, z. B. Europe/Berlin):",
        "cs_tz_load_btn": "Von erster Kamera laden",
        "cs_tz_help": "Setzt die Zeitzone der markierten Kamera(s) ueber die Time API "
        "(POST time.cgi, setTimeZone; ab AXIS OS 9.30). Ersetzt den in AXIS OS 13 "
        "entfernten Parameter Time.POSIXTimeZone; die Sommerzeit wird anhand des "
        "IANA-Namens automatisch angewandt. 'Von erster Kamera laden' holt die "
        "aktuelle Zone und die vom Geraet unterstuetzten Zonen (rein lesend).",
        "cs_tz_need": "Bitte eine Zeitzone waehlen oder eingeben.",
        "cs_tz_applying": "Setze Zeitzone {tz} auf {count} Kamera(s) ...",
        "cs_tz_reading": "Lese Zeitzone von {name} ({ip}) ...",
        "cs_tz_current": "Aktuelle Zeitzone von {name}: {tz}",
        "cs_tz_unknown": "(unbekannt)",
        # Benutzer-Reiter
        "cs_user_add": "Benutzer anlegen",
        "cs_user_setpw": "Passwort aendern",
        "cs_username": "Benutzername:",
        "cs_role": "Rolle:",
        "cs_user_root_hint": "Hinweis: 'root' ist der uebliche Erstbenutzer (Administrator).",
        "cs_factory_cb": "Auslieferungszustand (Standard-Zugangsdaten/ohne Anmeldung probieren; Anlegen als Administrator)",
        "cs_factory_help": "Ersteinstellung: \"Auslieferungszustand\" anhaken und \"Benutzer "
        "anlegen\" mit Benutzer 'root' + Passwort. Funktioniert fuer moderne "
        "Kameras (legt den Erstadmin an) wie aeltere (z. B. M7001: setzt das "
        "Passwort des vorhandenen 'root').",
        "cs_import_users_title": "Stapel-Import aus Textdatei (mehrere Benutzer anlegen):",
        "cs_import_btn": "Benutzerliste waehlen und anlegen...",
        "cs_import_users_help": "Eine Zeile je Benutzer: Name,Passwort,Rolle - Rolle optional "
        "(Standard: viewer), gueltig: administrator/operator/viewer. Passwoerter "
        "mit Komma in \"...\" setzen; Zeilen mit '#' sind Kommentare. Der oben "
        "gewaehlte 'Auslieferungszustand' gilt auch fuer den Import (legt als "
        "Administrator an).",
        # ONVIF-Reiter
        "cs_onvif_add": "ONVIF-Benutzer anlegen",
        "cs_onvif_setpw": "Passwort aendern",
        "cs_level": "Stufe:",
        "cs_import_onvif_title": "Stapel-Import aus Textdatei (mehrere ONVIF-Benutzer anlegen):",
        "cs_import_onvif_help": "Eine Zeile je Benutzer: Name,Passwort,Stufe - Stufe optional "
        "(Standard: User), gueltig: Administrator/Operator/User. Passwoerter "
        "mit Komma in \"...\" setzen; Zeilen mit '#' sind Kommentare.",
        # Firmware-Reiter
        "cs_fw_file": "Firmware-Datei:",
        "cs_browse": "Durchsuchen...",
        "cs_fw_factory": "Werkseinstellungen beim Update (factory default)",
        "cs_fw_help": "Achtung: Die Firmware muss zum Kameramodell passen. Sie wird auf "
        "ALLE markierten Kameras gespielt - nur Kameras gleichen Modells "
        "auswaehlen. Der Vorgang dauert einige Minuten; die Kamera startet "
        "danach neu.",
        # Konfigurations-Reiter
        "cs_cfg_file": "ADM-Konfig (.cfg):",
        "cs_cfg_none": "Keine Datei gewaehlt.",
        "cs_cfg_profiles": "Stream-Profile mit uebernehmen",
        "cs_cfg_vmd4": "Bewegungserkennung (VMD4) mit uebernehmen",
        "cs_cfg_help": "Wendet die Parameter aus der Axis-Device-Manager-Konfiguration "
        "(param.cgi) auf die markierten Kameras an; optional auch die "
        "Stream-Profile (gleichnamige vorhandene Profile werden ueberschrieben, "
        "neue angelegt). Enthaelt die Datei eine Bewegungserkennung (VMD4), "
        "wird diese automatisch mit angewendet (die VMD-Anwendung wird bei "
        "Bedarf gestartet). Die Konfiguration sollte zum Modell passen. "
        "Vom Geraet abgelehnte Einzelparameter (z. B. in neuerer Firmware wie "
        "AXIS OS 13 entfernte Parameter) werden uebersprungen und im Ergebnis "
        "genannt, statt den ganzen Import abzubrechen.",
        "cs_cfg_export_title": "Konfiguration aus Kamera auslesen:",
        "cs_cfg_export_btn": "Aus Kamera auslesen und speichern...",
        "cs_cfg_export_help": "Liest die komplette Parameterliste der ERSTEN markierten Kamera. "
        "Anschliessend laesst sich auswaehlen und durchsuchen, welche Parameter "
        "in die ADM-.cfg geschrieben werden. Tipp: ein vollstaendiger Export "
        "enthaelt auch geraetespezifische/nur-lesbare Werte (z.B. Seriennummer) "
        "- fuer die Uebertragung auf andere Kameras nur passende Parameter waehlen.",
        # Kamera-Einstellungen: Geraete-Sicherung (Device Configuration API)
        "camera_settings_backup_tab": "Geraete-Sicherung",
        "cs_bk_restore_title": "Sicherung einspielen:",
        "cs_bk_file": "Sicherungsdatei:",
        "cs_bk_none": "Keine Sicherungsdatei gewaehlt.",
        "cs_bk_info": "{n} Ressourcen in der Sicherung: {keys}",
        "cs_bk_parse_error": "Sicherung nicht lesbar: {exc}",
        "cs_bk_importtype": "Modus beim Einspielen:",
        "cs_bk_merge": "Zusammenfuehren - nur gesicherte Werte ueberschreiben, Rest behalten",
        "cs_bk_default": "Zuruecksetzen - betroffene Bereiche auf Standard, dann Sicherung",
        "cs_bk_help": "Spielt eine komplette Geraete-Sicherung (JSON aus AXIS OS "
        "„System > Wartung“, ab AXIS OS 11.8) auf die markierten Kameras ein. "
        "Passwoerter sind in einer Sicherung NICHT enthalten und werden nicht "
        "wiederhergestellt. Die Sicherung ist geraetespezifisch (u.a. IP, Hostname) - "
        "auf mehrere Kameras angewandt entstehen Adress-/Namenskonflikte. Das Geraet "
        "kann sich nach dem Einspielen selbst neu starten.",
        "cs_bk_need_file": "Bitte zuerst eine Sicherungsdatei waehlen.",
        "cs_bk_restore_confirm_title": "Sicherung einspielen?",
        "cs_bk_restore_confirm": "Sicherung auf {count} Kamera(s) einspielen? "
        "Die Geraete koennen dabei neu starten. Bei mehreren Kameras drohen "
        "IP-/Namenskonflikte (die Sicherung ist geraetespezifisch).",
        "cs_bk_restoring": "Spiele Sicherung auf {count} Kamera(s) ein ...",
        "cs_bk_restore_ok": "Sicherung eingespielt ({n} Ressourcen) - Geraet startet ggf. neu",
        "cs_bk_choose": "Sicherungsdatei waehlen",
        "cs_bk_download_title": "Sicherung herunterladen:",
        "cs_bk_download_btn": "Sicherung der ERSTEN Kamera speichern...",
        "cs_bk_download_help": "Liest die komplette Konfiguration der ERSTEN markierten "
        "Kamera und speichert sie als JSON-Sicherung (gleiches Format wie AXIS OS "
        "„System > Wartung“). Passwoerter sind aus Sicherheitsgruenden nicht enthalten.",
        "cs_bk_save_as": "Sicherung speichern unter",
        "cs_bk_saving": "Lese Sicherung von {name} ({ip}) ...",
        "cs_bk_save_ok": "Sicherung gespeichert: {path} ({n} Ressourcen)",
        "cs_ft_json": "Geraete-Sicherung",
        # Kamera-Einstellungen: Meldungen und Status
        "cs_input_error": "Eingabefehler",
        "cs_confirm_change": "Aenderung bestaetigen",
        "cs_no_ip_known": "keine IP-Adresse bekannt",
        "cs_test_conn_log": "Teste Verbindung (lesend, ohne Aenderung)...",
        "cs_applying": "Wende Aenderung an ({count} Kamera(s))...",
        "cs_done": "Fertig.",
        "cs_confirm_dhcp": "Auf DHCP umstellen?",
        "cs_confirm_set_ips": "Folgende IP-Adressen setzen?\n\n{ips}",
        "cs_dhcp_ok": "auf DHCP umgestellt",
        "cs_ip_set_ok": "IP gesetzt auf {ip}",
        "cs_need_subnet": "Bitte eine Subnetzmaske angeben.",
        "cs_need_start_ip": "Bitte eine Start-IP angeben.",
        "cs_invalid_start_ip": "Ungueltige Start-IP: {start}",
        "cs_need_ip_for": "Bitte fuer '{name}' eine IP angeben.",
        "cs_need_ipv6": "Bitte eine IPv6-Adresse mit Praefix angeben (z. B. 2001:db8::10/64).",
        "cs_ipv6_sum_off": "IPv6 deaktivieren",
        "cs_ipv6_sum_auto": "IPv6 auf automatisch (SLAAC / Router Advertisement) stellen",
        "cs_ipv6_sum_manual": "feste IPv6-Adresse {address} setzen",
        "cs_ipv6_confirm": "{summary}\nauf {count} Kamera(s)?",
        "cs_ipv6_applying": "Wende IPv6-Aenderung an ({count} Kamera(s))...",
        "cs_ipv6_done_off": "IPv6 deaktiviert",
        "cs_ipv6_done_auto": "IPv6 auf automatisch gesetzt",
        "cs_ipv6_done_manual": "feste IPv6-Adresse {address} gesetzt",
        "cs_ipv6_reading": "Lese aktuelle IPv6-Konfiguration (rein lesend)...",
        "cs_ipv6_state_on": "aktiv",
        "cs_ipv6_state_off": "deaktiviert",
        "cs_ipv6_none": "(keine)",
        "cs_ipv6_read_result": "IPv6 {state}; Adressen: {addrs}",
        "cs_need_username": "Bitte einen Benutzernamen angeben.",
        "cs_need_password": "Bitte ein Passwort angeben.",
        "cs_kind_onvif": "ONVIF-Benutzer",
        "cs_kind_user": "Benutzer",
        "cs_verb_add": "anlegen",
        "cs_verb_setpw": "Passwort aendern fuer",
        "cs_user_confirm": "{kind} '{name}' {verb} auf {count} Kamera(s)?",
        "cs_factory_no_auth": "ohne Anmeldung",
        "cs_factory_empty": "leer",
        "cs_factory_suffix": " [Auslieferungszustand: {label}]",
        "cs_no_access": "kein Zugang moeglich",
        "cs_existing_user_pw": " (vorhandener Benutzer, Passwort gesetzt)",
        "cs_choose_user_list": "Benutzerliste waehlen",
        "cs_ft_txt": "Textdatei",
        "cs_ft_csv": "CSV-Datei",
        "cs_ft_all": "Alle Dateien",
        "cs_file_error": "Datei-Fehler",
        "cs_more_users": "\n  ... ({count} weitere)",
        "cs_import_confirm": "{count} {kind} aus der Datei auf {cams} Kamera(s) anlegen?\n\n{preview}",
        "cs_import_confirm_title": "Stapel-Import bestaetigen",
        "cs_importing": "Importiere {count} {kind} auf {cams} Kamera(s)...",
        "cs_choose_fw": "Firmware-Datei waehlen",
        "cs_ft_fw": "Firmware",
        "cs_need_fw": "Bitte eine gueltige Firmware-Datei waehlen.",
        "cs_fw_confirm": "Firmware\n  {name}\nauf {count} Kamera(s) aufspielen?\n\n"
        "Die Firmware MUSS zum Modell passen. Der Vorgang dauert einige "
        "Minuten, danach startet die Kamera neu.",
        "cs_fw_confirm_title": "Firmware-Update bestaetigen",
        "cs_fw_applying": "Spiele Firmware auf ({count} Kamera(s)) - bitte warten...",
        "cs_choose_cfg": "ADM-Konfigurationsdatei waehlen",
        "cs_ft_cfg": "ADM-Konfiguration",
        "cs_cfg_vmd4_note": " | Bewegungserkennung (VMD4)",
        "cs_cfg_info": "Modell: {model} | Firmware: {fw} | {params} Parameter, {profiles} Stream-Profil(e){vmd}",
        "cs_cfg_parse_error": "Fehler: {exc}",
        "cs_need_cfg": "Bitte eine gueltige ADM-Konfigurationsdatei waehlen.",
        "cs_cfg_confirm": "Konfiguration fuer Modell '{model}'\n({params} Parameter) auf "
        "{count} Kamera(s) anwenden?\n\nDie Konfiguration sollte zum Kameramodell passen.",
        "cs_cfg_confirm_title": "Konfiguration anwenden",
        "cs_cfg_applying": "Wende Konfiguration an ({count} Kamera(s))...",
        "cs_no_camera_title": "Keine Kamera",
        "cs_no_camera": "Keine Kamera ausgewaehlt.",
        "cs_no_ip_title": "Keine IP",
        "cs_no_ip_for": "Fuer '{name}' ist keine IP-Adresse bekannt.",
        "cs_read_only_first": "Hinweis: Es wird nur die erste markierte Kamera ausgelesen ({name}).",
        "cs_reading_cfg": "Lese Konfiguration von {name} ({ip}) - bitte warten...",
        "cs_cfg_vmd4_note2": ", Bewegungserkennung (VMD4)",
        "cs_log_error": "  [FEHLER] {name}: {msg}",
        "cs_read_ok": "  [OK] {name}: {params} Parameter, {profiles} Stream-Profil(e){vmd} gelesen",
        "cs_log_ok": "OK",
        "cs_log_fail": "FEHLER",
        "cs_log_line": "  [{status}] {name}: {msg}",
        # Parameter-Auswahl-Dialog (Export)
        "ps_title": "Parameter auswaehlen und speichern",
        "ps_header": "{cam} - Modell {model}, FW {fw}",
        "ps_count_read": "{count} Parameter gelesen. Haken anklicken = in die .cfg uebernehmen.",
        "ps_search": "Suche:",
        "ps_col_param": "Parameter",
        "ps_col_value": "Wert",
        "ps_all_filtered": "Alle (gefiltert)",
        "ps_none_filtered": "Keine (gefiltert)",
        "ps_incl_profiles": "Stream-Profile einschliessen ({count})",
        "ps_incl_vmd4": "Bewegungserkennung (VMD4) einschliessen",
        "ps_not_available": " (nicht vorhanden)",
        "ps_save": "Speichern...",
        "ps_cancel": "Abbrechen",
        "ps_selected_count": "{sel} von {total} ausgewaehlt",
        "ps_nothing_title": "Nichts ausgewaehlt",
        "ps_nothing": "Bitte mindestens einen Parameter auswaehlen.",
        "ps_save_title": "ADM-Konfiguration speichern",
        "ps_save_error": "Fehler beim Speichern",
        "ps_extra_profiles": " + {count} Stream-Profil(e)",
        "ps_extra_vmd4": " + Bewegungserkennung (VMD4)",
        "ps_saved_title": "Gespeichert",
        "ps_saved": "{count} Parameter{extra} gespeichert:\n{path}",

        # Status
        "status_searching": "Suche laeuft...",
        "status_searching_with_timeout": "Suche laeuft ({timeout} s)...",
        "status_found": "{count} Kamera(s) gefunden",
        "status_exported": "Exportiert nach {path}",
        "status_no_cameras": "Keine Kameras gefunden",
        "status_error": "Fehler bei der Suche.",
        "status_no_axis_cameras": "Keine Axis-Kameras gefunden.",
        "msg_error": "Fehler",
        "msg_search_error": "Fehler bei der Suche",
        
        # Export-Dialog
        "export_dialog_title": "Ergebnisse speichern",
        "filetype_csv": "CSV-Datei",
        "filetype_txt": "Textdatei",
        "filetype_all": "Alle Dateien",
        
        # Spaltenüberschriften (aus FIELD_NAMES)
        "col_Name": "Name",
        "col_IP Adresse: Zeroconfig": "IP Adresse: Zeroconfig",
        "col_IP Adresse: Konfiguriert": "IP Adresse: Konfiguriert",
        "col_IPv6 Adresse": "IPv6 Adresse",
        "col_Port": "Port",
        "col_Hostname": "Hostname",
        "col_MAC-Adresse/Seriennummer": "MAC-Adresse/Seriennummer",
    },
    "en": {
        # GUI-Titel und Fenster
        "window_title": "Axis Camera Discovery",
        
        # Toolbar
        "btn_search": "Search",
        "menu_add_manual": "Add camera manually…",
        "manual_add_title": "Add camera manually",
        "manual_add_hint": "Adds a camera by its IP address that the search did not "
            "find (e.g. on a different subnet). The entry is kept after a new search.",
        "manual_add_name": "Name:",
        "manual_add_ip": "IP address:",
        "manual_add_port": "Port:",
        "manual_add_hostname": "Hostname:",
        "manual_add_add": "Add",
        "manual_add_cancel": "Cancel",
        "manual_add_ip_required": "Please enter an IP address.",
        "manual_add_ip_invalid": "“{ip}” is not a valid IP address.",
        "manual_add_duplicate": "A camera with IP address {ip} is already in the list.",
        "manual_add_default_name": "(added manually)",
        "label_duration": "Duration (s):",
        "label_every": "every (s):",
        "btn_autorefresh": "Auto-Refresh",
        "btn_export": "Export...",
        "btn_camera_settings": "Camera Settings",
        "btn_settings": "Settings",
        
        # Einstellungen-Menü
        "menu_dark_mode": "Dark Mode",
        "menu_update_check": "Check for updates on start",
        "menu_check_updates": "Check for updates",
        "menu_columns": "Columns...",
        "menu_language": "Language",
        "menu_language_de": "German",
        "menu_language_en": "English",
        "menu_info": "Info",
        "menu_help": "Help",
        "menu_licenses": "Licenses",
        "update_title": "Update check",
        "update_available": "A new version is available:\n\n"
            "    Current:  {current}\n    New:      {new}\n\n"
            "Open the download page on GitHub?",
        "update_none": "You are already on the latest version ({current}).",
        "update_error": "The update check failed:\n{error}",
        
        # Disclaimer
        "disclaimer": "Use at your own risk",
        
        # Spalten-Dialog
        "columns_dialog_title": "Columns",
        "columns_dialog_label": "Visible columns:",
        "btn_close": "Close",
        
        # Info-Dialog
        "info_title": "Info",
        "info_body": "Axis_Kamera_Discovery\nVersion {version}\n\n"
        "Finds Axis cameras on the local network via Zeroconf/mDNS.\n\n"
        "Project page: https://github.com/odomiel/Axis_Kamera_Discovery\n\n"
        "Components:\n{components}\n\n"
        "License: GPL-3.0-or-later\n"
        "Copyright (C) 2026 Mirik\n"
        "Co-author: Claude Opus 4.8 (Anthropic) - AI-assisted development",
        "cs_select_first_title": "Camera Settings",
        "cs_select_first": "Please select one or more cameras in the list first.",

        # Hilfe-Dialog
        "help_title": "Help - README",

        # Lizenzen-Dialog
        "licenses_title": "Licenses",
        "file_not_found": "{filename} was not found.",
        
        # Kamera Einstellungen Dialog
        "camera_settings_title": "Camera Settings",
        "camera_settings_cameras_selected": "{count} camera(s) selected",
        "camera_settings_credentials": "Credentials",
        "camera_settings_user": "User:",
        "camera_settings_password": "Password:",
        "camera_settings_connection": "Connection:",
        "camera_settings_port": "Port (optional):",
        "camera_settings_timeout": "Timeout (s):",
        "camera_settings_test_connection": "Test Connection",
        "camera_settings_ip_tab": "IP Address",
        "camera_settings_ipv6_tab": "IPv6 Address",
        "camera_settings_users_tab": "Users",
        "camera_settings_onvif_tab": "ONVIF Users",
        "camera_settings_firmware_tab": "Firmware",
        "camera_settings_config_tab": "Configuration",
        "cs_apply": "Apply",
        "cs_close": "Close",
        "cs_result": "Result:",
        # IP tab
        "cs_ip_dhcp": "Switch to DHCP",
        "cs_ip_range": "Static IP, consecutive from start IP",
        "cs_ip_each": "Per camera individually",
        "cs_subnet": "Subnet mask:",
        "cs_gateway_opt": "Gateway (optional):",
        "cs_start_ip": "Start IP:",
        "cs_range_hint": "(assigned consecutively to the cameras in list order)",
        # IPv6 tab
        "cs_ipv6_auto": "Automatic (Router Advertisement / SLAAC)",
        "cs_ipv6_manual": "Static IPv6 address",
        "cs_ipv6_off": "Disable IPv6",
        "cs_ipv6_addr_label": "IPv6 address (with prefix, e.g. 2001:db8::10/64):",
        "cs_ipv6_read_btn": "Read current IPv6 configuration",
        "cs_ipv6_help": "Configures the IPv6 settings of the selected camera(s) via "
        "param.cgi (Network.IPv6). 'Automatic' adopts addresses assigned via "
        "SLAAC/Router Advertisement; 'Static IPv6 address' sets a manual address "
        "including prefix length. The currently assigned addresses can be read "
        "beforehand (read-only).",
        # Timezone tab (Time API)
        "camera_settings_timezone_tab": "Time zone",
        "cs_tz_label": "Time zone (IANA, e.g. Europe/Berlin):",
        "cs_tz_load_btn": "Load from first camera",
        "cs_tz_help": "Sets the time zone of the selected camera(s) via the Time API "
        "(POST time.cgi, setTimeZone; AXIS OS 9.30+). Replaces the Time.POSIXTimeZone "
        "parameter removed in AXIS OS 13; daylight saving time is applied automatically "
        "from the IANA name. 'Load from first camera' fetches the current zone and the "
        "zones the device supports (read-only).",
        "cs_tz_need": "Please select or enter a time zone.",
        "cs_tz_applying": "Setting time zone {tz} on {count} camera(s) ...",
        "cs_tz_reading": "Reading time zone from {name} ({ip}) ...",
        "cs_tz_current": "Current time zone of {name}: {tz}",
        "cs_tz_unknown": "(unknown)",
        # Users tab
        "cs_user_add": "Create user",
        "cs_user_setpw": "Change password",
        "cs_username": "Username:",
        "cs_role": "Role:",
        "cs_user_root_hint": "Note: 'root' is the usual initial user (administrator).",
        "cs_factory_cb": "Factory state (try default credentials/no login; create as administrator)",
        "cs_factory_help": "Initial setup: check \"Factory state\" and \"Create user\" "
        "with user 'root' + password. Works for modern cameras (creates the "
        "initial admin) and older ones (e.g. M7001: sets the password of the "
        "existing 'root').",
        "cs_import_users_title": "Batch import from text file (create multiple users):",
        "cs_import_btn": "Choose user list and create...",
        "cs_import_users_help": "One line per user: name,password,role - role optional "
        "(default: viewer), valid: administrator/operator/viewer. Enclose passwords "
        "containing a comma in \"...\"; lines starting with '#' are comments. The "
        "'Factory state' selected above also applies to the import (creates as "
        "administrator).",
        # ONVIF tab
        "cs_onvif_add": "Create ONVIF user",
        "cs_onvif_setpw": "Change password",
        "cs_level": "Level:",
        "cs_import_onvif_title": "Batch import from text file (create multiple ONVIF users):",
        "cs_import_onvif_help": "One line per user: name,password,level - level optional "
        "(default: User), valid: Administrator/Operator/User. Enclose passwords "
        "containing a comma in \"...\"; lines starting with '#' are comments.",
        # Firmware tab
        "cs_fw_file": "Firmware file:",
        "cs_browse": "Browse...",
        "cs_fw_factory": "Factory default on update",
        "cs_fw_help": "Caution: the firmware must match the camera model. It is flashed "
        "to ALL selected cameras - only select cameras of the same model. The "
        "process takes a few minutes; the camera reboots afterwards.",
        # Configuration tab
        "cs_cfg_file": "ADM config (.cfg):",
        "cs_cfg_none": "No file selected.",
        "cs_cfg_profiles": "Include stream profiles",
        "cs_cfg_vmd4": "Include motion detection (VMD4)",
        "cs_cfg_help": "Applies the parameters from the Axis Device Manager configuration "
        "(param.cgi) to the selected cameras; optionally the stream profiles too "
        "(existing profiles of the same name are overwritten, new ones added). If "
        "the file contains a motion detection (VMD4), it is applied automatically "
        "(the VMD app is started if needed). The configuration should match the model. "
        "Individual parameters the device rejects (e.g. parameters removed in newer "
        "firmware such as AXIS OS 13) are skipped and listed in the result instead of "
        "aborting the whole import.",
        "cs_cfg_export_title": "Read configuration from camera:",
        "cs_cfg_export_btn": "Read from camera and save...",
        "cs_cfg_export_help": "Reads the complete parameter list of the FIRST selected camera. "
        "Afterwards you can select and search which parameters are written to the "
        "ADM .cfg. Tip: a full export also contains device-specific/read-only values "
        "(e.g. serial number) - for transfer to other cameras, select only matching "
        "parameters.",
        # Camera settings: device backup (Device Configuration API)
        "camera_settings_backup_tab": "Device backup",
        "cs_bk_restore_title": "Restore backup:",
        "cs_bk_file": "Backup file:",
        "cs_bk_none": "No backup file selected.",
        "cs_bk_info": "{n} resources in backup: {keys}",
        "cs_bk_parse_error": "Backup not readable: {exc}",
        "cs_bk_importtype": "Restore mode:",
        "cs_bk_merge": "Merge - overwrite only saved values, keep the rest",
        "cs_bk_default": "Reset - affected areas to default, then apply backup",
        "cs_bk_help": "Restores a complete device backup (JSON from AXIS OS "
        "“System > Maintenance”, AXIS OS 11.8 or newer) to the selected cameras. "
        "Passwords are NOT contained in a backup and are not restored. A backup is "
        "device-specific (incl. IP, hostname) - applying it to several cameras causes "
        "address/name conflicts. The device may reboot itself after the restore.",
        "cs_bk_need_file": "Please select a backup file first.",
        "cs_bk_restore_confirm_title": "Restore backup?",
        "cs_bk_restore_confirm": "Restore the backup to {count} camera(s)? "
        "The devices may reboot. With several cameras there is a risk of IP/name "
        "conflicts (a backup is device-specific).",
        "cs_bk_restoring": "Restoring backup to {count} camera(s) ...",
        "cs_bk_restore_ok": "Backup restored ({n} resources) - device may reboot",
        "cs_bk_choose": "Select backup file",
        "cs_bk_download_title": "Download backup:",
        "cs_bk_download_btn": "Save backup of the FIRST camera...",
        "cs_bk_download_help": "Reads the complete configuration of the FIRST selected "
        "camera and saves it as a JSON backup (same format as AXIS OS "
        "“System > Maintenance”). Passwords are not included for security reasons.",
        "cs_bk_save_as": "Save backup as",
        "cs_bk_saving": "Reading backup from {name} ({ip}) ...",
        "cs_bk_save_ok": "Backup saved: {path} ({n} resources)",
        "cs_ft_json": "Device backup",
        # Camera settings: messages and status
        "cs_input_error": "Input error",
        "cs_confirm_change": "Confirm change",
        "cs_no_ip_known": "no IP address known",
        "cs_test_conn_log": "Testing connection (read-only, no change)...",
        "cs_applying": "Applying change ({count} camera(s))...",
        "cs_done": "Done.",
        "cs_confirm_dhcp": "Switch to DHCP?",
        "cs_confirm_set_ips": "Set the following IP addresses?\n\n{ips}",
        "cs_dhcp_ok": "switched to DHCP",
        "cs_ip_set_ok": "IP set to {ip}",
        "cs_need_subnet": "Please provide a subnet mask.",
        "cs_need_start_ip": "Please provide a start IP.",
        "cs_invalid_start_ip": "Invalid start IP: {start}",
        "cs_need_ip_for": "Please provide an IP for '{name}'.",
        "cs_need_ipv6": "Please provide an IPv6 address with prefix (e.g. 2001:db8::10/64).",
        "cs_ipv6_sum_off": "disable IPv6",
        "cs_ipv6_sum_auto": "set IPv6 to automatic (SLAAC / Router Advertisement)",
        "cs_ipv6_sum_manual": "set static IPv6 address {address}",
        "cs_ipv6_confirm": "{summary}\non {count} camera(s)?",
        "cs_ipv6_applying": "Applying IPv6 change ({count} camera(s))...",
        "cs_ipv6_done_off": "IPv6 disabled",
        "cs_ipv6_done_auto": "IPv6 set to automatic",
        "cs_ipv6_done_manual": "static IPv6 address {address} set",
        "cs_ipv6_reading": "Reading current IPv6 configuration (read-only)...",
        "cs_ipv6_state_on": "enabled",
        "cs_ipv6_state_off": "disabled",
        "cs_ipv6_none": "(none)",
        "cs_ipv6_read_result": "IPv6 {state}; addresses: {addrs}",
        "cs_need_username": "Please provide a username.",
        "cs_need_password": "Please provide a password.",
        "cs_kind_onvif": "ONVIF user",
        "cs_kind_user": "user",
        "cs_verb_add": "create",
        "cs_verb_setpw": "change password for",
        "cs_user_confirm": "{verb} {kind} '{name}' on {count} camera(s)?",
        "cs_factory_no_auth": "no login",
        "cs_factory_empty": "empty",
        "cs_factory_suffix": " [factory state: {label}]",
        "cs_no_access": "no access possible",
        "cs_existing_user_pw": " (existing user, password set)",
        "cs_choose_user_list": "Choose user list",
        "cs_ft_txt": "Text file",
        "cs_ft_csv": "CSV file",
        "cs_ft_all": "All files",
        "cs_file_error": "File error",
        "cs_more_users": "\n  ... ({count} more)",
        "cs_import_confirm": "Create {count} {kind} from the file on {cams} camera(s)?\n\n{preview}",
        "cs_import_confirm_title": "Confirm batch import",
        "cs_importing": "Importing {count} {kind} on {cams} camera(s)...",
        "cs_choose_fw": "Choose firmware file",
        "cs_ft_fw": "Firmware",
        "cs_need_fw": "Please choose a valid firmware file.",
        "cs_fw_confirm": "Flash firmware\n  {name}\nto {count} camera(s)?\n\n"
        "The firmware MUST match the model. The process takes a few minutes, "
        "after which the camera reboots.",
        "cs_fw_confirm_title": "Confirm firmware update",
        "cs_fw_applying": "Flashing firmware ({count} camera(s)) - please wait...",
        "cs_choose_cfg": "Choose ADM configuration file",
        "cs_ft_cfg": "ADM configuration",
        "cs_cfg_vmd4_note": " | motion detection (VMD4)",
        "cs_cfg_info": "Model: {model} | Firmware: {fw} | {params} parameters, {profiles} stream profile(s){vmd}",
        "cs_cfg_parse_error": "Error: {exc}",
        "cs_need_cfg": "Please choose a valid ADM configuration file.",
        "cs_cfg_confirm": "Apply configuration for model '{model}'\n({params} parameters) to "
        "{count} camera(s)?\n\nThe configuration should match the camera model.",
        "cs_cfg_confirm_title": "Apply configuration",
        "cs_cfg_applying": "Applying configuration ({count} camera(s))...",
        "cs_no_camera_title": "No camera",
        "cs_no_camera": "No camera selected.",
        "cs_no_ip_title": "No IP",
        "cs_no_ip_for": "No IP address known for '{name}'.",
        "cs_read_only_first": "Note: only the first selected camera is read ({name}).",
        "cs_reading_cfg": "Reading configuration from {name} ({ip}) - please wait...",
        "cs_cfg_vmd4_note2": ", motion detection (VMD4)",
        "cs_log_error": "  [ERROR] {name}: {msg}",
        "cs_read_ok": "  [OK] {name}: {params} parameters, {profiles} stream profile(s){vmd} read",
        "cs_log_ok": "OK",
        "cs_log_fail": "ERROR",
        "cs_log_line": "  [{status}] {name}: {msg}",
        # Parameter selection dialog (export)
        "ps_title": "Select and save parameters",
        "ps_header": "{cam} - model {model}, FW {fw}",
        "ps_count_read": "{count} parameters read. Click the check = include in the .cfg.",
        "ps_search": "Search:",
        "ps_col_param": "Parameter",
        "ps_col_value": "Value",
        "ps_all_filtered": "All (filtered)",
        "ps_none_filtered": "None (filtered)",
        "ps_incl_profiles": "Include stream profiles ({count})",
        "ps_incl_vmd4": "Include motion detection (VMD4)",
        "ps_not_available": " (not available)",
        "ps_save": "Save...",
        "ps_cancel": "Cancel",
        "ps_selected_count": "{sel} of {total} selected",
        "ps_nothing_title": "Nothing selected",
        "ps_nothing": "Please select at least one parameter.",
        "ps_save_title": "Save ADM configuration",
        "ps_save_error": "Error while saving",
        "ps_extra_profiles": " + {count} stream profile(s)",
        "ps_extra_vmd4": " + motion detection (VMD4)",
        "ps_saved_title": "Saved",
        "ps_saved": "{count} parameters{extra} saved:\n{path}",

        # Status
        "status_searching": "Searching...",
        "status_searching_with_timeout": "Searching ({timeout} s)...",
        "status_found": "{count} camera(s) found",
        "status_exported": "Exported to {path}",
        "status_no_cameras": "No cameras found",
        "status_error": "Search error.",
        "status_no_axis_cameras": "No Axis cameras found.",
        "msg_error": "Error",
        "msg_search_error": "Search Error",
        
        # Export-Dialog
        "export_dialog_title": "Save Results",
        "filetype_csv": "CSV File",
        "filetype_txt": "Text File",
        "filetype_all": "All Files",
        
        # Spaltenüberschriften (aus FIELD_NAMES)
        "col_Name": "Name",
        "col_IP Adresse: Zeroconfig": "IP Address: Zeroconf",
        "col_IP Adresse: Konfiguriert": "IP Address: Configured",
        "col_IPv6 Adresse": "IPv6 Address",
        "col_Port": "Port",
        "col_Hostname": "Hostname",
        "col_MAC-Adresse/Seriennummer": "MAC Address/Serial",
    }
}

# Farbpaletten fuer hellen und dunklen Modus. Die Basisoptik liefert das
# Sun-Valley-ttk-Theme (sv_ttk, Windows-11-Look); diese Paletten sind auf dessen
# Flaechen abgestimmt und faerben nur, was ttk-Themes nicht erfassen: klassische
# tk-Widgets (tk.Text/Listbox/Menu) und die Hintergruende eigener Toplevels.
# Ohne sv_ttk dienen sie zusaetzlich dem clam-Rueckfall (_apply_clam_theme).
LIGHT_COLORS = {
    "bg": "#fafafa",          # Fensterhintergrund (Sun Valley hell)
    "fg": "#1a1a1a",          # Text
    "field_bg": "#ffffff",    # Eingabefelder/Buttons
    "select_bg": "#cfe3ff",   # markierte Zeile (heller Akzent)
    "select_fg": "#1a1a1a",
    "heading_bg": "#efefef",  # Tabellenkopf/Scrollbar
    "active_bg": "#e0e0e0",   # Hover/aktiv
    "tree_bg": "#ffffff",     # Tabellenflaeche
    "disabled_fg": "#a0a0a0",
}

DARK_COLORS = {
    "bg": "#1c1c1c",          # Fensterhintergrund (Sun Valley dunkel)
    "fg": "#fafafa",
    "field_bg": "#2b2b2b",
    "select_bg": "#2f5d8a",
    "select_fg": "#ffffff",
    "heading_bg": "#2b2b2b",
    "active_bg": "#333333",
    "tree_bg": "#1c1c1c",
    "disabled_fg": "#6f6f6f",
}


class AxisDiscoveryGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Axis_Kamera_Discovery {__version__}")
        self.geometry("1250x550")
        self.minsize(800, 400)

        self.cameras = []
        self._manual_cameras = []  # manuell hinzugefuegte Kameras (ueberleben eine Suche)
        self._result_queue = queue.Queue()
        self._searching = False
        self._refresh_after_id = None
        self._settings_popup = None
        self._sort_state = {}  # Spalte -> zuletzt absteigend? (fuer Klick-Toggle)
        self._text_windows = []  # offene Hilfe-/Lizenz-Fenster (fuer Theme-Wechsel)

        # Gespeicherte Einstellungen laden (Dark Mode bleibt ueber Neustarts erhalten)
        self._config = self._load_config()

        # Basisoptik: modernes Sun-Valley-Theme (sv_ttk) -- angewandt in
        # _apply_theme. Fehlt das Wheel (z. B. Quellbetrieb), dient "clam" als
        # Rueckfall fuer den Dark/Light-Wechsel.
        self._style = ttk.Style(self)
        try:
            self._style.theme_use("clam")
        except tk.TclError:
            pass
        self.dark_mode_var = tk.BooleanVar(value=bool(self.get_setting("dark_mode")))
        self.language_var = tk.StringVar(value=self.get_setting("language") or "de")
        self.update_check_var = tk.BooleanVar(value=bool(self.get_setting("update_check")))
        self._update_q = queue.Queue()  # Ergebnis der Update-Pruefung (Hintergrund-Thread)

        # Sprachwechsel-Callback
        self.language_var.trace_add("write", self._on_language_change)

        # Fonts fuer die automatische Spaltenbreiten-Messung
        self._cell_font = tkfont.nametofont("TkDefaultFont")
        try:
            self._heading_font = tkfont.nametofont("TkHeadingFont")
        except tk.TclError:
            self._heading_font = self._cell_font

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()
        self._apply_theme(self.dark_mode_var.get())  # Startet im hellen Modus

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Klick irgendwo schliesst ein offenes Einstellungen-Dropdown
        self.bind_all("<Button-1>", self._on_global_click, add="+")

        # War Auto-Refresh gespeichert aktiv, Schleife nach dem Start aufnehmen
        if self.autorefresh_var.get():
            self.after(400, self.start_search)

        # Beim Start still auf eine neue GitHub-Version pruefen (abschaltbar).
        if self.update_check_var.get():
            self.after(1500, lambda: self._check_for_updates(silent=True))

    # ------------------------------------------------------- i18n / Uebersetzungen
    def _(self, key, **kwargs):
        """Uebersetzt einen Text-Schluessel in die aktuelle Sprache.
        
        Args:
            key: Schluessel im TRANSLATIONS-Dictionary
            **kwargs: Format-Argumente fuer str.format() (z. B. _("status_found", count=5))
        
        Returns:
            Uebersetzter Text, oder der Schluessel selbst falls nicht gefunden
        """
        lang = self.language_var.get()
        text = TRANSLATIONS.get(lang, {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass  # Formatierung fehlgeschlagen, Originaltext zurueckgeben
        return text

    def _on_language_change(self, *args):
        """Callback beim Aendern der Sprache – aktualisiert alle UI-Texte."""
        self.set_setting("language", self.language_var.get())
        self._update_all_texts()

    def _update_all_texts(self):
        """Aktualisiert alle UI-Texte nach Sprachwechsel."""
        # Fenster-Titel
        self.title(self._("window_title") + f" {__version__}")
        
        # Toolbar
        self.search_btn.config(text=self._("btn_search"))
        if hasattr(self, "_search_menu"):
            self._search_menu.entryconfig(0, label=self._("menu_add_manual"))
        self.duration_label.config(text=self._("label_duration"))
        self.autorefresh_cb.config(text=self._("btn_autorefresh"))
        self.every_label.config(text=self._("label_every"))
        self.export_btn.config(text=self._("btn_export"))
        self.camera_settings_btn.config(text=self._("btn_camera_settings"))
        self.settings_btn.config(text=self._("btn_settings"))
        self.disclaimer_btn.config(text=self._("disclaimer"))
        
        # Sprach-Menübutton (nur wenn das Dropdown gerade offen ist -- der Button
        # lebt im Popup und ist sonst bereits zerstoert)
        btn = getattr(self, "lang_menu_btn", None)
        if btn is not None and btn.winfo_exists():
            btn.config(text=self._("menu_language"))
        
        # Statusbar
        self._update_status_text()
        
        # Tabellenüberschriften
        self._update_table_headers()

    def _update_status_text(self):
        """Aktualisiert den Status-Text in der Statusleiste."""
        if hasattr(self, "status_var"):
            current = self.status_var.get()
            # Einfache Heuristik um Status-Typ zu erkennen
            if "Suche laeuft" in current or "Searching" in current:
                self.status_var.set(self._("status_searching"))
            elif "Kamera" in current and "gefunden" in current:
                # Extrahiere Anzahl
                match = re.search(r'(\d+)', current)
                if match:
                    count = match.group(1)
                    self.status_var.set(self._("status_found", count=int(count)))
            elif "Exportiert" in current or "Exported" in current:
                self.status_var.set(self._("status_exported", path="..."))
            elif "Keine" in current or "No" in current:
                self.status_var.set(self._("status_no_cameras"))

    def _update_table_headers(self):
        """Aktualisiert die Tabellenüberschriften nach Sprachwechsel."""
        if hasattr(self, "tree"):
            for col in TREE_COLUMNS:
                if col:  # Leere Spalte hat keine Überschrift
                    col_key = f"col_{col}"
                    self.tree.heading(col, text=self._(col_key))

    # ---------------------------------------------------------------- UI
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        # "Suchen" als Split-Button: Hauptaktion links, anliegender Pfeil-Teil
        # rechts fuer die Unterpunkte (beide buendig -> ein Bedienelement).
        search_group = ttk.Frame(bar)
        search_group.pack(side=tk.LEFT)
        self.search_btn = ttk.Button(
            search_group, text=self._("btn_search"), command=self.start_search,
        )
        self.search_btn.pack(side=tk.LEFT)
        # Der Menubutton zeigt nur den nativen Theme-Pfeil (kein zweites "▾").
        self.search_menu_btn = ttk.Menubutton(search_group, direction="below")
        self._search_menu = tk.Menu(self.search_menu_btn, tearoff=0)
        self._search_menu.add_command(
            label=self._("menu_add_manual"), command=self._add_manual_camera
        )
        self.search_menu_btn.configure(menu=self._search_menu)
        self.search_menu_btn.pack(side=tk.LEFT)

        self.duration_label = ttk.Label(bar, text=self._("label_duration"))
        self.duration_label.pack(side=tk.LEFT, padx=(12, 4))
        self.timeout_var = tk.IntVar(value=int(self.get_setting("search_duration")))
        ttk.Spinbox(bar, from_=1, to=60, width=4, textvariable=self.timeout_var).pack(
            side=tk.LEFT
        )

        self.autorefresh_var = tk.BooleanVar(value=bool(self.get_setting("autorefresh")))
        self.autorefresh_cb = ttk.Checkbutton(
            bar,
            text=self._("btn_autorefresh"),
            variable=self.autorefresh_var,
            command=self._on_autorefresh_toggle,
        )
        self.autorefresh_cb.pack(side=tk.LEFT, padx=(16, 4))

        self.every_label = ttk.Label(bar, text=self._("label_every"))
        self.every_label.pack(side=tk.LEFT, padx=(0, 4))
        self.interval_var = tk.IntVar(value=int(self.get_setting("refresh_interval")))
        ttk.Spinbox(bar, from_=5, to=3600, width=5, textvariable=self.interval_var).pack(
            side=tk.LEFT
        )

        # Disclaimer-Hinweis in Rot (wie Button, aber ohne Funktion)
        self.disclaimer_btn = ttk.Button(
            bar,
            text=self._("disclaimer"),
            style="Disclaimer.TButton",
            state=tk.DISABLED,
        )
        self.disclaimer_btn.pack(side=tk.LEFT, padx=(16, 4))

        # Aenderungen an Dauer/Intervall dauerhaft speichern
        self.timeout_var.trace_add("write", self._persist_toolbar_settings)
        self.interval_var.trace_add("write", self._persist_toolbar_settings)

        # Menue-Button "Einstellungen" rechts neben "Exportieren"
        self.settings_btn = ttk.Button(
            bar, text=self._("btn_settings"), command=self._toggle_settings_menu
        )
        self.settings_btn.pack(side=tk.RIGHT)

        # "Kamera Einstellungen" direkt links neben "Einstellungen"
        self.camera_settings_btn = ttk.Button(
            bar, text=self._("btn_camera_settings"), command=self._open_camera_settings
        )
        self.camera_settings_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.export_btn = ttk.Button(
            bar, text=self._("btn_export"), command=self.export, state=tk.DISABLED
        )
        self.export_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT, padx=8)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Füge leere Endlos-Spalte für bessere Optik hinzu
        tree_columns = list(COLUMNS) + [""]
        self.tree = ttk.Treeview(frame, columns=tree_columns, show="headings")
        for i, col in enumerate(tree_columns):
            if col:  # Normale Spalte
                # Klick auf die Ueberschrift sortiert nach dieser Spalte
                self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
                # stretch=NO: die per _autosize_columns gemessenen Breiten bleiben verbindlich
                self.tree.column(col, width=180, anchor=tk.W, stretch=tk.NO)
            else:  # Leere Endlos-Spalte
                self.tree.heading(col, text="", command=lambda: None)
                self.tree.column(col, width=100, anchor=tk.W, stretch=tk.YES)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._open_in_browser)
        self._apply_column_visibility()  # gespeicherte Spaltenauswahl anwenden
        self._autosize_columns()  # initiale Breite an die Ueberschriften anpassen

    # ----------------------------------------------------- Spalten ein/aus
    def _apply_column_visibility(self):
        """Setzt die sichtbaren Spalten gemaess gespeicherter Auswahl."""
        hidden = set(self.get_setting("hidden_columns") or [])
        # Leere Spalte immer anzeigen, Daten-Spalten gemäss Einstellung
        visible = [c for c in TREE_COLUMNS if c and c not in hidden]
        # Leere Spalte hinzufügen
        if TREE_COLUMNS and not TREE_COLUMNS[-1]:
            visible.append(TREE_COLUMNS[-1])
        # Mindestens eine Spalte sichtbar lassen
        self.tree["displaycolumns"] = visible if visible else list(TREE_COLUMNS)

    def _show_columns_dialog(self):
        """Kleiner Dialog mit einer Checkbox je Spalte (sichtbar/ausgeblendet)."""
        palette = DARK_COLORS if self.dark_mode_var.get() else LIGHT_COLORS
        win = tk.Toplevel(self)
        win.title(self._("columns_dialog_title"))
        win.transient(self)
        win.resizable(False, False)
        win.configure(bg=palette["bg"])
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=self._("columns_dialog_label")).pack(anchor=tk.W, pady=(0, 6))

        hidden = set(self.get_setting("hidden_columns") or [])
        self._col_vars = {}
        for col in COLUMNS:
            var = tk.BooleanVar(value=col not in hidden)
            self._col_vars[col] = var
            # Uebersetzte Spaltenname verwenden
            col_key = f"col_{col}"
            ttk.Checkbutton(frame, text=self._(col_key), variable=var,
                            command=self._on_columns_changed).pack(anchor=tk.W)
        ttk.Button(frame, text=self._("btn_close"), command=win.destroy).pack(anchor=tk.E, pady=(8, 0))

    def _on_columns_changed(self):
        visible = [c for c, v in self._col_vars.items() if v.get()]
        if not visible:
            # Mindestens eine Spalte muss sichtbar bleiben -> erste wieder aktivieren
            first = next(iter(self._col_vars))
            self._col_vars[first].set(True)
            visible = [first]
        hidden = [c for c in COLUMNS if c not in visible]
        self.set_setting("hidden_columns", hidden)
        self._apply_column_visibility()

    def _autosize_columns(self):
        """Passt jede Spaltenbreite an den breitesten Inhalt (inkl. Ueberschrift) an."""
        for col in TREE_COLUMNS:
            if not col:  # Leere Spalte überspringen (hat stretch=YES)
                continue
            header = self.tree.heading(col, "text")
            width = self._heading_font.measure(header)
            for iid in self.tree.get_children(""):
                cell = self.tree.set(iid, col)
                width = max(width, self._cell_font.measure(cell))
            # Polster + sinnvolle Unter-/Obergrenze
            self.tree.column(col, width=min(max(width + 24, 60), 600))

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value=self._("status_no_cameras"))
        ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4
        ).pack(side=tk.BOTTOM, fill=tk.X)

    # ----------------------------------------------------------- Sortierung
    @staticmethod
    def _sort_key(value):
        """Sortierschluessel: Zahlen numerisch, IPv4 nach Oktetten, sonst Text."""
        v = value.strip()
        if v.isdigit():
            return (0, int(v))
        first = v.split(",")[0].strip()
        parts = first.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            return (0, tuple(int(p) for p in parts))
        return (1, v.casefold())

    def _sort_by(self, col):
        reverse = self._sort_state.get(col, False)
        rows = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        rows.sort(key=lambda t: self._sort_key(t[0]), reverse=reverse)
        for index, (_, iid) in enumerate(rows):
            self.tree.move(iid, "", index)
        self._sort_state[col] = not reverse  # naechster Klick: andere Richtung

        # Pfeil nur in der aktiven Spalte anzeigen
        for c in TREE_COLUMNS:
            if not c:  # Leere Spalte hat keine Überschrift mit Pfeil
                continue
            arrow = ("  ▲" if not reverse else "  ▼") if c == col else ""
            self.tree.heading(c, text=self._(f"col_{c}") + arrow)

    # ----------------------------------------------------------- Suche
    def start_search(self):
        if self._searching:
            return
        self._cancel_refresh()  # anstehenden Auto-Refresh verwerfen, da wir jetzt suchen
        self._searching = True
        self.search_btn.config(state=tk.DISABLED)
        self.export_btn.config(state=tk.DISABLED)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.cameras = []

        timeout = self.timeout_var.get()
        self.status_var.set(self._("status_searching_with_timeout", timeout=timeout))
        self.progress.start(12)

        thread = threading.Thread(target=self._run_discovery, args=(timeout,), daemon=True)
        thread.start()
        self.after(150, self._poll_result)

    def _run_discovery(self, timeout):
        try:
            discovery = AxisDiscovery()
            discovery.start()
            discovery.search(timeout)
            discovery.stop()
            self._result_queue.put(("ok", discovery.services))
        except Exception as exc:  # an die GUI weiterreichen
            self._result_queue.put(("error", str(exc)))

    def _poll_result(self):
        try:
            status, payload = self._result_queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_result)
            return

        self.progress.stop()
        self._searching = False
        self.search_btn.config(state=tk.NORMAL)

        if status == "error":
            self.status_var.set(self._("status_error"))
            messagebox.showerror(self._("msg_error"), payload)
            return

        self.cameras = payload
        for cam in self.cameras:
            # Werte für Daten-Spalten + leere Zelle für Endlos-Spalte
            values = [cam.get(c, "") for c in COLUMNS] + [""]
            self.tree.insert("", tk.END, values=values)

        # Manuell hinzugefuegte Kameras wieder einmischen (die Suche hat die Liste
        # geleert); per IP entdeckte Duplikate ueberspringen.
        discovered_ips = {get_first_ip(c) for c in self.cameras}
        for cam in self._manual_cameras:
            if get_first_ip(cam) in discovered_ips:
                continue
            self.cameras.append(cam)
            values = [cam.get(c, "") for c in COLUMNS] + [""]
            self.tree.insert("", tk.END, values=values)

        self._autosize_columns()  # Breiten an die neuen Inhalte anpassen

        if self.cameras:
            self.export_btn.config(state=tk.NORMAL)
            self.status_var.set(self._("status_found", count=len(self.cameras)))
        else:
            self.status_var.set(self._("status_no_axis_cameras"))

        self._schedule_refresh()  # naechsten Auto-Refresh planen (falls aktiviert)

    def _add_manual_camera(self):
        """Dialog: Kamera manuell ueber ihre IP-Adresse hinzufuegen (Unterpunkt
        des Suchen-Buttons). Der Eintrag ueberlebt eine erneute Suche."""
        palette = DARK_COLORS if self.dark_mode_var.get() else LIGHT_COLORS
        dlg = tk.Toplevel(self)
        dlg.title(self._("manual_add_title"))
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(bg=palette["bg"])

        frm = ttk.Frame(dlg, padding=20)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=self._("manual_add_hint"), wraplength=440).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 16)
        )

        name_var = tk.StringVar()
        ip_var = tk.StringVar()
        port_var = tk.StringVar(value="80")
        host_var = tk.StringVar()
        fields = (
            ("manual_add_name", name_var),
            ("manual_add_ip", ip_var),
            ("manual_add_port", port_var),
            ("manual_add_hostname", host_var),
        )
        entries = {}
        for i, (key, var) in enumerate(fields, start=1):
            ttk.Label(frm, text=self._(key)).grid(
                row=i, column=0, sticky="w", padx=(0, 12), pady=5
            )
            ent = ttk.Entry(frm, textvariable=var, width=38)
            ent.grid(row=i, column=1, sticky="ew", pady=5, ipady=2)
            entries[key] = ent
        frm.columnconfigure(1, weight=1)
        entries["manual_add_ip"].focus_set()

        def _submit(*_):
            ip = ip_var.get().strip()
            if not ip:
                messagebox.showwarning(self._("manual_add_title"),
                                       self._("manual_add_ip_required"), parent=dlg)
                return
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                messagebox.showwarning(self._("manual_add_title"),
                                       self._("manual_add_ip_invalid", ip=ip), parent=dlg)
                return
            if any(get_first_ip(c) == ip for c in self.cameras):
                messagebox.showinfo(self._("manual_add_title"),
                                    self._("manual_add_duplicate", ip=ip), parent=dlg)
                return
            cam = {
                "Name": name_var.get().strip() or self._("manual_add_default_name"),
                "IP Adresse: Zeroconfig": "",
                "IP Adresse: Konfiguriert": ip,
                "IPv6 Adresse": ip if addr.version == 6 else "",
                "Port": port_var.get().strip(),
                "Hostname": host_var.get().strip(),
                "MAC-Adresse/Seriennummer": "",
            }
            self._manual_cameras.append(cam)
            self.cameras.append(cam)
            values = [cam.get(c, "") for c in COLUMNS] + [""]
            iid = self.tree.insert("", tk.END, values=values)
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._autosize_columns()
            self.export_btn.config(state=tk.NORMAL)
            self.status_var.set(self._("status_found", count=len(self.cameras)))
            dlg.destroy()

        btns = ttk.Frame(frm)
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text=self._("manual_add_cancel"),
                   command=dlg.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text=self._("manual_add_add"),
                   command=_submit).pack(side=tk.RIGHT, padx=(0, 8))

        dlg.bind("<Return>", _submit)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_reqheight()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()

    def _persist_toolbar_settings(self, *_):
        """Speichert Dauer, Auto-Refresh und Intervall dauerhaft."""
        try:
            self._config["search_duration"] = self.timeout_var.get()
            self._config["autorefresh"] = self.autorefresh_var.get()
            self._config["refresh_interval"] = self.interval_var.get()
        except tk.TclError:
            return  # Feld gerade leer/ungueltig -> nichts speichern
        self._save_config()

    # ------------------------------------------------------- Auto-Refresh
    def _on_autorefresh_toggle(self):
        self._persist_toolbar_settings()
        if self.autorefresh_var.get():
            # Sofort einen Durchlauf starten; danach planen sich Folgelaeufe selbst
            if not self._searching:
                self.start_search()
        else:
            self._cancel_refresh()

    def _schedule_refresh(self):
        self._cancel_refresh()
        if not self.autorefresh_var.get():
            return
        interval_ms = max(5, self.interval_var.get()) * 1000
        self._refresh_after_id = self.after(interval_ms, self.start_search)
        self.status_var.set(
            f"{self.status_var.get()}  -  naechster Refresh in {interval_ms // 1000} s"
        )

    def _cancel_refresh(self):
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None

    def _on_close(self):
        self._cancel_refresh()
        self._close_settings_menu()
        self.destroy()

    # --------------------------------------------------- Menue: Einstellungen
    def _toggle_settings_menu(self):
        # offenes Dropdown wieder schliessen
        if self._settings_popup is not None and self._settings_popup.winfo_exists():
            self._close_settings_menu()
            return

        btn = self.settings_btn
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)        # randloses Fenster (wie ein Menue)
        popup.transient(self)
        popup.withdraw()  # unsichtbar erstellen, um Artefakte an (0,0) zu vermeiden
        frame = ttk.Frame(popup, relief="solid", borderwidth=1)
        frame.pack(fill=tk.BOTH, expand=True)

        # Dark-Mode-Umschalter: Haken an -> dunkel, Haken aus -> hell.
        ttk.Checkbutton(
            frame,
            text=self._("menu_dark_mode"),
            variable=self.dark_mode_var,
            command=self._toggle_dark_mode,
        ).pack(fill=tk.X, padx=4, pady=2)
        # Automatische Update-Pruefung beim Start (abschaltbar).
        ttk.Checkbutton(
            frame,
            text=self._("menu_update_check"),
            variable=self.update_check_var,
            command=self._toggle_update_check,
        ).pack(fill=tk.X, padx=4, pady=2)
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X)

        # Sprachauswahl mit Untermenü
        self.lang_menu_btn = ttk.Menubutton(
            frame,
            text=self._("menu_language"),
            direction="below"
        )
        self.lang_menu_btn.pack(anchor=tk.W, padx=4, pady=(2, 0), fill=tk.X)
        
        # Untermenü für Sprachauswahl erstellen
        lang_menu = tk.Menu(self.lang_menu_btn, tearoff=0)
        lang_menu.add_command(
            label=self._("menu_language_de"),
            command=lambda: self.language_var.set("de")
        )
        lang_menu.add_command(
            label=self._("menu_language_en"),
            command=lambda: self.language_var.set("en")
        )
        self.lang_menu_btn.configure(menu=lang_menu)

        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X)

        for label_key, command in (
            ("menu_check_updates", lambda: self._check_for_updates(silent=False)),
            ("menu_columns", self._show_columns_dialog),
            ("menu_info", self._show_info),
            ("menu_help", self._show_help),
            ("menu_licenses", self._show_licenses),
        ):
            ttk.Button(
                frame,
                text=self._(label_key),
                command=lambda c=command: self._choose_setting(c),
            ).pack(fill=tk.X)  # fuellt die volle Breite des Dropdowns

        self._settings_popup = popup

        # Breite mindestens wie der Button, aber breit genug fuer den laengsten
        # Eintrag (z. B. die "Dark Mode"-Checkbox), damit nichts abgeschnitten wird.
        popup.update_idletasks()
        width = max(btn.winfo_width(), frame.winfo_reqwidth())
        height = frame.winfo_reqheight()
        # rechtsbuendig zur Button-Kante ausrichten (der Button sitzt rechts),
        # damit das breitere Menue nicht ueber den Fensterrand hinauslaeuft
        x = btn.winfo_rootx() + btn.winfo_width() - width
        y = btn.winfo_rooty() + btn.winfo_height()
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()  # jetzt sichtbar machen

    def _choose_setting(self, command):
        # erst Dropdown schliessen, dann die Aktion ausfuehren
        self._close_settings_menu()
        command()

    def _on_global_click(self, event):
        # schliesst das Dropdown bei Klick ausserhalb (Klicks auf den Button
        # und auf die Dropdown-Eintraege werden von deren eigenen Befehlen erledigt)
        popup = self._settings_popup
        if popup is None or not popup.winfo_exists():
            return
        w = event.widget
        if w is self.settings_btn:
            return
        if isinstance(w, tk.Widget) and str(w).startswith(str(popup)):
            return
        self._close_settings_menu()

    def _close_settings_menu(self):
        if self._settings_popup is not None and self._settings_popup.winfo_exists():
            self._settings_popup.destroy()
        self._settings_popup = None

    # ------------------------------------------------------------- Dark Mode
    def _toggle_dark_mode(self):
        self._apply_theme(self.dark_mode_var.get())
        self.set_setting("dark_mode", self.dark_mode_var.get())

    # -------------------------------------------------------- Update-Pruefung
    def _toggle_update_check(self):
        self.set_setting("update_check", self.update_check_var.get())

    def _check_for_updates(self, silent=True):
        """Prueft im Hintergrund die neueste GitHub-Version. silent=True: nur bei
        einer neueren Version melden (Start); False: immer eine Rueckmeldung
        (manueller Aufruf ueber das Menue)."""
        threading.Thread(target=self._worker_update_check, args=(silent,),
                         daemon=True).start()
        self.after(200, self._poll_update_check)

    def _worker_update_check(self, silent):
        # Laeuft im Thread: KEIN Tk-Zugriff, nur Netz + Queue.
        import urllib.request
        try:
            req = urllib.request.Request(
                _GITHUB_API_RELEASES,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "Axis_Kamera_Discovery"})
            with urllib.request.urlopen(req, timeout=8,
                                        context=_verified_ssl_context()) as resp:
                data = json.load(resp)
            newest = None
            newest_t = None
            url = GITHUB_RELEASES_URL
            for rel in (data if isinstance(data, list) else []):
                if rel.get("draft"):
                    continue
                t = _parse_version(rel.get("tag_name", ""))
                if t and (newest_t is None or t > newest_t):
                    newest_t, newest = t, rel.get("tag_name", "").lstrip("v")
                    url = rel.get("html_url") or url
            self._update_q.put(("ok", silent, newest, newest_t, url))
        except Exception as exc:  # Netzfehler etc. an die GUI weiterreichen
            self._update_q.put(("error", silent, str(exc)))

    def _poll_update_check(self):
        try:
            item = self._update_q.get_nowait()
        except queue.Empty:
            self.after(200, self._poll_update_check)
            return

        if item[0] == "error":
            _, silent, msg = item
            if not silent:
                messagebox.showwarning(self._("update_title"),
                                       self._("update_error", error=msg))
            return

        _, silent, newest, newest_t, url = item
        current_t = _parse_version(__version__)
        if newest_t and current_t and newest_t > current_t:
            if messagebox.askyesno(self._("update_title"),
                                   self._("update_available",
                                          current=__version__, new=newest)):
                webbrowser.open(url)
        elif not silent:
            messagebox.showinfo(self._("update_title"),
                                self._("update_none", current=__version__))

    # ----------------------------------------------------- Einstellungen-Datei
    @staticmethod
    def _load_config():
        """Laedt die Einstellungen: Defaults als Basis, gespeicherte Werte gewinnen.

        Unbekannte Schluessel aus der Datei bleiben erhalten (Vorwaerts-
        kompatibilitaet); bei Lese-/Parse-Fehlern gelten die Defaults.
        """
        config = dict(DEFAULT_SETTINGS)
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                config.update(data)
        except (OSError, ValueError):
            pass
        return config

    def _save_config(self):
        """Schreibt alle Einstellungen als JSON (Fehler werden still ignoriert)."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, sort_keys=True)
        except OSError:
            pass

    def get_setting(self, key, default=None):
        """Liest eine Einstellung (Reihenfolge: Datei -> DEFAULT_SETTINGS -> default)."""
        return self._config.get(key, DEFAULT_SETTINGS.get(key, default))

    def set_setting(self, key, value):
        """Setzt eine Einstellung und speichert sie sofort dauerhaft."""
        self._config[key] = value
        self._save_config()

    def _apply_theme(self, dark):
        """Wendet das Sun-Valley-Theme an (Hell/Dunkel).

        sv_ttk liefert die Basisoptik aller ttk-Widgets. Fehlt das Wheel, faellt
        die Methode auf das bisherige clam-Styling (_apply_clam_theme) zurueck.
        Klassische tk-Widgets (tk.Text/Listbox/Menu) und eigene Toplevels erfasst
        kein ttk-Theme -> sie werden hier ueber option_add/Palette gefaerbt.
        """
        c = DARK_COLORS if dark else LIGHT_COLORS
        self.configure(bg=c["bg"])

        if not self._apply_sun_valley(dark):
            self._apply_clam_theme(c)

        # Roter "Disclaimer"-Button-Text -- unabhaengig vom Basistheme, erbt den
        # Rest vom jeweiligen TButton-Style (sv_ttk oder clam).
        self._style.configure("Disclaimer.TButton", foreground="#ff0000")
        self._style.map("Disclaimer.TButton", foreground=[("disabled", "#ff0000")])

        # Klassische tk-Widgets (Text/Listbox/Menu) deckt kein ttk-Theme ab:
        # Defaults fuer neu erzeugte Exemplare setzen.
        for cls in ("Text", "Listbox"):
            self.option_add(f"*{cls}.background", c["tree_bg"])
            self.option_add(f"*{cls}.foreground", c["fg"])
            self.option_add(f"*{cls}.insertBackground", c["fg"])
            self.option_add(f"*{cls}.selectBackground", c["select_bg"])
            self.option_add(f"*{cls}.selectForeground", c["select_fg"])
        self.option_add("*Menu.background", c["tree_bg"])
        self.option_add("*Menu.foreground", c["fg"])

        # sv_ttk nutzt eine groessere Schrift als TkDefaultFont -> Messschriften
        # fuer die Spaltenbreite nachziehen und ggf. neu vermessen.
        self._refresh_measure_fonts()

        # Hilfe-/Lizenzfenster sind klassische tk.Text-Widgets ohne ttk-Style
        self._theme_text_windows(c)

    def _apply_sun_valley(self, dark):
        """Aktiviert das Sun-Valley-Theme; True bei Erfolg, False ohne sv_ttk."""
        try:
            import sv_ttk
            sv_ttk.set_theme("dark" if dark else "light")
            return True
        except Exception:
            return False  # kein sv_ttk -> Aufrufer nutzt den clam-Rueckfall

    def _refresh_measure_fonts(self):
        """Uebernimmt die tatsaechliche Treeview-Schrift fuer die Spaltenmessung."""
        cell = self._style.lookup("Treeview", "font") or "TkDefaultFont"
        head = self._style.lookup("Treeview.Heading", "font") or "TkHeadingFont"
        try:
            self._cell_font = tkfont.Font(font=cell)
        except tk.TclError:
            pass
        try:
            self._heading_font = tkfont.Font(font=head)
        except tk.TclError:
            self._heading_font = self._cell_font
        if hasattr(self, "tree"):
            self._autosize_columns()

    def _apply_clam_theme(self, c):
        """Rueckfall ohne sv_ttk: faerbt alle ttk-Widgets ueber das clam-Theme."""
        s = self._style
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass

        # Grundeinstellung fuer alle ttk-Widgets
        s.configure(
            ".",
            background=c["bg"],
            foreground=c["fg"],
            fieldbackground=c["field_bg"],
            bordercolor=c["active_bg"],
            troughcolor=c["field_bg"],
            arrowcolor=c["fg"],
        )
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("TSeparator", background=c["active_bg"])

        s.configure("TButton", background=c["field_bg"], foreground=c["fg"])
        s.map(
            "TButton",
            background=[("active", c["active_bg"]), ("disabled", c["bg"])],
            foreground=[("disabled", c["disabled_fg"])],
        )

        # Disclaimer-Button: roter Text, sieht aus wie Button aber ohne Funktion
        s.configure("Disclaimer.TButton", background=c["field_bg"], foreground="#ff0000")
        s.map(
            "Disclaimer.TButton",
            background=[("active", c["active_bg"]), ("disabled", c["bg"])],
            foreground=[("disabled", "#ff0000")],
        )

        s.configure(
            "TCheckbutton",
            background=c["bg"],
            foreground=c["fg"],
            indicatorbackground=c["field_bg"],
            indicatorforeground=c["fg"],
        )
        s.map(
            "TCheckbutton",
            background=[("active", c["bg"])],
            indicatorbackground=[("selected", c["select_bg"]), ("active", c["field_bg"])],
            indicatorforeground=[("selected", c["select_fg"])],
            foreground=[("disabled", c["disabled_fg"])],
        )

        s.configure(
            "TSpinbox",
            fieldbackground=c["field_bg"],
            foreground=c["fg"],
            background=c["field_bg"],
            arrowcolor=c["fg"],
        )

        # Eingabefelder/Comboboxen (u. a. im Kamera-Einstellungen-Dialog)
        s.configure("TEntry", fieldbackground=c["field_bg"], foreground=c["fg"],
                    insertcolor=c["fg"])
        s.configure("TCombobox", fieldbackground=c["field_bg"], foreground=c["fg"],
                    background=c["field_bg"], arrowcolor=c["fg"])
        s.map("TCombobox",
              fieldbackground=[("readonly", c["field_bg"])],
              foreground=[("readonly", c["fg"])])
        s.configure("TLabelframe", background=c["bg"], bordercolor=c["active_bg"])
        s.configure("TLabelframe.Label", background=c["bg"], foreground=c["fg"])
        s.configure("TNotebook", background=c["bg"], bordercolor=c["active_bg"])
        s.configure("TNotebook.Tab", background=c["heading_bg"], foreground=c["fg"])
        s.map("TNotebook.Tab",
              background=[("selected", c["bg"]), ("active", c["active_bg"])],
              foreground=[("selected", c["fg"])])
        s.configure("TRadiobutton", background=c["bg"], foreground=c["fg"],
                    indicatorbackground=c["field_bg"])
        s.map("TRadiobutton",
              background=[("active", c["bg"])],
              indicatorbackground=[("selected", c["select_bg"])],
              foreground=[("disabled", c["disabled_fg"])])

        s.configure("TProgressbar", background=c["select_bg"], troughcolor=c["field_bg"])

        s.configure("TScrollbar", background=c["heading_bg"], troughcolor=c["field_bg"])
        s.map("TScrollbar", background=[("active", c["active_bg"])])

        # Tabelle: Flaeche, Text und markierte Zeile
        s.configure(
            "Treeview",
            background=c["tree_bg"],
            foreground=c["fg"],
            fieldbackground=c["tree_bg"],
        )
        s.map(
            "Treeview",
            background=[("selected", c["select_bg"])],
            foreground=[("selected", c["select_fg"])],
        )
        s.configure("Treeview.Heading", background=c["heading_bg"], foreground=c["fg"])
        s.map("Treeview.Heading", background=[("active", c["active_bg"])])

    def _theme_text_windows(self, colors):
        """Faerbt offene Hilfe-/Lizenzfenster (tk.Text) mit den aktuellen Farben."""
        for win, text in list(self._text_windows):
            if not win.winfo_exists():
                self._text_windows.remove((win, text))
                continue
            win.configure(bg=colors["bg"])
            text.configure(
                bg=colors["tree_bg"],
                fg=colors["fg"],
                insertbackground=colors["fg"],
                selectbackground=colors["select_bg"],
                selectforeground=colors["select_fg"],
            )

    def _show_info(self):
        messagebox.showinfo(
            self._("info_title"),
            self._("info_body", version=__version__,
                   components=self._component_versions()),
        )

    def _component_versions(self):
        """Laufzeit-Versionen der wichtigsten Programmteile als Text."""
        items = [
            ("Python", platform.python_version()),
            ("Tcl/Tk", self.tk.call("info", "patchlevel")),
        ]
        for pkg in ("zeroconf", "ifaddr", "prettytable", "wcwidth"):
            try:
                items.append((pkg, metadata.version(pkg)))
            except metadata.PackageNotFoundError:
                items.append((pkg, "?"))
        return "\n".join(f"  {name:<12}{ver}" for name, ver in items)

    def _show_help(self):
        self._show_text_window("README.md", self._("help_title"))

    def _show_licenses(self):
        self._show_text_window("THIRD_PARTY_LICENSES.md", self._("licenses_title"))

    def _show_text_window(self, filename, title):
        # Unter PyInstaller liegen gebundelte Datendateien in sys._MEIPASS,
        # sonst neben diesem Modul (AppImage/Quellcode).
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, filename)
        if not os.path.exists(path):
            messagebox.showerror(title, self._("file_not_found", filename=filename))
            return
        with open(path, encoding="utf-8") as f:
            content = f.read()

        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("850x650")
        text = scrolledtext.ScrolledText(win, wrap=tk.WORD, padx=8, pady=8)
        text.insert("1.0", content)
        text.config(state=tk.DISABLED)  # schreibgeschuetzt
        text.pack(fill=tk.BOTH, expand=True)

        # Fenster fuer spaetere Theme-Wechsel merken und sofort einfaerben
        self._text_windows.append((win, text))
        win.bind(
            "<Destroy>",
            lambda e, w=win: e.widget is w and self._forget_text_window(w),
        )
        self._theme_text_windows(DARK_COLORS if self.dark_mode_var.get() else LIGHT_COLORS)

    def _forget_text_window(self, win):
        self._text_windows = [(w, t) for (w, t) in self._text_windows if w is not win]

    # ------------------------------------------------- Kamera-Einstellungen
    def _open_camera_settings(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                self._("cs_select_first_title"),
                self._("cs_select_first"),
            )
            return
        # Werte aus Treeview (inkl. leere Endlos-Spalte) -> nur Daten-Spalten verwenden
        cams = [dict(zip(COLUMNS, self.tree.item(iid, "values")[:len(COLUMNS)])) for iid in selection]
        palette = DARK_COLORS if self.dark_mode_var.get() else LIGHT_COLORS
        CameraSettingsDialog(self, cams, palette)

    # ----------------------------------------------------------- Aktionen
    def _open_in_browser(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")[:len(COLUMNS)]  # Leere Endlos-Spalte ausschließen
        # gleiche Logik wie das CLI: erste IP aus dem Adressfeld
        first_ip = get_first_ip(dict(zip(COLUMNS, values)))
        if first_ip:
            webbrowser.open(f"http://{first_ip}")

    def export(self):
        if not self.cameras:
            return
        path = filedialog.asksaveasfilename(
            title=self._("export_dialog_title"),
            defaultextension=".csv",
            initialfile="axis_cameras.csv",
            filetypes=[
                (self._("filetype_csv"), "*.csv"),
                (self._("filetype_txt"), "*.txt"),
                (self._("filetype_all"), "*.*"),
            ],
        )
        if not path:
            return
        # Format anhand der Dateiendung (csv -> CSV, sonst Texttabelle)
        # Exportiert nur die aktuell sichtbaren Spalten (leere Endlos-Spalte ausschließen)
        visible_columns = [c for c in self.tree["displaycolumns"] if c]
        export_results(self.cameras, path, columns=visible_columns)
        self.status_var.set(self._("status_exported", path=path))


# Fallback-Zeitzonen, falls die Laufzeit keine tz-Datenbank hat (zoneinfo leer,
# z. B. Windows ohne tzdata). Die Combobox ist frei editierbar -- der Nutzer kann
# jeden IANA-Namen eingeben, und "Von erster Kamera laden" holt die vom Geraet
# selbst unterstuetzte Liste.
_FALLBACK_ZONES = [
    "UTC", "Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/London",
    "Europe/Paris", "Europe/Madrid", "Europe/Rome", "Europe/Amsterdam",
    "Europe/Stockholm", "Europe/Warsaw", "Europe/Moscow", "America/New_York",
    "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Sao_Paulo",
    "Asia/Dubai", "Asia/Kolkata", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney",
]


def _iana_zones():
    """Liefert die IANA-Zeitzonennamen aus der stdlib (zoneinfo), sonst den Fallback."""
    try:
        from zoneinfo import available_timezones
        zones = sorted(available_timezones())
        if zones:
            return zones
    except Exception:  # noqa: BLE001 - keine tz-Datenbank o. Ae.
        pass
    return list(_FALLBACK_ZONES)


class CameraSettingsDialog(tk.Toplevel):
    """Dialog zum Aendern von Einstellungen an einer oder mehreren Kameras.

    Reiter "IP-Adresse": IP aendern (DHCP, Start-IP fortlaufend, oder pro Kamera).
    Reiter "Benutzer": regulaeren Axis-Benutzer anlegen oder dessen Passwort aendern.
    Reiter "ONVIF-Benutzer": ONVIF-Benutzer anlegen oder dessen Passwort aendern.
    Die Aufrufe laufen in einem Hintergrund-Thread; Ergebnisse je Kamera werden
    ueber eine Queue eingesammelt und im Ergebnisfeld angezeigt.
    """

    def __init__(self, master, cameras, palette):
        super().__init__(master)
        self._app = master  # AxisDiscoveryGUI (liefert die Sprache)
        # Sprache als reinen String cachen: die Worker laufen in Hintergrund-
        # Threads und duerfen kein Tk anfassen (language_var.get()). Wird bei
        # jeder Aktion im Haupt-Thread (in _conn_kwargs) aufgefrischt.
        self._lang = master.language_var.get()
        self.title(self._("camera_settings_title"))
        self.geometry("720x780")
        # Breite darf klein werden -> die Reiter-Leiste scrollt dann horizontal.
        self.minsize(480, 600)
        self.transient(master)
        self._palette = palette
        self.configure(bg=palette["bg"])

        self.cameras = cameras
        self._queue = queue.Queue()
        self._working = False
        self._ip_entries = {}   # Kamera-Index -> StringVar (Modus "pro Kamera")
        self._mode_var = tk.StringVar(value="dhcp")

        self._build_ui()
        self._on_mode_change()   # passende IP-Felder anzeigen/ausblenden
        self._on_ipv6_mode_change()  # IPv6-Felder je nach Modus anzeigen/ausblenden
        self._on_user_action()   # Rollen-Feld je nach Benutzer-Aktion schalten

    def _(self, key, **kwargs):
        """Uebersetzt anhand der gecachten Sprache (self._lang), ohne Tk-Zugriff,
        damit die Methode auch aus Worker-Threads sicher aufrufbar ist."""
        text = TRANSLATIONS.get(self._lang, {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text=self._("camera_settings_cameras_selected", count=len(self.cameras)),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W)

        # --- Zugangsdaten ---
        cred = ttk.LabelFrame(outer, text=self._("camera_settings_credentials"), padding=8)
        cred.pack(fill=tk.X, pady=(8, 4))
        self.user_var = tk.StringVar(value="root")
        self.pass_var = tk.StringVar()
        self.scheme_var = tk.StringVar(value="auto")
        self.port_var = tk.StringVar()
        self.timeout_var = tk.IntVar(value=10)

        ttk.Label(cred, text=self._("camera_settings_user")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.user_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(cred, text=self._("camera_settings_password")).grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.pass_var, width=18, show="*").grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(cred, text=self._("camera_settings_connection")).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            cred, textvariable=self.scheme_var, width=15, state="readonly",
            values=("auto", "https", "http"),
        ).grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(cred, text=self._("camera_settings_port")).grid(row=1, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.port_var, width=18).grid(row=1, column=3, padx=4, pady=2)
        ttk.Label(cred, text=self._("camera_settings_timeout")).grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Spinbox(cred, from_=2, to=120, width=6, textvariable=self.timeout_var).grid(
            row=2, column=1, sticky=tk.W, padx=4, pady=2
        )

        # --- Aktionen in Reitern ---
        # ttk.Notebook kann seine Reiter nicht scrollen -> bei zu schmalem Fenster
        # wuerden sie abgeschnitten. Deshalb: ein "tabloses" Notebook (Reiter per
        # leerem Style ausgeblendet) plus eine eigene, horizontal scrollbare
        # Reiter-Leiste darueber (Pfeile + Mausrad).
        self._build_tabbar(outer)
        self.nb = ttk.Notebook(outer, style="Tabless.TNotebook")
        self.nb.pack(fill=tk.X, pady=(0, 4))
        self.nb.bind("<<NotebookTabChanged>>", self._sync_active_tab)

        # ===== Reiter: IP-Adresse =====
        # Reiter-Frames + zugehoerige Apply-Handler merken, damit _apply nicht
        # vom (uebersetzten) Reiter-Text abhaengt.
        self._tab_handlers = []
        tab_ip = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_ip, self._("camera_settings_ip_tab"))
        self._tab_handlers.append((str(tab_ip), self._apply_ip))
        ttk.Radiobutton(tab_ip, text=self._("cs_ip_dhcp"), value="dhcp",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ip, text=self._("cs_ip_range"), value="range",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ip, text=self._("cs_ip_each"), value="each",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)

        # gemeinsame Felder Maske/Gateway (fuer "range" und "each")
        self.mask_var = tk.StringVar(value="255.255.255.0")
        self.gw_var = tk.StringVar()
        self.start_ip_var = tk.StringVar()

        self._shared = ttk.Frame(tab_ip)
        ttk.Label(self._shared, text=self._("cs_subnet")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._shared, textvariable=self.mask_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self._shared, text=self._("cs_gateway_opt")).grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._shared, textvariable=self.gw_var, width=18).grid(row=0, column=3, padx=4, pady=2)

        self._range_frame = ttk.Frame(tab_ip)
        ttk.Label(self._range_frame, text=self._("cs_start_ip")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._range_frame, textvariable=self.start_ip_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(
            self._range_frame,
            text=self._("cs_range_hint"),
        ).grid(row=0, column=2, columnspan=2, sticky=tk.W, padx=4)

        # "each": je Kamera ein IP-Feld
        self._each_frame = ttk.Frame(tab_ip)
        for idx, cam in enumerate(self.cameras):
            name = cam.get("Name", "?")
            current = get_first_ip(cam)
            var = tk.StringVar(value=current)
            self._ip_entries[idx] = var
            ttk.Label(self._each_frame, text=f"{name} ({current or '—'}):").grid(
                row=idx, column=0, sticky=tk.W, padx=4, pady=1
            )
            ttk.Entry(self._each_frame, textvariable=var, width=18).grid(
                row=idx, column=1, padx=4, pady=1
            )

        # ===== Reiter: IPv6-Adresse =====
        tab_ipv6 = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_ipv6, self._("camera_settings_ipv6_tab"))
        self._tab_handlers.append((str(tab_ipv6), self._apply_ipv6))
        self._ipv6_mode_var = tk.StringVar(value="auto")
        ttk.Radiobutton(tab_ipv6, text=self._("cs_ipv6_auto"),
                        value="auto", variable=self._ipv6_mode_var,
                        command=self._on_ipv6_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ipv6, text=self._("cs_ipv6_manual"), value="manual",
                        variable=self._ipv6_mode_var,
                        command=self._on_ipv6_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ipv6, text=self._("cs_ipv6_off"), value="off",
                        variable=self._ipv6_mode_var,
                        command=self._on_ipv6_mode_change).pack(anchor=tk.W)

        self._ipv6_addr_var = tk.StringVar()
        self._ipv6_router_var = tk.StringVar()
        self._ipv6_manual = ttk.Frame(tab_ipv6)
        ttk.Label(self._ipv6_manual,
                  text=self._("cs_ipv6_addr_label")).grid(
            row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._ipv6_manual, textvariable=self._ipv6_addr_var, width=40).grid(
            row=0, column=1, padx=4, pady=2)
        ttk.Label(self._ipv6_manual, text=self._("cs_gateway_opt")).grid(
            row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._ipv6_manual, textvariable=self._ipv6_router_var, width=40).grid(
            row=1, column=1, padx=4, pady=2)

        self.ipv6_read_btn = ttk.Button(
            tab_ipv6, text=self._("cs_ipv6_read_btn"),
            command=self._read_ipv6)
        self.ipv6_read_btn.pack(anchor=tk.W, pady=(10, 0))
        ttk.Label(
            tab_ipv6,
            text=self._("cs_ipv6_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(6, 0))

        # ===== Reiter: Zeitzone (Time API, Ersatz fuer Time.POSIXTimeZone) =====
        tab_tz = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_tz, self._("camera_settings_timezone_tab"))
        self._tab_handlers.append((str(tab_tz), self._apply_timezone))
        self.tz_var = tk.StringVar()
        ttk.Label(tab_tz, text=self._("cs_tz_label")).pack(anchor=tk.W)
        tzrow = ttk.Frame(tab_tz)
        tzrow.pack(fill=tk.X, pady=(2, 0))
        self.tz_combo = ttk.Combobox(tzrow, textvariable=self.tz_var,
                                     values=_iana_zones(), width=34)
        self.tz_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.tz_load_btn = ttk.Button(tzrow, text=self._("cs_tz_load_btn"),
                                      command=self._load_timezone)
        self.tz_load_btn.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(
            tab_tz,
            text=self._("cs_tz_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        # ===== Reiter: Benutzer (regulaere Axis-Benutzer) =====
        tab_user = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_user, self._("camera_settings_users_tab"))
        self._tab_handlers.append((str(tab_user), lambda: self._apply_user(onvif=False)))
        self.user_action_var = tk.StringVar(value="add")
        ttk.Radiobutton(tab_user, text=self._("cs_user_add"), value="add",
                        variable=self.user_action_var, command=self._on_user_action).pack(anchor=tk.W)
        ttk.Radiobutton(tab_user, text=self._("cs_user_setpw"), value="setpw",
                        variable=self.user_action_var, command=self._on_user_action).pack(anchor=tk.W)
        uf = ttk.Frame(tab_user)
        uf.pack(fill=tk.X, pady=(6, 0))
        # "root" als Vorschlag fuer den (Erst-)Benutzer; aenderbar.
        self.nu_name_var = tk.StringVar(value="root")
        self.nu_pass_var = tk.StringVar()
        self.nu_role_var = tk.StringVar(value="administrator")
        ttk.Label(uf, text=self._("cs_username")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(uf, textvariable=self.nu_name_var, width=20).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(uf, text=self._("camera_settings_password")).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(uf, textvariable=self.nu_pass_var, width=20, show="*").grid(row=1, column=1, padx=4, pady=2)
        self.nu_role_label = ttk.Label(uf, text=self._("cs_role"))
        self.nu_role_label.grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        self.nu_role_cb = ttk.Combobox(
            uf, textvariable=self.nu_role_var, width=17, state="readonly",
            values=("administrator", "operator", "viewer"),
        )
        self.nu_role_cb.grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Label(
            tab_user,
            text=self._("cs_user_root_hint"),
        ).pack(anchor=tk.W, pady=(6, 0))
        # Manuelle Option, falls die Auto-Erkennung des Auslieferungszustands
        # bei diesem Modell/dieser Firmware nicht greift.
        self.factory_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab_user,
            text=self._("cs_factory_cb"),
            variable=self.factory_var,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            tab_user,
            text=self._("cs_factory_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

        ttk.Separator(tab_user, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 6))
        ttk.Label(tab_user, text=self._("cs_import_users_title"),
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.import_user_btn = ttk.Button(
            tab_user, text=self._("cs_import_btn"),
            command=lambda: self._import_users(onvif=False))
        self.import_user_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_user,
            text=self._("cs_import_users_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # ===== Reiter: ONVIF-Benutzer =====
        tab_onvif = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_onvif, self._("camera_settings_onvif_tab"))
        self._tab_handlers.append((str(tab_onvif), lambda: self._apply_user(onvif=True)))
        self.onv_action_var = tk.StringVar(value="add")
        ttk.Radiobutton(tab_onvif, text=self._("cs_onvif_add"), value="add",
                        variable=self.onv_action_var).pack(anchor=tk.W)
        ttk.Radiobutton(tab_onvif, text=self._("cs_onvif_setpw"), value="setpw",
                        variable=self.onv_action_var).pack(anchor=tk.W)
        of = ttk.Frame(tab_onvif)
        of.pack(fill=tk.X, pady=(6, 0))
        self.onv_name_var = tk.StringVar()
        self.onv_pass_var = tk.StringVar()
        self.onv_level_var = tk.StringVar(value="Administrator")
        ttk.Label(of, text=self._("cs_username")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(of, textvariable=self.onv_name_var, width=20).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(of, text=self._("camera_settings_password")).grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(of, textvariable=self.onv_pass_var, width=20, show="*").grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(of, text=self._("cs_level")).grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            of, textvariable=self.onv_level_var, width=17, state="readonly",
            values=vapix.ONVIF_LEVELS,
        ).grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)

        ttk.Separator(tab_onvif, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 6))
        ttk.Label(tab_onvif,
                  text=self._("cs_import_onvif_title"),
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.import_onvif_btn = ttk.Button(
            tab_onvif, text=self._("cs_import_btn"),
            command=lambda: self._import_users(onvif=True))
        self.import_onvif_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_onvif,
            text=self._("cs_import_onvif_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # ===== Reiter: Firmware =====
        tab_fw = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_fw, self._("camera_settings_firmware_tab"))
        self._tab_handlers.append((str(tab_fw), self._apply_firmware))
        self.fw_path_var = tk.StringVar()
        ff = ttk.Frame(tab_fw)
        ff.pack(fill=tk.X)
        ttk.Label(ff, text=self._("cs_fw_file")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(ff, textvariable=self.fw_path_var, width=46).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(ff, text=self._("cs_browse"), command=self._choose_firmware).grid(
            row=0, column=2, padx=4, pady=2)
        self.fw_factory_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab_fw, text=self._("cs_fw_factory"),
                        variable=self.fw_factory_var).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            tab_fw,
            text=self._("cs_fw_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        # ===== Reiter: Konfiguration (ADM .cfg) =====
        tab_cfg = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_cfg, self._("camera_settings_config_tab"))
        self._tab_handlers.append((str(tab_cfg), self._apply_config))
        self.cfg_path_var = tk.StringVar()
        self._cfg = None  # zuletzt geparste Konfiguration
        cf = ttk.Frame(tab_cfg)
        cf.pack(fill=tk.X)
        ttk.Label(cf, text=self._("cs_cfg_file")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cf, textvariable=self.cfg_path_var, width=46).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(cf, text=self._("cs_browse"), command=self._choose_config).grid(
            row=0, column=2, padx=4, pady=2)
        self.cfg_info_var = tk.StringVar(value=self._("cs_cfg_none"))
        ttk.Label(tab_cfg, textvariable=self.cfg_info_var, wraplength=560,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))
        self.cfg_profiles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab_cfg, text=self._("cs_cfg_profiles"),
                        variable=self.cfg_profiles_var).pack(anchor=tk.W, pady=(6, 0))
        self.cfg_vmd4_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab_cfg, text=self._("cs_cfg_vmd4"),
                        variable=self.cfg_vmd4_var).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            tab_cfg,
            text=self._("cs_cfg_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(tab_cfg, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(12, 8))
        ttk.Label(tab_cfg, text=self._("cs_cfg_export_title"),
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.export_cfg_btn = ttk.Button(
            tab_cfg, text=self._("cs_cfg_export_btn"),
            command=self._read_config)
        self.export_cfg_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_cfg,
            text=self._("cs_cfg_export_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # ===== Reiter: Geraete-Sicherung (Device Configuration API .json) =====
        tab_bk = ttk.Frame(self.nb, padding=8)
        self._add_tab(tab_bk, self._("camera_settings_backup_tab"))
        self._tab_handlers.append((str(tab_bk), self._apply_backup))
        self.backup_path_var = tk.StringVar()
        self._backup_data = None  # zuletzt geladene Sicherung (Ressourcen-Map)
        ttk.Label(tab_bk, text=self._("cs_bk_restore_title"),
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        bf = ttk.Frame(tab_bk)
        bf.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(bf, text=self._("cs_bk_file")).grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(bf, textvariable=self.backup_path_var, width=46).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(bf, text=self._("cs_browse"), command=self._choose_backup).grid(
            row=0, column=2, padx=4, pady=2)
        self.backup_info_var = tk.StringVar(value=self._("cs_bk_none"))
        ttk.Label(tab_bk, textvariable=self.backup_info_var, wraplength=560,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))
        self.backup_importtype_var = tk.StringVar(value="merge")
        ttk.Label(tab_bk, text=self._("cs_bk_importtype")).pack(anchor=tk.W, pady=(6, 0))
        ttk.Radiobutton(tab_bk, text=self._("cs_bk_merge"), value="merge",
                        variable=self.backup_importtype_var).pack(anchor=tk.W)
        ttk.Radiobutton(tab_bk, text=self._("cs_bk_default"), value="default",
                        variable=self.backup_importtype_var).pack(anchor=tk.W)
        ttk.Label(
            tab_bk,
            text=self._("cs_bk_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(tab_bk, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(12, 8))
        ttk.Label(tab_bk, text=self._("cs_bk_download_title"),
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.backup_dl_btn = ttk.Button(
            tab_bk, text=self._("cs_bk_download_btn"),
            command=self._download_backup)
        self.backup_dl_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_bk,
            text=self._("cs_bk_download_help"),
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # --- Buttons ---
        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(6, 4))
        self.test_btn = ttk.Button(btns, text=self._("camera_settings_test_connection"), command=self._test_connection)
        self.test_btn.pack(side=tk.LEFT)
        self.apply_btn = ttk.Button(btns, text=self._("cs_apply"), command=self._apply)
        self.apply_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text=self._("cs_close"), command=self.destroy).pack(side=tk.RIGHT)

        # --- Ergebnisanzeige ---
        ttk.Label(outer, text=self._("cs_result")).pack(anchor=tk.W, pady=(6, 0))
        self.result = scrolledtext.ScrolledText(outer, height=18, wrap=tk.WORD)
        self.result.configure(
            bg=self._palette["tree_bg"], fg=self._palette["fg"],
            insertbackground=self._palette["fg"],
        )
        self.result.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self.result.config(state=tk.DISABLED)

        # Aktive Reiter-Markierung initialisieren (das <<NotebookTabChanged>>
        # feuert beim Aufbau nicht zuverlaessig synchron).
        self._sync_active_tab()
        # Reiter-Ueberlauf erst pruefen, wenn die Groessen feststehen.
        self.after(0, self._update_tab_overflow)

    # ------------------------------------------------- scrollbare Reiter-Leiste
    def _setup_tabless_style(self):
        """Legt einen Notebook-Style ohne sichtbare Reiter an (Reiter kommen in die
        eigene scrollbare Leiste). Der Rumpf erbt vom aktuellen Theme-Notebook."""
        style = ttk.Style(self)
        try:
            style.layout("Tabless.TNotebook", style.layout("TNotebook"))
            style.layout("Tabless.TNotebook.Tab", [])
        except tk.TclError:
            pass

    def _build_tabbar(self, parent):
        """Baut die horizontal scrollbare Reiter-Leiste (Pfeile + Canvas)."""
        self._setup_tabless_style()
        self._active_tab_var = tk.StringVar()
        self._tab_buttons = []
        self._tab_overflow = None

        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(4, 0))
        self._tab_left = ttk.Button(bar, text="‹", width=2,
                                    command=lambda: self._scroll_tabs(-1))
        self._tab_right = ttk.Button(bar, text="›", width=2,
                                     command=lambda: self._scroll_tabs(1))
        self._tabcanvas = tk.Canvas(bar, height=1, highlightthickness=0,
                                    bg=self._palette["bg"])
        self._tabcanvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tabinner = ttk.Frame(self._tabcanvas)
        self._tabcanvas.create_window((0, 0), window=self._tabinner, anchor="nw")
        self._tabinner.bind("<Configure>", self._on_tabinner_configure)
        self._tabcanvas.bind("<Configure>", lambda e: self._update_tab_overflow())
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._tabcanvas.bind(seq, self._on_tab_wheel)
            self._tabinner.bind(seq, self._on_tab_wheel)

    def _add_tab(self, frame, text):
        """Fuegt eine Seite ins tablose Notebook ein und legt den zugehoerigen
        Reiter-Knopf in der scrollbaren Leiste an."""
        btn = ttk.Radiobutton(
            self._tabinner, text=text, value=str(frame),
            variable=self._active_tab_var, style="Toolbutton",
            command=lambda f=frame: self._select_tab(f))
        btn.pack(side=tk.LEFT, padx=1)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            btn.bind(seq, self._on_tab_wheel)
        self._tab_buttons.append(btn)
        self.nb.add(frame, text=text)

    def _select_tab(self, frame):
        """Waehlt eine Seite (loest <<NotebookTabChanged>> -> _sync_active_tab)."""
        self.nb.select(frame)

    def _sync_active_tab(self, event=None):
        """Haelt Knopf-Markierung und Sichtbarkeit mit der aktiven Seite in Sync."""
        try:
            current = self.nb.select()
        except tk.TclError:
            return
        if current:
            self._active_tab_var.set(current)
            self._ensure_tab_visible(current)

    def _on_tabinner_configure(self, event=None):
        self._tabcanvas.configure(scrollregion=self._tabcanvas.bbox("all"))
        h = self._tabinner.winfo_reqheight()
        if h > 1:
            self._tabcanvas.configure(height=h)
        self._update_tab_overflow()

    def _update_tab_overflow(self):
        """Blendet die Scroll-Pfeile nur ein, wenn die Reiter nicht ganz passen."""
        if not hasattr(self, "_tabcanvas"):
            return
        inner_w = self._tabinner.winfo_reqwidth()
        canvas_w = self._tabcanvas.winfo_width()
        overflow = inner_w > canvas_w + 1
        if overflow == self._tab_overflow:
            return
        self._tab_overflow = overflow
        if overflow:
            self._tab_left.pack(side=tk.LEFT, before=self._tabcanvas)
            self._tab_right.pack(side=tk.RIGHT)
        else:
            self._tab_left.pack_forget()
            self._tab_right.pack_forget()
            self._tabcanvas.xview_moveto(0)

    def _scroll_tabs(self, direction):
        self._tabcanvas.xview_scroll(direction * 3, "units")

    def _on_tab_wheel(self, event):
        num = getattr(event, "num", None)
        if num == 4:
            delta = -1
        elif num == 5:
            delta = 1
        else:
            delta = -1 if getattr(event, "delta", 0) > 0 else 1
        self._tabcanvas.xview_scroll(delta * 2, "units")
        return "break"

    def _ensure_tab_visible(self, pathname):
        """Scrollt den aktiven Reiter in den sichtbaren Bereich."""
        if not self._tab_overflow:
            return
        btn = next((b for b in self._tab_buttons
                    if str(b["value"]) == pathname), None)
        if btn is None:
            return
        self._tabcanvas.update_idletasks()
        bx = btn.winfo_x()
        bw = btn.winfo_width()
        inner_w = max(1, self._tabinner.winfo_reqwidth())
        canvas_w = self._tabcanvas.winfo_width()
        view_left = self._tabcanvas.canvasx(0)
        view_right = view_left + canvas_w
        if bx < view_left:
            self._tabcanvas.xview_moveto(bx / inner_w)
        elif bx + bw > view_right:
            self._tabcanvas.xview_moveto(max(0, (bx + bw - canvas_w)) / inner_w)

    def _on_mode_change(self):
        mode = self._mode_var.get()
        for frame in (self._shared, self._range_frame, self._each_frame):
            frame.pack_forget()
        if mode == "range":
            self._range_frame.pack(fill=tk.X, pady=(6, 0))
            self._shared.pack(fill=tk.X, pady=(2, 0))
        elif mode == "each":
            self._each_frame.pack(fill=tk.X, pady=(6, 0))
            self._shared.pack(fill=tk.X, pady=(2, 0))

    # ------------------------------------------------------------- Logging
    def _log(self, text):
        self.result.config(state=tk.NORMAL)
        self.result.insert(tk.END, text + "\n")
        self.result.see(tk.END)
        self.result.config(state=tk.DISABLED)

    def _clear_log(self):
        self.result.config(state=tk.NORMAL)
        self.result.delete("1.0", tk.END)
        self.result.config(state=tk.DISABLED)

    # ---------------------------------------------------------- Hilfsdaten
    def _conn_kwargs(self):
        """Verbindungsparameter aus den Eingabefeldern als Dict."""
        # Sprache im Haupt-Thread auffrischen (Worker lesen danach nur self._lang).
        self._lang = self._app.language_var.get()
        port = self.port_var.get().strip()
        return {
            "username": self.user_var.get(),
            "password": self.pass_var.get(),
            "scheme": self.scheme_var.get(),
            "port": int(port) if port.isdigit() else None,
            "timeout": max(2, self.timeout_var.get()),
        }

    def _set_busy(self, busy):
        self._working = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.test_btn.config(state=state)
        self.apply_btn.config(state=state)
        self.export_cfg_btn.config(state=state)
        self.backup_dl_btn.config(state=state)
        self.import_user_btn.config(state=state)
        self.import_onvif_btn.config(state=state)
        self.ipv6_read_btn.config(state=state)
        self.tz_load_btn.config(state=state)

    # ------------------------------------------------- Verbindung testen
    def _test_connection(self):
        if self._working:
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_test_conn_log"))
        kwargs = self._conn_kwargs()
        threading.Thread(
            target=self._worker_test, args=(kwargs,), daemon=True
        ).start()
        self.after(150, self._poll)

    def _worker_test(self, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            name = cam.get("Name", ip)
            if not ip:
                self._queue.put((name, False, self._("cs_no_ip_known")))
                continue
            try:
                info = vapix.get_device_info(ip, **kwargs)
                self._queue.put((name, True, f"{info['model']} (S/N {info['serial']})"))
            except vapix.VapixError as exc:
                self._queue.put((name, False, str(exc)))
        self._queue.put(None)  # Ende-Marker

    def _on_user_action(self):
        # Rolle nur beim Anlegen relevant; beim Passwortwechsel deaktivieren.
        state = "readonly" if self.user_action_var.get() == "add" else tk.DISABLED
        self.nu_role_cb.config(state=state)

    # --------------------------------------------------------- Anwenden
    def _apply(self):
        if self._working:
            return
        # Dispatch anhand der Reiter-Widget-ID (sprachunabhaengig, robust gegen
        # Reihenfolge/neue Reiter) -- self._tab_handlers wird in _build_ui befuellt.
        current = self.nb.select()
        for widget_id, handler in self._tab_handlers:
            if widget_id == current:
                handler()
                return

    def _apply_ip(self):
        mode = self._mode_var.get()
        # Plausibilitaet pruefen und Zieladressen vorberechnen
        try:
            targets = self._compute_targets(mode)
        except ValueError as exc:
            messagebox.showerror(self._("cs_input_error"), str(exc), parent=self)
            return

        if mode == "dhcp":
            confirm = self._("cs_confirm_dhcp")
        else:
            ips = "\n".join(
                f"  {self.cameras[i].get('Name','?')}: {t}" for i, t in targets.items()
            )
            confirm = self._("cs_confirm_set_ips", ips=ips)
        if not messagebox.askyesno(self._("cs_confirm_change"), confirm, parent=self):
            return

        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_applying", count=len(self.cameras)))
        kwargs = self._conn_kwargs()
        # Tk-Variablen NUR im Haupt-Thread lesen und an den Worker uebergeben
        # (Tkinter ist nicht thread-safe).
        mask = self.mask_var.get().strip()
        gateway = self.gw_var.get().strip()
        threading.Thread(
            target=self._worker_apply, args=(mode, targets, mask, gateway, kwargs),
            daemon=True,
        ).start()
        self.after(150, self._poll)

    def _compute_targets(self, mode):
        """Berechnet die Ziel-IP je Kamera-Index (leer bei DHCP). Wirft ValueError."""
        if mode == "dhcp":
            return {}
        mask = self.mask_var.get().strip()
        if not mask:
            raise ValueError(self._("cs_need_subnet"))
        targets = {}
        if mode == "range":
            start = self.start_ip_var.get().strip()
            if not start:
                raise ValueError(self._("cs_need_start_ip"))
            try:
                for offset in range(len(self.cameras)):
                    targets[offset] = vapix.next_ip(start, offset)
            except ValueError:
                raise ValueError(self._("cs_invalid_start_ip", start=start))
        elif mode == "each":
            for idx in range(len(self.cameras)):
                value = self._ip_entries[idx].get().strip()
                if not value:
                    raise ValueError(
                        self._("cs_need_ip_for", name=self.cameras[idx].get('Name', '?'))
                    )
                targets[idx] = value
        return targets

    def _worker_apply(self, mode, targets, mask, gateway, kwargs):
        for idx, cam in enumerate(self.cameras):
            ip = get_first_ip(cam)
            name = cam.get("Name", ip)
            if not ip:
                self._queue.put((name, False, self._("cs_no_ip_known")))
                continue
            try:
                if mode == "dhcp":
                    vapix.set_dhcp(ip, **kwargs)
                    self._queue.put((name, True, self._("cs_dhcp_ok")))
                else:
                    new_ip = targets[idx]
                    vapix.set_static_ip(ip, new_ip=new_ip, subnet_mask=mask,
                                        gateway=gateway, **kwargs)
                    self._queue.put((name, True, self._("cs_ip_set_ok", ip=new_ip)))
            except vapix.VapixError as exc:
                self._queue.put((name, False, str(exc)))
        self._queue.put(None)

    # ------------------------------------------------------------- IPv6
    def _on_ipv6_mode_change(self):
        if self._ipv6_mode_var.get() == "manual":
            self._ipv6_manual.pack(fill=tk.X, pady=(6, 0), before=self.ipv6_read_btn)
        else:
            self._ipv6_manual.pack_forget()

    def _apply_ipv6(self):
        mode = self._ipv6_mode_var.get()
        address = self._ipv6_addr_var.get().strip()
        router = self._ipv6_router_var.get().strip()
        if mode == "manual" and not address:
            messagebox.showerror(
                self._("cs_input_error"),
                self._("cs_need_ipv6"),
                parent=self)
            return
        summary = {
            "off": self._("cs_ipv6_sum_off"),
            "auto": self._("cs_ipv6_sum_auto"),
            "manual": self._("cs_ipv6_sum_manual", address=address),
        }[mode]
        if not messagebox.askyesno(
                self._("cs_confirm_change"),
                self._("cs_ipv6_confirm", summary=summary, count=len(self.cameras)),
                parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_ipv6_applying", count=len(self.cameras)))
        kwargs = self._conn_kwargs()
        threading.Thread(
            target=self._worker_ipv6, args=(mode, address, router, kwargs),
            daemon=True,
        ).start()
        self.after(150, self._poll)

    def _worker_ipv6(self, mode, address, router, kwargs):
        done = {
            "off": self._("cs_ipv6_done_off"),
            "auto": self._("cs_ipv6_done_auto"),
            "manual": self._("cs_ipv6_done_manual", address=address),
        }[mode]
        for cam in self.cameras:
            ip = get_first_ip(cam)
            name = cam.get("Name", ip)
            if not ip:
                self._queue.put((name, False, self._("cs_no_ip_known")))
                continue
            try:
                vapix.set_ipv6_config(ip, mode=mode, address=address,
                                      router=router, **kwargs)
                self._queue.put((name, True, done))
            except vapix.VapixError as exc:
                self._queue.put((name, False, str(exc)))
        self._queue.put(None)

    def _read_ipv6(self):
        if self._working:
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_ipv6_reading"))
        kwargs = self._conn_kwargs()
        threading.Thread(
            target=self._worker_read_ipv6, args=(kwargs,), daemon=True).start()
        self.after(150, self._poll)

    def _worker_read_ipv6(self, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            name = cam.get("Name", ip)
            if not ip:
                self._queue.put((name, False, self._("cs_no_ip_known")))
                continue
            try:
                cfg = vapix.read_ipv6_config(ip, **kwargs)
                state = self._("cs_ipv6_state_on") if cfg["enabled"] else self._("cs_ipv6_state_off")
                addrs = ", ".join(cfg["addresses"]) or self._("cs_ipv6_none")
                self._queue.put((name, True, self._("cs_ipv6_read_result", state=state, addrs=addrs)))
            except vapix.VapixError as exc:
                self._queue.put((name, False, str(exc)))
        self._queue.put(None)

    # ------------------------------------------- Benutzer / ONVIF-Benutzer
    def _apply_user(self, onvif):
        action = (self.onv_action_var if onvif else self.user_action_var).get()
        name = (self.onv_name_var if onvif else self.nu_name_var).get().strip()
        pwd = (self.onv_pass_var if onvif else self.nu_pass_var).get()
        level = self.onv_level_var.get() if onvif else self.nu_role_var.get()

        if not name:
            messagebox.showerror(self._("cs_input_error"), self._("cs_need_username"), parent=self)
            return
        if not pwd:
            messagebox.showerror(self._("cs_input_error"), self._("cs_need_password"), parent=self)
            return

        kind = self._("cs_kind_onvif") if onvif else self._("cs_kind_user")
        verb = self._("cs_verb_add") if action == "add" else self._("cs_verb_setpw")
        confirm = self._("cs_user_confirm", kind=kind, name=name, verb=verb,
                         count=len(self.cameras))
        if not messagebox.askyesno(self._("cs_confirm_change"), confirm, parent=self):
            return

        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_applying", count=len(self.cameras)))
        kwargs = self._conn_kwargs()
        # Manuell erzwungener Auslieferungszustand (nur fuer regulaere Benutzer)
        factory = self.factory_var.get() and not onvif
        threading.Thread(
            target=self._worker_user,
            args=(onvif, action, name, pwd, level, factory, kwargs), daemon=True,
        ).start()
        self.after(150, self._poll)

    def _factory_call(self, op, base_kwargs):
        """Fuehrt op im Auslieferungszustand aus: erst ohne Anmeldung, dann mit
        gaengigen Standard-Zugangsdaten; nimmt die erste funktionierende Variante.
        """
        attempts = [(self._("cs_factory_no_auth"), "", "", False)]
        for u, p in vapix.DEFAULT_CREDENTIALS:
            attempts.append((f"{u}/{p or self._('cs_factory_empty')}", u, p, True))
        last = None
        for label, u, p, auth in attempts:
            ck = dict(base_kwargs)
            ck["username"] = u
            ck["password"] = p
            try:
                return op(ck, auth) + self._("cs_factory_suffix", label=label)
            except vapix.VapixError as exc:
                last = exc
        raise last if last is not None else vapix.VapixError(self._("cs_no_access"))

    def _worker_user(self, onvif, action, name, pwd, level, factory, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            try:
                if onvif and action == "add":
                    msg = vapix.add_onvif_user(ip, new_user=name, new_password=pwd,
                                               level=level, **kwargs)
                elif onvif:
                    msg = vapix.set_onvif_user_password(ip, target_user=name,
                                                        new_password=pwd, level=level, **kwargs)
                else:
                    # Regulaerer Benutzer: anlegen (im Auslieferungsfall als
                    # Administrator) oder Passwort aendern.
                    if action == "add":
                        eff_role = "administrator" if factory else level

                        def op(ck, auth):
                            try:
                                return vapix.add_user(ip, new_user=name, new_password=pwd,
                                                      role=eff_role, authenticate=auth, **ck)
                            except vapix.VapixError:
                                # Ohne Anmeldung (moderne werksneue Kamera) ist
                                # "anlegen" der einzige Weg -> Fehler weiterreichen.
                                if not auth:
                                    raise
                                # Aeltere Kamera: 'root' existiert bereits ->
                                # stattdessen dessen Passwort setzen.
                                return (vapix.set_user_password(
                                    ip, target_user=name, new_password=pwd,
                                    authenticate=auth, **ck)
                                    + self._("cs_existing_user_pw"))
                    else:
                        def op(ck, auth):
                            return vapix.set_user_password(ip, target_user=name,
                                                           new_password=pwd,
                                                           authenticate=auth, **ck)
                    if factory:
                        msg = self._factory_call(op, kwargs)
                    else:
                        msg = op(kwargs, True)
                self._queue.put((cname, True, msg))
            except vapix.VapixError as exc:
                self._queue.put((cname, False, str(exc)))
        self._queue.put(None)

    # ----------------------------- Stapel-Import aus Textdatei
    def _import_users(self, onvif):
        if self._working:
            return
        path = filedialog.askopenfilename(
            title=self._("cs_choose_user_list"), parent=self,
            filetypes=[(self._("cs_ft_txt"), "*.txt"), (self._("cs_ft_csv"), "*.csv"),
                       (self._("cs_ft_all"), "*.*")],
        )
        if not path:
            return
        try:
            users = vapix.parse_user_list(path, onvif=onvif)
        except vapix.VapixError as exc:
            messagebox.showerror(self._("cs_file_error"), str(exc), parent=self)
            return
        kind = self._("cs_kind_onvif") if onvif else self._("cs_kind_user")
        preview = "\n".join(f"  {u['name']} ({u['role']})" for u in users[:12])
        if len(users) > 12:
            preview += self._("cs_more_users", count=len(users) - 12)
        confirm = self._("cs_import_confirm", count=len(users), kind=kind,
                         cams=len(self.cameras), preview=preview)
        if not messagebox.askyesno(self._("cs_import_confirm_title"), confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        factory = self.factory_var.get() and not onvif
        self._log(self._("cs_importing", count=len(users), kind=kind, cams=len(self.cameras)))
        kwargs = self._conn_kwargs()
        threading.Thread(target=self._worker_import_users,
                         args=(onvif, users, factory, kwargs), daemon=True).start()
        self.after(150, self._poll)

    def _worker_import_users(self, onvif, users, factory, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            for u in users:
                label = f"{cname} / {u['name']}"
                try:
                    if onvif:
                        msg = vapix.add_onvif_user(
                            ip, new_user=u["name"], new_password=u["password"],
                            level=u["role"], **kwargs)
                    else:
                        msg = vapix.add_or_set_user(
                            ip, new_user=u["name"], new_password=u["password"],
                            role=u["role"], factory=factory, **kwargs)
                    self._queue.put((label, True, msg))
                except vapix.VapixError as exc:
                    self._queue.put((label, False, str(exc)))
        self._queue.put(None)

    # --------------------------------------------------------- Firmware
    def _choose_firmware(self):
        path = filedialog.askopenfilename(
            title=self._("cs_choose_fw"), parent=self,
            filetypes=[(self._("cs_ft_fw"), "*.bin"), (self._("cs_ft_all"), "*.*")],
        )
        if path:
            self.fw_path_var.set(path)

    def _apply_firmware(self):
        path = self.fw_path_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror(self._("cs_input_error"), self._("cs_need_fw"),
                                 parent=self)
            return
        confirm = self._("cs_fw_confirm", name=os.path.basename(path),
                         count=len(self.cameras))
        if not messagebox.askyesno(self._("cs_fw_confirm_title"), confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_fw_applying", count=len(self.cameras)))
        conn = self._conn_kwargs()
        conn["timeout"] = 600  # Firmware-Upload braucht deutlich laenger
        factory = self.fw_factory_var.get()
        threading.Thread(
            target=self._worker_firmware, args=(path, factory, conn), daemon=True,
        ).start()
        self.after(150, self._poll)

    def _worker_firmware(self, path, factory, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            try:
                msg = vapix.upgrade_firmware(ip, firmware_path=path,
                                             factory_default=factory, **kwargs)
                self._queue.put((cname, True, msg))
            except vapix.VapixError as exc:
                self._queue.put((cname, False, str(exc)))
        self._queue.put(None)

    # ----------------------------------------------- ADM-Konfiguration
    def _choose_config(self):
        path = filedialog.askopenfilename(
            title=self._("cs_choose_cfg"), parent=self,
            filetypes=[(self._("cs_ft_cfg"), "*.cfg"), (self._("cs_ft_all"), "*.*")],
        )
        if not path:
            return
        self.cfg_path_var.set(path)
        try:
            self._cfg = vapix.parse_adm_config(path)
            vmd4_note = (self._("cs_cfg_vmd4_note")
                         if self._cfg.get("vmd4") is not None else "")
            self.cfg_info_var.set(self._(
                "cs_cfg_info",
                model=self._cfg['model'] or '?',
                fw=self._cfg['firmware'] or '?',
                params=len(self._cfg['parameters']),
                profiles=len(self._cfg['profiles']),
                vmd=vmd4_note,
            ))
        except vapix.VapixError as exc:
            self._cfg = None
            self.cfg_info_var.set(self._("cs_cfg_parse_error", exc=exc))

    def _apply_config(self):
        if self._cfg is None:
            messagebox.showerror(self._("cs_input_error"),
                                 self._("cs_need_cfg"),
                                 parent=self)
            return
        confirm = self._("cs_cfg_confirm", model=self._cfg['model'] or '?',
                         params=len(self._cfg['parameters']), count=len(self.cameras))
        if not messagebox.askyesno(self._("cs_cfg_confirm_title"), confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_cfg_applying", count=len(self.cameras)))
        conn = self._conn_kwargs()
        conn["timeout"] = max(30, conn["timeout"])
        cfg = self._cfg
        with_profiles = self.cfg_profiles_var.get()
        with_vmd4 = self.cfg_vmd4_var.get()
        threading.Thread(target=self._worker_config,
                         args=(cfg, with_profiles, with_vmd4, conn),
                         daemon=True).start()
        self.after(150, self._poll)

    def _worker_config(self, cfg, with_profiles, with_vmd4, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            try:
                msg = vapix.apply_adm_config(ip, config=cfg, with_profiles=with_profiles,
                                             with_vmd4=with_vmd4, **kwargs)
                self._queue.put((cname, True, msg))
            except vapix.VapixError as exc:
                self._queue.put((cname, False, str(exc)))
        self._queue.put(None)

    # ------------------------ Konfiguration aus Kamera auslesen
    def _read_config(self):
        if self._working:
            return
        if not self.cameras:
            messagebox.showerror(self._("cs_no_camera_title"), self._("cs_no_camera"), parent=self)
            return
        cam = self.cameras[0]
        ip = get_first_ip(cam)
        name = cam.get("Name", ip)
        if not ip:
            messagebox.showerror(self._("cs_no_ip_title"),
                                 self._("cs_no_ip_for", name=name), parent=self)
            return
        self._clear_log()
        self._set_busy(True)
        if len(self.cameras) > 1:
            self._log(self._("cs_read_only_first", name=name))
        self._log(self._("cs_reading_cfg", name=name, ip=ip))
        kwargs = self._conn_kwargs()
        kwargs["timeout"] = max(30, kwargs["timeout"])
        self._read_q = queue.Queue()
        threading.Thread(target=self._worker_read_config,
                         args=(ip, name, kwargs), daemon=True).start()
        self.after(150, self._poll_read)

    def _worker_read_config(self, ip, name, kwargs):
        try:
            cfg = vapix.read_device_config(ip, **kwargs)
            self._read_q.put(("ok", name, cfg))
        except vapix.VapixError as exc:
            self._read_q.put(("err", name, str(exc)))

    def _poll_read(self):
        try:
            kind, name, payload = self._read_q.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_read)
            return
        self._set_busy(False)
        if kind == "err":
            self._log(self._("cs_log_error", name=name, msg=payload))
            return
        cfg = payload
        vmd4_note = (self._("cs_cfg_vmd4_note2")
                     if cfg.get("vmd4") is not None else "")
        self._log(self._("cs_read_ok", name=name, params=len(cfg['parameters']),
                         profiles=len(cfg['profiles']), vmd=vmd4_note))
        ParameterSelectDialog(self, cfg, name, self._palette)

    # ------------------------ Geraete-Sicherung: einspielen (Restore)
    def _choose_backup(self):
        path = filedialog.askopenfilename(
            title=self._("cs_bk_choose"), parent=self,
            filetypes=[(self._("cs_ft_json"), "*.json"), (self._("cs_ft_all"), "*.*")],
        )
        if not path:
            return
        self.backup_path_var.set(path)
        try:
            self._backup_data = vapix.load_device_settings_backup(path)
            keys = ", ".join(sorted(self._backup_data))
            self.backup_info_var.set(self._(
                "cs_bk_info", n=len(self._backup_data), keys=keys))
        except vapix.VapixError as exc:
            self._backup_data = None
            self.backup_info_var.set(self._("cs_bk_parse_error", exc=exc))

    def _apply_backup(self):
        if self._backup_data is None:
            messagebox.showerror(self._("cs_input_error"),
                                 self._("cs_bk_need_file"), parent=self)
            return
        confirm = self._("cs_bk_restore_confirm", count=len(self.cameras))
        if not messagebox.askyesno(self._("cs_bk_restore_confirm_title"),
                                   confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_bk_restoring", count=len(self.cameras)))
        conn = self._conn_kwargs()
        conn["timeout"] = max(60, conn["timeout"])
        data = self._backup_data
        import_type = self.backup_importtype_var.get()
        threading.Thread(target=self._worker_backup_restore,
                         args=(data, import_type, conn), daemon=True).start()
        self.after(150, self._poll)

    def _worker_backup_restore(self, data, import_type, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            try:
                n = vapix.import_device_settings(
                    ip, data=data, import_type=import_type, **kwargs)
                self._queue.put((cname, True, self._("cs_bk_restore_ok", n=n)))
            except vapix.VapixError as exc:
                self._queue.put((cname, False, str(exc)))
        self._queue.put(None)

    # ------------------------ Geraete-Sicherung: herunterladen (Download)
    def _download_backup(self):
        if self._working:
            return
        if not self.cameras:
            messagebox.showerror(self._("cs_no_camera_title"),
                                 self._("cs_no_camera"), parent=self)
            return
        cam = self.cameras[0]
        ip = get_first_ip(cam)
        name = cam.get("Name", ip)
        if not ip:
            messagebox.showerror(self._("cs_no_ip_title"),
                                 self._("cs_no_ip_for", name=name), parent=self)
            return
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_") or "kamera"
        path = filedialog.asksaveasfilename(
            title=self._("cs_bk_save_as"), parent=self, defaultextension=".json",
            initialfile=f"device_setting_{safe}.json",
            filetypes=[(self._("cs_ft_json"), "*.json"), (self._("cs_ft_all"), "*.*")],
        )
        if not path:
            return
        self._clear_log()
        self._set_busy(True)
        if len(self.cameras) > 1:
            self._log(self._("cs_read_only_first", name=name))
        self._log(self._("cs_bk_saving", name=name, ip=ip))
        kwargs = self._conn_kwargs()
        kwargs["timeout"] = max(60, kwargs["timeout"])
        self._backup_q = queue.Queue()
        threading.Thread(target=self._worker_backup_download,
                         args=(ip, name, path, kwargs), daemon=True).start()
        self.after(150, self._poll_backup)

    def _worker_backup_download(self, ip, name, path, kwargs):
        try:
            n = vapix.save_device_settings(ip, path=path, **kwargs)
            self._backup_q.put(("ok", name, (path, n)))
        except vapix.VapixError as exc:
            self._backup_q.put(("err", name, str(exc)))

    def _poll_backup(self):
        try:
            kind, name, payload = self._backup_q.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_backup)
            return
        self._set_busy(False)
        if kind == "err":
            self._log(self._("cs_log_error", name=name, msg=payload))
            return
        path, n = payload
        self._log(self._("cs_bk_save_ok", path=path, n=n))

    # ------------------------ Zeitzone (Time API)
    def _apply_timezone(self):
        tz = self.tz_var.get().strip()
        if not tz:
            messagebox.showerror(self._("cs_input_error"),
                                 self._("cs_tz_need"), parent=self)
            return
        self._clear_log()
        self._set_busy(True)
        self._log(self._("cs_tz_applying", tz=tz, count=len(self.cameras)))
        conn = self._conn_kwargs()
        threading.Thread(target=self._worker_timezone, args=(tz, conn),
                         daemon=True).start()
        self.after(150, self._poll)

    def _worker_timezone(self, tz, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, self._("cs_no_ip_known")))
                continue
            try:
                msg = vapix.set_timezone(ip, timezone=tz, **kwargs)
                self._queue.put((cname, True, msg))
            except vapix.VapixError as exc:
                self._queue.put((cname, False, str(exc)))
        self._queue.put(None)

    def _load_timezone(self):
        if self._working:
            return
        if not self.cameras:
            messagebox.showerror(self._("cs_no_camera_title"),
                                 self._("cs_no_camera"), parent=self)
            return
        cam = self.cameras[0]
        ip = get_first_ip(cam)
        name = cam.get("Name", ip)
        if not ip:
            messagebox.showerror(self._("cs_no_ip_title"),
                                 self._("cs_no_ip_for", name=name), parent=self)
            return
        self._clear_log()
        self._set_busy(True)
        if len(self.cameras) > 1:
            self._log(self._("cs_read_only_first", name=name))
        self._log(self._("cs_tz_reading", name=name, ip=ip))
        kwargs = self._conn_kwargs()
        self._tz_q = queue.Queue()
        threading.Thread(target=self._worker_load_timezone,
                         args=(ip, name, kwargs), daemon=True).start()
        self.after(150, self._poll_tz)

    def _worker_load_timezone(self, ip, name, kwargs):
        try:
            data = vapix.get_time_settings(ip, **kwargs)
            self._tz_q.put(("ok", name, data))
        except vapix.VapixError as exc:
            self._tz_q.put(("err", name, str(exc)))

    def _poll_tz(self):
        try:
            kind, name, payload = self._tz_q.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_tz)
            return
        self._set_busy(False)
        if kind == "err":
            self._log(self._("cs_log_error", name=name, msg=payload))
            return
        data = payload if isinstance(payload, dict) else {}
        zones = data.get("timeZones") or []
        if zones:
            self.tz_combo.config(values=sorted(zones))
        current = data.get("timeZone") or ""
        if current:
            self.tz_var.set(current)
        self._log(self._("cs_tz_current", name=name,
                         tz=current or self._("cs_tz_unknown")))

    def _poll(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._set_busy(False)
                    self._log(self._("cs_done"))
                    return
                name, ok, msg = item
                status = self._("cs_log_ok") if ok else self._("cs_log_fail")
                self._log(self._("cs_log_line", status=status, name=name, msg=msg))
        except queue.Empty:
            self.after(150, self._poll)


class ParameterSelectDialog(tk.Toplevel):
    """Auswahl- und Suchdialog fuer den Konfigurations-Export.

    Zeigt die ausgelesene Parameterliste einer Kamera, laesst die zu
    speichernden Parameter per Klick-Haken (an-/abwaehlen) markieren und ueber
    ein Suchfeld filtern, und schreibt die Auswahl ueber vapix.write_adm_config
    als ADM-.cfg. Die Auswahl bleibt beim Filtern erhalten (separat in
    self._selected gehalten).
    """

    CHECK = "X"

    def __init__(self, master, config, cam_name, palette):
        super().__init__(master)
        # Sprache vom oeffnenden CameraSettingsDialog uebernehmen (reiner String).
        self._lang = getattr(master, "_lang", "de")
        self.title(self._("ps_title"))
        self.geometry("680x680")
        self.minsize(560, 480)
        self.transient(master)
        self.configure(bg=palette["bg"])
        self._palette = palette
        self._config = config
        self._cam_name = cam_name
        self._all_names = sorted(config.get("parameters", {}))
        self._selected = set(self._all_names)  # Standard: alles ausgewaehlt
        self._build_ui()
        self._refilter()

    def _(self, key, **kwargs):
        """Uebersetzt anhand der gecachten Sprache (self._lang), ohne Tk-Zugriff."""
        text = TRANSLATIONS.get(self._lang, {}).get(key, key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return text

    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text=self._("ps_header", cam=self._cam_name,
                        model=self._config.get('model') or '?',
                        fw=self._config.get('firmware') or '?'),
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(outer, text=self._("ps_count_read", count=len(self._all_names))).pack(
            anchor=tk.W, pady=(0, 6))

        sf = ttk.Frame(outer)
        sf.pack(fill=tk.X)
        ttk.Label(sf, text=self._("ps_search")).pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refilter())
        ttk.Entry(sf, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        tf = ttk.Frame(outer)
        tf.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tf, columns=("chk", "name", "value"),
                                 show="headings", selectmode="none")
        self.tree.heading("chk", text="")
        self.tree.heading("name", text=self._("ps_col_param"))
        self.tree.heading("value", text=self._("ps_col_value"))
        self.tree.column("chk", width=32, anchor=tk.CENTER, stretch=tk.NO)
        self.tree.column("name", width=340, stretch=tk.NO)
        self.tree.column("value", width=260)
        vsb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self._on_click)

        cf = ttk.Frame(outer)
        cf.pack(fill=tk.X, pady=(6, 0))
        self._count_var = tk.StringVar()
        ttk.Label(cf, textvariable=self._count_var).pack(side=tk.LEFT)
        ttk.Button(cf, text=self._("ps_all_filtered"),
                   command=lambda: self._set_filtered(True)).pack(side=tk.RIGHT)
        ttk.Button(cf, text=self._("ps_none_filtered"),
                   command=lambda: self._set_filtered(False)).pack(side=tk.RIGHT, padx=(0, 4))

        self._profiles_var = tk.BooleanVar(value=bool(self._config.get("profiles")))
        ttk.Checkbutton(
            outer,
            text=self._("ps_incl_profiles", count=len(self._config.get('profiles', []))),
            variable=self._profiles_var,
        ).pack(anchor=tk.W, pady=(6, 0))

        has_vmd4 = self._config.get("vmd4") is not None
        self._vmd4_var = tk.BooleanVar(value=has_vmd4)
        cb_vmd4 = ttk.Checkbutton(
            outer,
            text=self._("ps_incl_vmd4")
                 + ("" if has_vmd4 else self._("ps_not_available")),
            variable=self._vmd4_var,
        )
        if not has_vmd4:
            cb_vmd4.state(["disabled"])
        cb_vmd4.pack(anchor=tk.W, pady=(2, 0))

        bf = ttk.Frame(outer)
        bf.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(bf, text=self._("ps_save"), command=self._save).pack(side=tk.LEFT)
        ttk.Button(bf, text=self._("ps_cancel"), command=self.destroy).pack(side=tk.RIGHT)

    def _filtered_names(self):
        term = self._search_var.get().strip().lower()
        if not term:
            return self._all_names
        params = self._config["parameters"]
        return [n for n in self._all_names
                if term in n.lower() or term in params[n].lower()]

    def _refilter(self):
        self.tree.delete(*self.tree.get_children())
        params = self._config["parameters"]
        for name in self._filtered_names():
            value = params[name]
            if len(value) > 90:
                value = value[:87] + "..."
            glyph = self.CHECK if name in self._selected else ""
            self.tree.insert("", tk.END, iid=name, values=(glyph, name, value))
        self._update_count()

    def _update_count(self):
        self._count_var.set(
            self._("ps_selected_count", sel=len(self._selected), total=len(self._all_names)))

    def _on_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row in self._selected:
            self._selected.discard(row)
            self.tree.set(row, "chk", "")
        else:
            self._selected.add(row)
            self.tree.set(row, "chk", self.CHECK)
        self._update_count()

    def _set_filtered(self, on):
        for name in self._filtered_names():
            if on:
                self._selected.add(name)
            else:
                self._selected.discard(name)
        self._refilter()

    def _save(self):
        if not self._selected:
            messagebox.showerror(self._("ps_nothing_title"),
                                 self._("ps_nothing"),
                                 parent=self)
            return
        default = (self._config.get("model") or "konfiguration").replace(" ", "_") + ".cfg"
        path = filedialog.asksaveasfilename(
            title=self._("ps_save_title"), parent=self,
            defaultextension=".cfg", initialfile=default,
            filetypes=[(self._("cs_ft_cfg"), "*.cfg"), (self._("cs_ft_all"), "*.*")],
        )
        if not path:
            return
        with_profiles = self._profiles_var.get()
        with_vmd4 = self._vmd4_var.get()
        try:
            n = vapix.write_adm_config(path, self._config,
                                       selected_params=self._selected,
                                       with_profiles=with_profiles,
                                       with_vmd4=with_vmd4)
        except vapix.VapixError as exc:
            messagebox.showerror(self._("ps_save_error"), str(exc), parent=self)
            return
        extra = (self._("ps_extra_profiles", count=len(self._config.get('profiles', [])))
                 if with_profiles else "")
        if with_vmd4 and self._config.get("vmd4") is not None:
            extra += self._("ps_extra_vmd4")
        messagebox.showinfo(self._("ps_saved_title"),
                            self._("ps_saved", count=n, extra=extra, path=path), parent=self)
        self.destroy()


def main():
    app = AxisDiscoveryGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
