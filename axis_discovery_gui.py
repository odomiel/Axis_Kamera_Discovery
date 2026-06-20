#!/usr/bin/env python3
"""Grafische Oberflaeche fuer die Axis-Kamera-Suche.

Verwendet die Discovery-Logik aus axis_discovery_cli.py wieder und stellt
sie ueber eine Tkinter-Oberflaeche bereit. Die Suche laeuft in einem
Hintergrund-Thread, damit das Fenster waehrend der ~10 Sekunden nicht
einfriert.
"""

import os
import queue
import threading
import webbrowser

import tkinter as tk
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

        self._build_menu()
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- UI
    def _build_menu(self):
        menubar = tk.Menu(self)
        settings = tk.Menu(menubar, tearoff=0)
        settings.add_command(label="Info", command=self._show_info)
        settings.add_command(label="Hilfe", command=self._show_help)
        menubar.add_cascade(label="Einstellungen", menu=settings)
        self.config(menu=menubar)

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

        self.export_btn = ttk.Button(
            bar, text="Exportieren...", command=self.export, state=tk.DISABLED
        )
        self.export_btn.pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.RIGHT, padx=8)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings")
        for col in COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=180, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._open_in_browser)

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4
        ).pack(side=tk.BOTTOM, fill=tk.X)

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
        self.destroy()

    # --------------------------------------------------- Menue: Einstellungen
    def _show_info(self):
        messagebox.showinfo(
            "Info",
            "Axis IP Utility\n"
            f"Version {__version__}\n\n"
            "Findet Axis-Kameras im lokalen Netzwerk per Zeroconf/mDNS.",
        )

    def _show_help(self):
        readme = os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md")
        if not os.path.exists(readme):
            messagebox.showerror("Hilfe", "README.md wurde nicht gefunden.")
            return
        with open(readme, encoding="utf-8") as f:
            content = f.read()

        win = tk.Toplevel(self)
        win.title("Hilfe - README")
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
