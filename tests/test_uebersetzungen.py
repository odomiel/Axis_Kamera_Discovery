"""Jeder Oberflaechentext existiert auf Deutsch UND Englisch.

Analysiert axis_kamera_discovery_gui.py per AST (kein Import, also kein Tkinter
noetig): sammelt die Schluessel der TRANSLATIONS-Woerterbuecher 'de'/'en' sowie
jeden literal benutzten `self._("...")`-Schluessel.
"""

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUI = ROOT / "axis_kamera_discovery_gui.py"


def _analysieren():
    baum = ast.parse(GUI.read_text(encoding="utf-8"))
    sprachen = {}
    benutzt = set()
    for knoten in ast.walk(baum):
        # TRANSLATIONS = { "de": {...}, "en": {...} }
        if isinstance(knoten, ast.Assign) and any(
                isinstance(z, ast.Name) and z.id == "TRANSLATIONS"
                for z in knoten.targets) and isinstance(knoten.value, ast.Dict):
            for lang, woerter in zip(knoten.value.keys, knoten.value.values):
                if (isinstance(lang, ast.Constant) and isinstance(lang.value, str)
                        and isinstance(woerter, ast.Dict)):
                    sprachen[lang.value] = {
                        k.value for k in woerter.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        # self._("schluessel")
        if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                and knoten.func.attr == "_" and knoten.args
                and isinstance(knoten.args[0], ast.Constant)
                and isinstance(knoten.args[0].value, str)):
            benutzt.add(knoten.args[0].value)
    return sprachen, benutzt


class TestUebersetzungen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sprachen, cls.benutzt = _analysieren()

    def test_de_und_en_vorhanden(self):
        self.assertIn("de", self.sprachen)
        self.assertIn("en", self.sprachen)
        self.assertGreater(len(self.sprachen["de"]), 50)

    def test_de_und_en_haben_dieselben_schluessel(self):
        nur_de = self.sprachen["de"] - self.sprachen["en"]
        nur_en = self.sprachen["en"] - self.sprachen["de"]
        self.assertEqual(nur_de, set(), f"nur auf Deutsch: {sorted(nur_de)}")
        self.assertEqual(nur_en, set(), f"nur auf Englisch: {sorted(nur_en)}")

    def test_jeder_benutzte_schluessel_ist_uebersetzt(self):
        fehlt_de = sorted(self.benutzt - self.sprachen["de"])
        fehlt_en = sorted(self.benutzt - self.sprachen["en"])
        self.assertEqual(fehlt_de, [], f"self._()-Schluessel ohne de-Eintrag: {fehlt_de}")
        self.assertEqual(fehlt_en, [], f"self._()-Schluessel ohne en-Eintrag: {fehlt_en}")


if __name__ == "__main__":
    unittest.main()
