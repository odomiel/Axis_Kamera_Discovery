"""Spiegel-Hygiene: kein versionierter Text verraet Infrastruktur oder Heimatpfade.

Das Repo wird oeffentlich nach GitHub gespiegelt. Alles, was committet ist,
landet dort. Dieser Test wacht darueber, dass der Forgejo-Host, der Owner und
lokale `/home/`-Pfade NICHT in versionierte Dateien geraten.
"""

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Aus Teilen gebaut, damit diese Testdatei die Nadeln nicht selbst traegt.
NADELN = {
    "Forgejo-Host": "ere" + "bor",
    "Host-Domain":  "mittel" + "erde",
    "Owner":        "forgejo" + "user",
    "Heimatpfad":   "/home/" + "thomas",
}

# Binaerdateien ueberspringen.
BINAER = {".png", ".ico", ".jpg", ".jpeg", ".gif", ".pdf", ".AppImage",
          ".zsync", ".exe", ".whl", ".bin", ".so", ".pyc"}


def versionierte_textdateien():
    out = subprocess.check_output(["git", "ls-files"], cwd=str(ROOT), text=True)
    for name in out.splitlines():
        p = ROOT / name
        if p.suffix in BINAER or not p.is_file():
            continue
        try:
            yield name, p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


class TestSpiegelHygiene(unittest.TestCase):
    def test_keine_infrastruktur_in_versionierten_dateien(self):
        treffer = []
        for name, inhalt in versionierte_textdateien():
            for was, nadel in NADELN.items():
                if nadel in inhalt:
                    treffer.append(f"{name}: {was}")
        self.assertEqual(treffer, [],
                         "Infrastruktur/Heimatpfad in versionierten Dateien "
                         "(gelangt in den oeffentlichen GitHub-Spiegel): "
                         + "; ".join(treffer))


if __name__ == "__main__":
    unittest.main()
