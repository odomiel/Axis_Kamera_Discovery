"""axis_kamera_discovery_vapix bleibt stdlib-only (Entwurfs-Invariante).

Der VAPIX-Client soll ohne Fremdpakete auskommen, damit er sich mit dem blossen
System-python3 testen laesst. Optionale Dinge (z. B. pyzipper) werden nur LAZY in
einer Funktion importiert -- das zaehlt hier nicht als Modul-Abhaengigkeit.
"""

import ast
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
VAPIX = ROOT / "axis_kamera_discovery_vapix.py"


def top_level_importe():
    """Namen der auf Modulebene importierten Top-Pakete."""
    baum = ast.parse(VAPIX.read_text(encoding="utf-8"))
    namen = set()
    for knoten in baum.body:   # nur Modulebene, keine Importe in Funktionen
        if isinstance(knoten, ast.Import):
            for a in knoten.names:
                namen.add(a.name.split(".")[0])
        elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
            namen.add(knoten.module.split(".")[0])
    return namen


class TestVapixStdlib(unittest.TestCase):
    def test_nur_stdlib_auf_modulebene(self):
        stdlib = set(sys.stdlib_module_names)
        fremd = sorted(n for n in top_level_importe() if n not in stdlib)
        self.assertEqual(
            fremd, [],
            f"vapix importiert auf Modulebene Nicht-stdlib: {fremd} "
            f"-> entweder stdlib nutzen oder LAZY in der Funktion importieren")

    def test_keine_vendored_pakete_auf_modulebene(self):
        vendored = {"zeroconf", "ifaddr", "prettytable", "wcwidth", "sv_ttk",
                    "pyzipper", "Cryptodome", "Cryptodomex"}
        verletzt = top_level_importe() & vendored
        self.assertEqual(verletzt, set(),
                         f"vapix haengt am Modulanfang an {verletzt}")


if __name__ == "__main__":
    unittest.main()
