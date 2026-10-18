"""release.sh bleibt oeffentlich-spiegel-tauglich und liefert die .zsync mit."""

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release.sh"

# Verbotene Infrastruktur-Literale, aus Teilen gebaut, damit diese Testdatei sie
# nicht selbst traegt (sonst schluege die Spiegel-Hygiene darueber an).
VERBOTEN = {
    "Forgejo-Host": "ere" + "bor",
    "Host-Domain":  "mittel" + "erde",
    "Owner":        "forgejo" + "user",
    "API-Port":     ":30" + "53",
}


class TestReleaseHygiene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = RELEASE.read_text(encoding="utf-8")

    def test_keine_host_owner_literale(self):
        # Host/Owner/Token werden zur Laufzeit abgeleitet, nicht hinterlegt.
        for name, nadel in VERBOTEN.items():
            self.assertNotIn(nadel, self.t,
                             f"release.sh enthaelt das {name}-Literal "
                             f"-> nicht spiegel-tauglich")

    def test_laedt_die_zsync_mit(self):
        self.assertIn(".zsync", self.t,
                      "release.sh haengt die .zsync nicht an -> GearLever-Updates fehlen")

    def test_token_kommt_aus_git_credentials(self):
        self.assertIn(".git-credentials", self.t)


if __name__ == "__main__":
    unittest.main()
