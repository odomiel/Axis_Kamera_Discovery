#! /bin/bash
# Startet die Tkinter-GUI mit dem im AppImage gebuendelten Python.
exec "{{ python-executable }}" "${APPDIR}/axis_discovery_gui.py" "$@"
