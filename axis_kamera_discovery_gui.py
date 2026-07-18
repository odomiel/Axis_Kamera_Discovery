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

import json
import os
import platform
import queue
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
}

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
        "label_duration": "Dauer (s):",
        "label_every": "alle (s):",
        "btn_autorefresh": "Auto-Refresh",
        "btn_export": "Exportieren...",
        "btn_camera_settings": "Kamera Einstellungen",
        "btn_settings": "Einstellungen",
        
        # Einstellungen-Menü
        "menu_dark_mode": "Dark Mode",
        "menu_columns": "Spalten...",
        "menu_language": "Sprache",
        "menu_language_de": "Deutsch",
        "menu_language_en": "Englisch",
        "menu_info": "Info",
        "menu_help": "Hilfe",
        "menu_licenses": "Lizenzen",
        
        # Disclaimer
        "disclaimer": "Nutzung des Programms auf eigene Gefahr",
        
        # Spalten-Dialog
        "columns_dialog_title": "Spalten",
        "columns_dialog_label": "Sichtbare Spalten:",
        "btn_close": "Schliessen",
        
        # Info-Dialog
        "info_title": "Info",
        
        # Hilfe-Dialog
        "help_title": "Hilfe",
        
        # Lizenzen-Dialog
        "licenses_title": "Lizenzen",
        
        # Kamera Einstellungen Dialog
        "camera_settings_title": "Kamera Einstellungen",
        "camera_settings_cameras_selected": "{} Kamera(s) ausgewaehlt",
        "camera_settings_credentials": "Zugangsdaten",
        "camera_settings_user": "Benutzer:",
        "camera_settings_password": "Passwort:",
        "camera_settings_connection": "Verbindung:",
        "camera_settings_port": "Port (optional):",
        "camera_settings_timeout": "Timeout (s):",
        "camera_settings_test_connection": "Verbindung testen",
        "camera_settings_ip_tab": "IP-Adresse",
        "camera_settings_users_tab": "Benutzer",
        "camera_settings_onvif_tab": "ONVIF-Benutzer",
        "camera_settings_firmware_tab": "Firmware",
        "camera_settings_config_tab": "Konfiguration",
        
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
        "col_Port": "Port",
        "col_Hostname": "Hostname",
        "col_MAC-Adresse/Seriennummer": "MAC-Adresse/Seriennummer",
    },
    "en": {
        # GUI-Titel und Fenster
        "window_title": "Axis Camera Discovery",
        
        # Toolbar
        "btn_search": "Search",
        "label_duration": "Duration (s):",
        "label_every": "every (s):",
        "btn_autorefresh": "Auto-Refresh",
        "btn_export": "Export...",
        "btn_camera_settings": "Camera Settings",
        "btn_settings": "Settings",
        
        # Einstellungen-Menü
        "menu_dark_mode": "Dark Mode",
        "menu_columns": "Columns...",
        "menu_language": "Language",
        "menu_language_de": "German",
        "menu_language_en": "English",
        "menu_info": "Info",
        "menu_help": "Help",
        "menu_licenses": "Licenses",
        
        # Disclaimer
        "disclaimer": "Use at your own risk",
        
        # Spalten-Dialog
        "columns_dialog_title": "Columns",
        "columns_dialog_label": "Visible columns:",
        "btn_close": "Close",
        
        # Info-Dialog
        "info_title": "Info",
        
        # Hilfe-Dialog
        "help_title": "Help",
        
        # Lizenzen-Dialog
        "licenses_title": "Licenses",
        
        # Kamera Einstellungen Dialog
        "camera_settings_title": "Camera Settings",
        "camera_settings_cameras_selected": "{} camera(s) selected",
        "camera_settings_credentials": "Credentials",
        "camera_settings_user": "User:",
        "camera_settings_password": "Password:",
        "camera_settings_connection": "Connection:",
        "camera_settings_port": "Port (optional):",
        "camera_settings_timeout": "Timeout (s):",
        "camera_settings_test_connection": "Test Connection",
        "camera_settings_ip_tab": "IP Address",
        "camera_settings_users_tab": "Users",
        "camera_settings_onvif_tab": "ONVIF Users",
        "camera_settings_firmware_tab": "Firmware",
        "camera_settings_config_tab": "Configuration",
        
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

    def _update_language_menu(self, *args):
        """Aktualisiert den Text des Sprach-Menübuttons nach Sprachwechsel."""
        self.lang_menu_btn.config(text=self._("menu_language"))

    def _update_all_texts(self):
        """Aktualisiert alle UI-Texte nach Sprachwechsel."""
        # Fenster-Titel
        self.title(self._("window_title") + f" {__version__}")
        
        # Toolbar
        self.search_btn.config(text=self._("btn_search"))
        self.duration_label.config(text=self._("label_duration"))
        self.autorefresh_cb.config(text=self._("btn_autorefresh"))
        self.every_label.config(text=self._("label_every"))
        self.export_btn.config(text=self._("btn_export"))
        self.camera_settings_btn.config(text=self._("btn_camera_settings"))
        self.settings_btn.config(text=self._("btn_settings"))
        self.disclaimer_btn.config(text=self._("disclaimer"))
        
        # Sprach-Menübutton
        if hasattr(self, "lang_menu_btn"):
            self.lang_menu_btn.config(text=self._("menu_language"))
        
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
                import re
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

        self.search_btn = ttk.Button(bar, text=self._("btn_search"), command=self.start_search)
        self.search_btn.pack(side=tk.LEFT)

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
        self._autosize_columns()  # Breiten an die neuen Inhalte anpassen

        if self.cameras:
            self.export_btn.config(state=tk.NORMAL)
            self.status_var.set(self._("status_found", count=len(self.cameras)))
        else:
            self.status_var.set(self._("status_no_axis_cameras"))

        self._schedule_refresh()  # naechsten Auto-Refresh planen (falls aktiviert)

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
        
        # Aktualisiere Menü-Text wenn Sprache geändert wird
        self.language_var.trace_add("write", self._update_language_menu)
        
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X)

        for label_key, command in (
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
            "Info",
            "Axis_Kamera_Discovery\n"
            f"Version {__version__}\n\n"
            "Findet Axis-Kameras im lokalen Netzwerk per Zeroconf/mDNS.\n\n"
            "Komponenten:\n"
            f"{self._component_versions()}\n\n"
            "Lizenz: GPL-3.0-or-later\n"
            "Copyright (C) 2026 Mirik\n"
            "Co-Autor: Claude Opus 4.8 (Anthropic) - KI-gestuetzte Entwicklung",
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
        self._show_text_window("README.md", "Hilfe - README")

    def _show_licenses(self):
        self._show_text_window("THIRD_PARTY_LICENSES.md", "Lizenzen")

    def _show_text_window(self, filename, title):
        # Unter PyInstaller liegen gebundelte Datendateien in sys._MEIPASS,
        # sonst neben diesem Modul (AppImage/Quellcode).
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, filename)
        if not os.path.exists(path):
            messagebox.showerror(title, f"{filename} wurde nicht gefunden.")
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
                "Kamera Einstellungen",
                "Bitte zuerst eine oder mehrere Kameras in der Liste auswaehlen.",
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
        self.title("Kamera Einstellungen")
        self.geometry("720x780")
        self.minsize(720, 600)
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
        self._on_user_action()   # Rollen-Feld je nach Benutzer-Aktion schalten

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            text=f"{len(self.cameras)} Kamera(s) ausgewaehlt",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W)

        # --- Zugangsdaten ---
        cred = ttk.LabelFrame(outer, text="Zugangsdaten", padding=8)
        cred.pack(fill=tk.X, pady=(8, 4))
        self.user_var = tk.StringVar(value="root")
        self.pass_var = tk.StringVar()
        self.scheme_var = tk.StringVar(value="auto")
        self.port_var = tk.StringVar()
        self.timeout_var = tk.IntVar(value=10)

        ttk.Label(cred, text="Benutzer:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.user_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(cred, text="Passwort:").grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.pass_var, width=18, show="*").grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(cred, text="Verbindung:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            cred, textvariable=self.scheme_var, width=15, state="readonly",
            values=("auto", "https", "http"),
        ).grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(cred, text="Port (optional):").grid(row=1, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cred, textvariable=self.port_var, width=18).grid(row=1, column=3, padx=4, pady=2)
        ttk.Label(cred, text="Timeout (s):").grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Spinbox(cred, from_=2, to=120, width=6, textvariable=self.timeout_var).grid(
            row=2, column=1, sticky=tk.W, padx=4, pady=2
        )

        # --- Aktionen in Reitern ---
        self.nb = ttk.Notebook(outer)
        self.nb.pack(fill=tk.X, pady=4)

        # ===== Reiter: IP-Adresse =====
        tab_ip = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab_ip, text="IP-Adresse")
        ttk.Radiobutton(tab_ip, text="Auf DHCP umstellen", value="dhcp",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ip, text="Feste IP ab Start-IP fortlaufend", value="range",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Radiobutton(tab_ip, text="Pro Kamera einzeln", value="each",
                        variable=self._mode_var, command=self._on_mode_change).pack(anchor=tk.W)

        # gemeinsame Felder Maske/Gateway (fuer "range" und "each")
        self.mask_var = tk.StringVar(value="255.255.255.0")
        self.gw_var = tk.StringVar()
        self.start_ip_var = tk.StringVar()

        self._shared = ttk.Frame(tab_ip)
        ttk.Label(self._shared, text="Subnetzmaske:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._shared, textvariable=self.mask_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(self._shared, text="Gateway (optional):").grid(row=0, column=2, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._shared, textvariable=self.gw_var, width=18).grid(row=0, column=3, padx=4, pady=2)

        self._range_frame = ttk.Frame(tab_ip)
        ttk.Label(self._range_frame, text="Start-IP:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(self._range_frame, textvariable=self.start_ip_var, width=18).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(
            self._range_frame,
            text="(wird fortlaufend an die Kameras in Listenreihenfolge vergeben)",
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

        # ===== Reiter: Benutzer (regulaere Axis-Benutzer) =====
        tab_user = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab_user, text="Benutzer")
        self.user_action_var = tk.StringVar(value="add")
        ttk.Radiobutton(tab_user, text="Benutzer anlegen", value="add",
                        variable=self.user_action_var, command=self._on_user_action).pack(anchor=tk.W)
        ttk.Radiobutton(tab_user, text="Passwort aendern", value="setpw",
                        variable=self.user_action_var, command=self._on_user_action).pack(anchor=tk.W)
        uf = ttk.Frame(tab_user)
        uf.pack(fill=tk.X, pady=(6, 0))
        # "root" als Vorschlag fuer den (Erst-)Benutzer; aenderbar.
        self.nu_name_var = tk.StringVar(value="root")
        self.nu_pass_var = tk.StringVar()
        self.nu_role_var = tk.StringVar(value="administrator")
        ttk.Label(uf, text="Benutzername:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(uf, textvariable=self.nu_name_var, width=20).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(uf, text="Passwort:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(uf, textvariable=self.nu_pass_var, width=20, show="*").grid(row=1, column=1, padx=4, pady=2)
        self.nu_role_label = ttk.Label(uf, text="Rolle:")
        self.nu_role_label.grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        self.nu_role_cb = ttk.Combobox(
            uf, textvariable=self.nu_role_var, width=17, state="readonly",
            values=("administrator", "operator", "viewer"),
        )
        self.nu_role_cb.grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)
        ttk.Label(
            tab_user,
            text="Hinweis: 'root' ist der uebliche Erstbenutzer (Administrator).",
        ).pack(anchor=tk.W, pady=(6, 0))
        # Manuelle Option, falls die Auto-Erkennung des Auslieferungszustands
        # bei diesem Modell/dieser Firmware nicht greift.
        self.factory_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab_user,
            text="Auslieferungszustand (Standard-Zugangsdaten/ohne Anmeldung probieren; Anlegen als Administrator)",
            variable=self.factory_var,
        ).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            tab_user,
            text="Ersteinstellung: \"Auslieferungszustand\" anhaken und \"Benutzer "
            "anlegen\" mit Benutzer 'root' + Passwort. Funktioniert fuer moderne "
            "Kameras (legt den Erstadmin an) wie aeltere (z. B. M7001: setzt das "
            "Passwort des vorhandenen 'root').",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

        ttk.Separator(tab_user, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 6))
        ttk.Label(tab_user, text="Stapel-Import aus Textdatei (mehrere Benutzer anlegen):",
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.import_user_btn = ttk.Button(
            tab_user, text="Benutzerliste waehlen und anlegen...",
            command=lambda: self._import_users(onvif=False))
        self.import_user_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_user,
            text="Eine Zeile je Benutzer: Name,Passwort,Rolle - Rolle optional "
            "(Standard: viewer), gueltig: administrator/operator/viewer. Passwoerter "
            "mit Komma in \"...\" setzen; Zeilen mit '#' sind Kommentare. Der oben "
            "gewaehlte 'Auslieferungszustand' gilt auch fuer den Import (legt als "
            "Administrator an).",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # ===== Reiter: ONVIF-Benutzer =====
        tab_onvif = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab_onvif, text="ONVIF-Benutzer")
        self.onv_action_var = tk.StringVar(value="add")
        ttk.Radiobutton(tab_onvif, text="ONVIF-Benutzer anlegen", value="add",
                        variable=self.onv_action_var).pack(anchor=tk.W)
        ttk.Radiobutton(tab_onvif, text="Passwort aendern", value="setpw",
                        variable=self.onv_action_var).pack(anchor=tk.W)
        of = ttk.Frame(tab_onvif)
        of.pack(fill=tk.X, pady=(6, 0))
        self.onv_name_var = tk.StringVar()
        self.onv_pass_var = tk.StringVar()
        self.onv_level_var = tk.StringVar(value="Administrator")
        ttk.Label(of, text="Benutzername:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(of, textvariable=self.onv_name_var, width=20).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(of, text="Passwort:").grid(row=1, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(of, textvariable=self.onv_pass_var, width=20, show="*").grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(of, text="Stufe:").grid(row=2, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Combobox(
            of, textvariable=self.onv_level_var, width=17, state="readonly",
            values=vapix.ONVIF_LEVELS,
        ).grid(row=2, column=1, sticky=tk.W, padx=4, pady=2)

        ttk.Separator(tab_onvif, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(10, 6))
        ttk.Label(tab_onvif,
                  text="Stapel-Import aus Textdatei (mehrere ONVIF-Benutzer anlegen):",
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.import_onvif_btn = ttk.Button(
            tab_onvif, text="Benutzerliste waehlen und anlegen...",
            command=lambda: self._import_users(onvif=True))
        self.import_onvif_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_onvif,
            text="Eine Zeile je Benutzer: Name,Passwort,Stufe - Stufe optional "
            "(Standard: User), gueltig: Administrator/Operator/User. Passwoerter "
            "mit Komma in \"...\" setzen; Zeilen mit '#' sind Kommentare.",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # ===== Reiter: Firmware =====
        tab_fw = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab_fw, text="Firmware")
        self.fw_path_var = tk.StringVar()
        ff = ttk.Frame(tab_fw)
        ff.pack(fill=tk.X)
        ttk.Label(ff, text="Firmware-Datei:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(ff, textvariable=self.fw_path_var, width=46).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(ff, text="Durchsuchen...", command=self._choose_firmware).grid(
            row=0, column=2, padx=4, pady=2)
        self.fw_factory_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab_fw, text="Werkseinstellungen beim Update (factory default)",
                        variable=self.fw_factory_var).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            tab_fw,
            text="Achtung: Die Firmware muss zum Kameramodell passen. Sie wird auf "
            "ALLE markierten Kameras gespielt - nur Kameras gleichen Modells "
            "auswaehlen. Der Vorgang dauert einige Minuten; die Kamera startet "
            "danach neu.",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        # ===== Reiter: Konfiguration (ADM .cfg) =====
        tab_cfg = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab_cfg, text="Konfiguration")
        self.cfg_path_var = tk.StringVar()
        self._cfg = None  # zuletzt geparste Konfiguration
        cf = ttk.Frame(tab_cfg)
        cf.pack(fill=tk.X)
        ttk.Label(cf, text="ADM-Konfig (.cfg):").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(cf, textvariable=self.cfg_path_var, width=46).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(cf, text="Durchsuchen...", command=self._choose_config).grid(
            row=0, column=2, padx=4, pady=2)
        self.cfg_info_var = tk.StringVar(value="Keine Datei gewaehlt.")
        ttk.Label(tab_cfg, textvariable=self.cfg_info_var, wraplength=560,
                  justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))
        self.cfg_profiles_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab_cfg, text="Stream-Profile mit uebernehmen",
                        variable=self.cfg_profiles_var).pack(anchor=tk.W, pady=(6, 0))
        self.cfg_vmd4_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab_cfg, text="Bewegungserkennung (VMD4) mit uebernehmen",
                        variable=self.cfg_vmd4_var).pack(anchor=tk.W, pady=(2, 0))
        ttk.Label(
            tab_cfg,
            text="Wendet die Parameter aus der Axis-Device-Manager-Konfiguration "
            "(param.cgi) auf die markierten Kameras an; optional auch die "
            "Stream-Profile (gleichnamige vorhandene Profile werden ueberschrieben, "
            "neue angelegt). Enthaelt die Datei eine Bewegungserkennung (VMD4), "
            "wird diese automatisch mit angewendet (die VMD-Anwendung wird bei "
            "Bedarf gestartet). Die Konfiguration sollte zum Modell passen.",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(tab_cfg, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(12, 8))
        ttk.Label(tab_cfg, text="Konfiguration aus Kamera auslesen:",
                  font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        self.export_cfg_btn = ttk.Button(
            tab_cfg, text="Aus Kamera auslesen und speichern...",
            command=self._read_config)
        self.export_cfg_btn.pack(anchor=tk.W, pady=(4, 0))
        ttk.Label(
            tab_cfg,
            text="Liest die komplette Parameterliste der ERSTEN markierten Kamera. "
            "Anschliessend laesst sich auswaehlen und durchsuchen, welche Parameter "
            "in die ADM-.cfg geschrieben werden. Tipp: ein vollstaendiger Export "
            "enthaelt auch geraetespezifische/nur-lesbare Werte (z.B. Seriennummer) "
            "- fuer die Uebertragung auf andere Kameras nur passende Parameter waehlen.",
            wraplength=560, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        # --- Buttons ---
        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(6, 4))
        self.test_btn = ttk.Button(btns, text="Verbindung testen", command=self._test_connection)
        self.test_btn.pack(side=tk.LEFT)
        self.apply_btn = ttk.Button(btns, text="Anwenden", command=self._apply)
        self.apply_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Schliessen", command=self.destroy).pack(side=tk.RIGHT)

        # --- Ergebnisanzeige ---
        ttk.Label(outer, text="Ergebnis:").pack(anchor=tk.W, pady=(6, 0))
        self.result = scrolledtext.ScrolledText(outer, height=18, wrap=tk.WORD)
        self.result.configure(
            bg=self._palette["tree_bg"], fg=self._palette["fg"],
            insertbackground=self._palette["fg"],
        )
        self.result.pack(fill=tk.BOTH, expand=True, pady=(2, 0))
        self.result.config(state=tk.DISABLED)

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
        self.import_user_btn.config(state=state)
        self.import_onvif_btn.config(state=state)

    # ------------------------------------------------- Verbindung testen
    def _test_connection(self):
        if self._working:
            return
        self._clear_log()
        self._set_busy(True)
        self._log("Teste Verbindung (lesend, ohne Aenderung)...")
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
                self._queue.put((name, False, "keine IP-Adresse bekannt"))
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
        tab = self.nb.index(self.nb.select())
        if tab == 0:
            self._apply_ip()
        elif tab == 1:
            self._apply_user(onvif=False)
        elif tab == 2:
            self._apply_user(onvif=True)
        elif tab == 3:
            self._apply_firmware()
        else:
            self._apply_config()

    def _apply_ip(self):
        mode = self._mode_var.get()
        # Plausibilitaet pruefen und Zieladressen vorberechnen
        try:
            targets = self._compute_targets(mode)
        except ValueError as exc:
            messagebox.showerror("Eingabefehler", str(exc), parent=self)
            return

        confirm = "Auf DHCP umstellen?" if mode == "dhcp" else \
            "Folgende IP-Adressen setzen?\n\n" + "\n".join(
                f"  {self.cameras[i].get('Name','?')}: {t}" for i, t in targets.items()
            )
        if not messagebox.askyesno("Aenderung bestaetigen", confirm, parent=self):
            return

        self._clear_log()
        self._set_busy(True)
        self._log(f"Wende Aenderung an ({len(self.cameras)} Kamera(s))...")
        kwargs = self._conn_kwargs()
        threading.Thread(
            target=self._worker_apply, args=(mode, targets, kwargs), daemon=True
        ).start()
        self.after(150, self._poll)

    def _compute_targets(self, mode):
        """Berechnet die Ziel-IP je Kamera-Index (leer bei DHCP). Wirft ValueError."""
        if mode == "dhcp":
            return {}
        mask = self.mask_var.get().strip()
        if not mask:
            raise ValueError("Bitte eine Subnetzmaske angeben.")
        targets = {}
        if mode == "range":
            start = self.start_ip_var.get().strip()
            if not start:
                raise ValueError("Bitte eine Start-IP angeben.")
            try:
                for offset in range(len(self.cameras)):
                    targets[offset] = vapix.next_ip(start, offset)
            except ValueError:
                raise ValueError(f"Ungueltige Start-IP: {start}")
        elif mode == "each":
            for idx in range(len(self.cameras)):
                value = self._ip_entries[idx].get().strip()
                if not value:
                    raise ValueError(
                        f"Bitte fuer '{self.cameras[idx].get('Name','?')}' eine IP angeben."
                    )
                targets[idx] = value
        return targets

    def _worker_apply(self, mode, targets, kwargs):
        mask = self.mask_var.get().strip()
        gateway = self.gw_var.get().strip()
        for idx, cam in enumerate(self.cameras):
            ip = get_first_ip(cam)
            name = cam.get("Name", ip)
            if not ip:
                self._queue.put((name, False, "keine IP-Adresse bekannt"))
                continue
            try:
                if mode == "dhcp":
                    vapix.set_dhcp(ip, **kwargs)
                    self._queue.put((name, True, "auf DHCP umgestellt"))
                else:
                    new_ip = targets[idx]
                    vapix.set_static_ip(ip, new_ip=new_ip, subnet_mask=mask,
                                        gateway=gateway, **kwargs)
                    self._queue.put((name, True, f"IP gesetzt auf {new_ip}"))
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
            messagebox.showerror("Eingabefehler", "Bitte einen Benutzernamen angeben.", parent=self)
            return
        if not pwd:
            messagebox.showerror("Eingabefehler", "Bitte ein Passwort angeben.", parent=self)
            return

        kind = "ONVIF-Benutzer" if onvif else "Benutzer"
        verb = "anlegen" if action == "add" else "Passwort aendern fuer"
        confirm = f"{kind} '{name}' {verb} auf {len(self.cameras)} Kamera(s)?"
        if not messagebox.askyesno("Aenderung bestaetigen", confirm, parent=self):
            return

        self._clear_log()
        self._set_busy(True)
        self._log(f"Wende Aenderung an ({len(self.cameras)} Kamera(s))...")
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
        attempts = [("ohne Anmeldung", "", "", False)]
        for u, p in vapix.DEFAULT_CREDENTIALS:
            attempts.append((f"{u}/{p or 'leer'}", u, p, True))
        last = None
        for label, u, p, auth in attempts:
            ck = dict(base_kwargs)
            ck["username"] = u
            ck["password"] = p
            try:
                return op(ck, auth) + f" [Auslieferungszustand: {label}]"
            except vapix.VapixError as exc:
                last = exc
        raise last if last is not None else vapix.VapixError("kein Zugang moeglich")

    def _worker_user(self, onvif, action, name, pwd, level, factory, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, "keine IP-Adresse bekannt"))
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
                                    + " (vorhandener Benutzer, Passwort gesetzt)")
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
            title="Benutzerliste waehlen", parent=self,
            filetypes=[("Textdatei", "*.txt"), ("CSV-Datei", "*.csv"),
                       ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            users = vapix.parse_user_list(path, onvif=onvif)
        except vapix.VapixError as exc:
            messagebox.showerror("Datei-Fehler", str(exc), parent=self)
            return
        kind = "ONVIF-Benutzer" if onvif else "Benutzer"
        preview = "\n".join(f"  {u['name']} ({u['role']})" for u in users[:12])
        if len(users) > 12:
            preview += f"\n  ... ({len(users) - 12} weitere)"
        confirm = (f"{len(users)} {kind} aus der Datei auf {len(self.cameras)} "
                   f"Kamera(s) anlegen?\n\n{preview}")
        if not messagebox.askyesno("Stapel-Import bestaetigen", confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        factory = self.factory_var.get() and not onvif
        self._log(f"Importiere {len(users)} {kind} auf {len(self.cameras)} Kamera(s)...")
        kwargs = self._conn_kwargs()
        threading.Thread(target=self._worker_import_users,
                         args=(onvif, users, factory, kwargs), daemon=True).start()
        self.after(150, self._poll)

    def _worker_import_users(self, onvif, users, factory, kwargs):
        for cam in self.cameras:
            ip = get_first_ip(cam)
            cname = cam.get("Name", ip)
            if not ip:
                self._queue.put((cname, False, "keine IP-Adresse bekannt"))
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
            title="Firmware-Datei waehlen", parent=self,
            filetypes=[("Firmware", "*.bin"), ("Alle Dateien", "*.*")],
        )
        if path:
            self.fw_path_var.set(path)

    def _apply_firmware(self):
        path = self.fw_path_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showerror("Eingabefehler", "Bitte eine gueltige Firmware-Datei waehlen.",
                                 parent=self)
            return
        confirm = (
            f"Firmware\n  {os.path.basename(path)}\n"
            f"auf {len(self.cameras)} Kamera(s) aufspielen?\n\n"
            "Die Firmware MUSS zum Modell passen. Der Vorgang dauert einige "
            "Minuten, danach startet die Kamera neu."
        )
        if not messagebox.askyesno("Firmware-Update bestaetigen", confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(f"Spiele Firmware auf ({len(self.cameras)} Kamera(s)) - bitte warten...")
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
                self._queue.put((cname, False, "keine IP-Adresse bekannt"))
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
            title="ADM-Konfigurationsdatei waehlen", parent=self,
            filetypes=[("ADM-Konfiguration", "*.cfg"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        self.cfg_path_var.set(path)
        try:
            self._cfg = vapix.parse_adm_config(path)
            vmd4_note = (" | Bewegungserkennung (VMD4)"
                         if self._cfg.get("vmd4") is not None else "")
            self.cfg_info_var.set(
                f"Modell: {self._cfg['model'] or '?'} | Firmware: "
                f"{self._cfg['firmware'] or '?'} | {len(self._cfg['parameters'])} "
                f"Parameter, {len(self._cfg['profiles'])} Stream-Profil(e)"
                f"{vmd4_note}"
            )
        except vapix.VapixError as exc:
            self._cfg = None
            self.cfg_info_var.set(f"Fehler: {exc}")

    def _apply_config(self):
        if self._cfg is None:
            messagebox.showerror("Eingabefehler",
                                 "Bitte eine gueltige ADM-Konfigurationsdatei waehlen.",
                                 parent=self)
            return
        confirm = (
            f"Konfiguration fuer Modell '{self._cfg['model'] or '?'}'\n"
            f"({len(self._cfg['parameters'])} Parameter) auf "
            f"{len(self.cameras)} Kamera(s) anwenden?\n\n"
            "Die Konfiguration sollte zum Kameramodell passen."
        )
        if not messagebox.askyesno("Konfiguration anwenden", confirm, parent=self):
            return
        self._clear_log()
        self._set_busy(True)
        self._log(f"Wende Konfiguration an ({len(self.cameras)} Kamera(s))...")
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
                self._queue.put((cname, False, "keine IP-Adresse bekannt"))
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
            messagebox.showerror("Keine Kamera", "Keine Kamera ausgewaehlt.", parent=self)
            return
        cam = self.cameras[0]
        ip = get_first_ip(cam)
        name = cam.get("Name", ip)
        if not ip:
            messagebox.showerror("Keine IP",
                                 f"Fuer '{name}' ist keine IP-Adresse bekannt.", parent=self)
            return
        self._clear_log()
        self._set_busy(True)
        if len(self.cameras) > 1:
            self._log(f"Hinweis: Es wird nur die erste markierte Kamera ausgelesen ({name}).")
        self._log(f"Lese Konfiguration von {name} ({ip}) - bitte warten...")
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
            self._log(f"  [FEHLER] {name}: {payload}")
            return
        cfg = payload
        vmd4_note = (", Bewegungserkennung (VMD4)"
                     if cfg.get("vmd4") is not None else "")
        self._log(f"  [OK] {name}: {len(cfg['parameters'])} Parameter, "
                  f"{len(cfg['profiles'])} Stream-Profil(e){vmd4_note} gelesen")
        ParameterSelectDialog(self, cfg, name, self._palette)

    def _poll(self):
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._set_busy(False)
                    self._log("Fertig.")
                    return
                name, ok, msg = item
                self._log(f"  [{'OK' if ok else 'FEHLER'}] {name}: {msg}")
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
        self.title("Parameter auswaehlen und speichern")
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

    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            outer,
            text=f"{self._cam_name} - Modell {self._config.get('model') or '?'}, "
                 f"FW {self._config.get('firmware') or '?'}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(outer, text=f"{len(self._all_names)} Parameter gelesen. "
                  "Haken anklicken = in die .cfg uebernehmen.").pack(anchor=tk.W,
                                                                     pady=(0, 6))

        sf = ttk.Frame(outer)
        sf.pack(fill=tk.X)
        ttk.Label(sf, text="Suche:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refilter())
        ttk.Entry(sf, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        tf = ttk.Frame(outer)
        tf.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree = ttk.Treeview(tf, columns=("chk", "name", "value"),
                                 show="headings", selectmode="none")
        self.tree.heading("chk", text="")
        self.tree.heading("name", text="Parameter")
        self.tree.heading("value", text="Wert")
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
        ttk.Button(cf, text="Alle (gefiltert)",
                   command=lambda: self._set_filtered(True)).pack(side=tk.RIGHT)
        ttk.Button(cf, text="Keine (gefiltert)",
                   command=lambda: self._set_filtered(False)).pack(side=tk.RIGHT, padx=(0, 4))

        self._profiles_var = tk.BooleanVar(value=bool(self._config.get("profiles")))
        ttk.Checkbutton(
            outer,
            text=f"Stream-Profile einschliessen ({len(self._config.get('profiles', []))})",
            variable=self._profiles_var,
        ).pack(anchor=tk.W, pady=(6, 0))

        has_vmd4 = self._config.get("vmd4") is not None
        self._vmd4_var = tk.BooleanVar(value=has_vmd4)
        cb_vmd4 = ttk.Checkbutton(
            outer,
            text="Bewegungserkennung (VMD4) einschliessen"
                 + ("" if has_vmd4 else " (nicht vorhanden)"),
            variable=self._vmd4_var,
        )
        if not has_vmd4:
            cb_vmd4.state(["disabled"])
        cb_vmd4.pack(anchor=tk.W, pady=(2, 0))

        bf = ttk.Frame(outer)
        bf.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(bf, text="Speichern...", command=self._save).pack(side=tk.LEFT)
        ttk.Button(bf, text="Abbrechen", command=self.destroy).pack(side=tk.RIGHT)

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
            f"{len(self._selected)} von {len(self._all_names)} ausgewaehlt")

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
            messagebox.showerror("Nichts ausgewaehlt",
                                 "Bitte mindestens einen Parameter auswaehlen.",
                                 parent=self)
            return
        default = (self._config.get("model") or "konfiguration").replace(" ", "_") + ".cfg"
        path = filedialog.asksaveasfilename(
            title="ADM-Konfiguration speichern", parent=self,
            defaultextension=".cfg", initialfile=default,
            filetypes=[("ADM-Konfiguration", "*.cfg"), ("Alle Dateien", "*.*")],
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
            messagebox.showerror("Fehler beim Speichern", str(exc), parent=self)
            return
        extra = (f" + {len(self._config.get('profiles', []))} Stream-Profil(e)"
                 if with_profiles else "")
        if with_vmd4 and self._config.get("vmd4") is not None:
            extra += " + Bewegungserkennung (VMD4)"
        messagebox.showinfo("Gespeichert",
                            f"{n} Parameter{extra} gespeichert:\n{path}", parent=self)
        self.destroy()


def main():
    app = AxisDiscoveryGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
