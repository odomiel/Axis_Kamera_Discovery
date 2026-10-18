"""Kritische Zusagen des Build-Skripts -- sie sind leicht aus Versehen zu brechen."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build_appimage.sh"
SPEC = ROOT / "Axis_Kamera_Discovery.spec"


class TestBuildAppimage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = BUILD.read_text(encoding="utf-8")

    def test_strip_laesst_tcl_tk_in_ruhe(self):
        # strip --strip-unneeded auf libtcl*/libtk* schneidet die angehaengte
        # zipfs-Script-Library ab -> Tcl bricht mit "init.tcl"-Fehler.
        self.assertRegex(self.t, r"strip --strip-unneeded")
        self.assertIn("! -name '*tcl*'", self.t)
        self.assertIn("! -name '*tk*'", self.t)

    def test_ca_bundle_wird_mitgeliefert(self):
        # Ohne cert.pem schlaegt die verifizierte HTTPS-Update-Pruefung fehl.
        self.assertIn("ssl/cert.pem", self.t)

    def test_update_information_wird_eingebettet(self):
        # Fuer AppImageUpdate/GearLever.
        self.assertIn("gh-releases-zsync|", self.t)
        self.assertRegex(self.t, r'"\$AIT".*-u ')

    def test_x_appimage_version_in_desktop(self):
        # GearLever liest die installierte Fassung daraus.
        self.assertIn("X-AppImage-Version=", self.t)

    def test_zsync_wird_abgesichert(self):
        # appimagetool laesst die .zsync gelegentlich leise aus -> Pruefung noetig.
        self.assertIn(".zsync", self.t)
        self.assertRegex(self.t, r"\.zsync.*fehlt|WARNUNG")


class TestSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = SPEC.read_text(encoding="utf-8")

    def test_dynamisch_geladene_pakete_werden_eingesammelt(self):
        for paket in ("zeroconf", "ifaddr", "sv_ttk", "pyzipper", "Cryptodome"):
            self.assertIn(f'collect_submodules("{paket}")', self.t,
                          f"hiddenimports fehlt {paket} -> EXE findet es evtl. nicht")

    def test_ungenutzte_module_ausgeschlossen(self):
        self.assertRegex(self.t, r"excludes\s*=\s*\[[^\]]*unittest")


if __name__ == "__main__":
    unittest.main()
