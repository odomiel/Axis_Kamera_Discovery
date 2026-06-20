#!/usr/bin/env python3
"""Grafische Oberflaeche fuer die Axis-Kamera-Suche.

Verwendet die Discovery-Logik aus axis_discovery_cli.py wieder und stellt
sie ueber eine Tkinter-Oberflaeche bereit. Die Suche laeuft in einem
Hintergrund-Thread, damit das Fenster waehrend der ~10 Sekunden nicht
einfriert.
"""

# Axis IP Utility - findet Axis-Netzwerkkameras per Zeroconf/mDNS.
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

import os
import platform
import queue
import threading
import webbrowser
from importlib import metadata

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, scrolledtext, ttk

from axis_discovery_cli import (
    AxisDiscovery,
    export_results,
    get_first_ip,
    FIELD_NAMES,
    __version__,
)

COLUMNS = FIELD_NAMES


class AxisDiscoveryGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Axis Kamera Discovery {__version__}")
        self.geometry("1000x500")
        self.minsize(700, 350)

        self.cameras = []
        self._result_queue = queue.Queue()
        self._searching = False
        self._refresh_after_id = None
        self._settings_popup = None
        self._sort_state = {}  # Spalte -> zuletzt absteigend? (fuer Klick-Toggle)

        # Fonts fuer die automatische Spaltenbreiten-Messung
        self._cell_font = tkfont.nametofont("TkDefaultFont")
        try:
            self._heading_font = tkfont.nametofont("TkHeadingFont")
        except tk.TclError:
            self._heading_font = self._cell_font

        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Klick irgendwo schliesst ein offenes Einstellungen-Dropdown
        self.bind_all("<Button-1>", self._on_global_click, add="+")

    # ---------------------------------------------------------------- UI
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        self.search_btn = ttk.Button(bar, text="Suchen", command=self.start_search)
        self.search_btn.pack(side=tk.LEFT)

        ttk.Label(bar, text="Dauer (s):").pack(side=tk.LEFT, padx=(12, 4))
        self.timeout_var = tk.IntVar(value=10)
        ttk.Spinbox(bar, from_=1, to=60, width=4, textvariable=self.timeout_var).pack(
            side=tk.LEFT
        )

        self.autorefresh_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            bar,
            text="Auto-Refresh",
            variable=self.autorefresh_var,
            command=self._on_autorefresh_toggle,
        ).pack(side=tk.LEFT, padx=(16, 4))

        ttk.Label(bar, text="alle (s):").pack(side=tk.LEFT, padx=(0, 4))
        self.interval_var = tk.IntVar(value=30)
        ttk.Spinbox(bar, from_=5, to=3600, width=5, textvariable=self.interval_var).pack(
            side=tk.LEFT
        )

        # Menue-Button "Einstellungen" rechts neben "Exportieren"
        self.settings_btn = ttk.Button(
            bar, text="Einstellungen", command=self._toggle_settings_menu
        )
        self.settings_btn.pack(side=tk.RIGHT)

        self.export_btn = ttk.Button(
            bar, text="Exportieren...", command=self.export, state=tk.DISABLED
        )
        self.export_btn.pack(side=tk.RIGHT, padx=(0, 8))

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT, padx=8)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            # Klick auf die Ueberschrift sortiert nach dieser Spalte
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            # stretch=NO: die per _autosize_columns gemessenen Breiten bleiben verbindlich
            self.tree.column(col, width=180, anchor=tk.W, stretch=tk.NO)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._open_in_browser)
        self._autosize_columns()  # initiale Breite an die Ueberschriften anpassen

    def _autosize_columns(self):
        """Passt jede Spaltenbreite an den breitesten Inhalt (inkl. Ueberschrift) an."""
        for col in COLUMNS:
            header = self.tree.heading(col, "text")
            width = self._heading_font.measure(header)
            for iid in self.tree.get_children(""):
                cell = self.tree.set(iid, col)
                width = max(width, self._cell_font.measure(cell))
            # Polster + sinnvolle Unter-/Obergrenze
            self.tree.column(col, width=min(max(width + 24, 60), 600))

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Bereit.")
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
        for c in COLUMNS:
            arrow = ("  ▲" if not reverse else "  ▼") if c == col else ""
            self.tree.heading(c, text=c + arrow)

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
        self.status_var.set(f"Suche laeuft ({timeout} s)...")
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
            self.status_var.set("Fehler bei der Suche.")
            messagebox.showerror("Fehler", payload)
            return

        self.cameras = payload
        for cam in self.cameras:
            self.tree.insert("", tk.END, values=[cam.get(c, "") for c in COLUMNS])
        self._autosize_columns()  # Breiten an die neuen Inhalte anpassen

        if self.cameras:
            self.export_btn.config(state=tk.NORMAL)
            self.status_var.set(f"{len(self.cameras)} Kamera(s) gefunden.")
        else:
            self.status_var.set("Keine Axis-Kameras gefunden.")

        self._schedule_refresh()  # naechsten Auto-Refresh planen (falls aktiviert)

    # ------------------------------------------------------- Auto-Refresh
    def _on_autorefresh_toggle(self):
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
        frame = ttk.Frame(popup, relief="solid", borderwidth=1)
        frame.pack(fill=tk.BOTH, expand=True)

        for label, command in (
            ("Info", self._show_info),
            ("Hilfe", self._show_help),
            ("Lizenzen", self._show_licenses),
        ):
            ttk.Button(
                frame,
                text=label,
                command=lambda c=command: self._choose_setting(c),
            ).pack(fill=tk.X)  # fuellt die volle Breite des Dropdowns

        self._settings_popup = popup

        # Position unter dem Button, Breite exakt wie der Einstellungen-Button
        popup.update_idletasks()
        width = btn.winfo_width()
        height = frame.winfo_reqheight()
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        popup.geometry(f"{width}x{height}+{x}+{y}")

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

    def _show_info(self):
        messagebox.showinfo(
            "Info",
            "Axis IP Utility\n"
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
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
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

    # ----------------------------------------------------------- Aktionen
    def _open_in_browser(self, _event):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        # gleiche Logik wie das CLI: erste IP aus dem Adressfeld
        first_ip = get_first_ip(dict(zip(COLUMNS, values)))
        if first_ip:
            webbrowser.open(f"http://{first_ip}")

    def export(self):
        if not self.cameras:
            return
        path = filedialog.asksaveasfilename(
            title="Ergebnisse speichern",
            defaultextension=".csv",
            initialfile="axis_cameras.csv",
            filetypes=[
                ("CSV-Datei", "*.csv"),
                ("Textdatei", "*.txt"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not path:
            return
        # Format anhand der Dateiendung (csv -> CSV, sonst Texttabelle)
        export_results(self.cameras, path)
        self.status_var.set(f"Exportiert nach {path}")


def main():
    app = AxisDiscoveryGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
