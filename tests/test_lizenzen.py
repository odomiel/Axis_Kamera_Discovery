"""Lizenz-/Bausteinvollstaendigkeit -- fuer die GPL-Compliance und gegen Drift.

Faengt genau die Fehler ab, die beim Aktualisieren leicht passieren: einen Pin
(z. B. OpenSSL) anheben und THIRD_PARTY_LICENSES.md vergessen, oder ein neues
Wheel vendorn ohne es zu dokumentieren.
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build_appimage.sh"
DRITT = ROOT / "THIRD_PARTY_LICENSES.md"
LIZENZ = ROOT / "LICENSE"
SPEC = ROOT / "Axis_Kamera_Discovery.spec"

# Pin-Variable in build_appimage.sh -> Komponentenname in THIRD_PARTY.
PIN_KOMPONENTE = {"PY_VER": "cpython", "SSL_VER": "openssl",
                  "TCL_VER": "tcl", "TK_VER": "tk", "FFI_VER": "libffi"}


def _normieren(name):
    # "sv-ttk (Sun Valley)" -> "sv-ttk"; Gross/Klein egal.
    return name.split("(")[0].strip().lower()


def pins():
    out = {}
    for m in re.finditer(r"^(TCL_VER|TK_VER|PY_VER|FFI_VER|SSL_VER)=(\S+)",
                         BUILD.read_text(encoding="utf-8"), re.MULTILINE):
        out[m.group(1)] = m.group(2)
    return out


def vendored_wheels():
    return re.findall(r"^wheel\s+(\S+)", BUILD.read_text(encoding="utf-8"), re.MULTILINE)


def dritt_tabelle():
    """{normierter Komponentenname: Version} aus der Uebersichtstabelle."""
    out = {}
    for line in DRITT.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*([^|]+?)\s*\|\s*([0-9][0-9A-Za-z.\-]*)\s*\|", line)
        if m:
            out[_normieren(m.group(1))] = m.group(2)
    return out


class TestToolchainPins(unittest.TestCase):
    def test_alle_pins_vorhanden(self):
        self.assertEqual(set(pins()), set(PIN_KOMPONENTE),
                         "build_appimage.sh fehlt ein Toolchain-Pin")

    def test_pins_stimmen_mit_der_doku(self):
        tab = dritt_tabelle()
        for pin, wert in pins().items():
            komp = PIN_KOMPONENTE[pin]
            self.assertIn(komp, tab, f"{komp} fehlt in THIRD_PARTY_LICENSES.md")
            self.assertEqual(
                tab[komp], wert,
                f"{komp}: Pin {pin}={wert}, aber THIRD_PARTY sagt {tab[komp]} "
                f"-> THIRD_PARTY_LICENSES.md nachziehen")


class TestWheels(unittest.TestCase):
    def test_jedes_gebuendelte_wheel_ist_dokumentiert(self):
        tab = dritt_tabelle()
        for whl in vendored_wheels():
            self.assertIn(_normieren(whl), tab,
                          f"Wheel '{whl}' aus build_appimage.sh fehlt in "
                          f"THIRD_PARTY_LICENSES.md")


class TestLizenztexte(unittest.TestCase):
    def test_eigene_lizenz_ist_gpl3(self):
        t = LIZENZ.read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", t)
        self.assertIn("Version 3", t)

    def test_apache_2_volltext_liegt_bei(self):
        # Apache 2.0 (OpenSSL) verlangt die Beilage des Lizenztextes.
        t = DRITT.read_text(encoding="utf-8")
        self.assertIn("Apache License", t)
        self.assertIn("Version 2.0, January 2004", t)
        self.assertIn("TERMS AND CONDITIONS", t)

    def test_lgpl_21_volltext_liegt_bei(self):
        # LGPL-2.1 (zeroconf) verlangt die Beilage des Lizenztextes.
        t = DRITT.read_text(encoding="utf-8")
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", t)
        self.assertIn("Version 2.1, February 1999", t)

    def test_spec_buendelt_die_lizenzdateien(self):
        t = SPEC.read_text(encoding="utf-8")
        for datei in ("README.md", "THIRD_PARTY_LICENSES.md", "LICENSE"):
            self.assertIn(datei, t,
                          f"Windows-Spec buendelt '{datei}' nicht -> EXE ohne Lizenz")


if __name__ == "__main__":
    unittest.main()
