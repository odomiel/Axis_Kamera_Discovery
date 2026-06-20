#! /bin/bash
# Weiche zwischen GUI und CLI:
#   - ohne Argumente (z. B. Doppelklick) -> grafische Oberflaeche
#   - "cli ..." oder ein Flag (-x/--xyz) -> Kommandozeilen-Tool
PY="{{ python-executable }}"
if [ "$1" = "cli" ]; then
    shift
    exec "$PY" "${APPDIR}/axis_discovery_cli.py" "$@"
elif [ "${1:0:1}" = "-" ]; then
    exec "$PY" "${APPDIR}/axis_discovery_cli.py" "$@"
else
    exec "$PY" "${APPDIR}/axis_discovery_gui.py" "$@"
fi
