"""Die Version ist einheitlich und hat das richtige Format."""

import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "axis_kamera_discovery_cli.py"
SPEC = ROOT / "Axis_Kamera_Discovery.spec"
RELEASE = ROOT / "release.sh"

# Schema: JJ.MM.TT, optional b1/b2/... fuer mehrere Releases am selben Tag.
VERSION_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}(b\d+)?$")


def version_aus_cli():
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']',
                  CLI.read_text(encoding="utf-8"), re.MULTILINE)
    return m.group(1) if m else None


class TestVersion(unittest.TestCase):
    def test_cli_version_hat_das_schema(self):
        v = version_aus_cli()
        self.assertIsNotNone(v, "__version__ nicht in cli-Modul gefunden")
        self.assertRegex(v, VERSION_RE, f"Version '{v}' passt nicht zu JJ.MM.TT[bN]")

    def test_bump_version_print_stimmt_mit_cli_ueberein(self):
        # bump_version.py ist die einzige Quelle, die __version__ schreibt/liest.
        out = subprocess.check_output(
            [sys.executable, str(ROOT / "bump_version.py"), "--print"],
            cwd=str(ROOT), text=True).strip()
        self.assertEqual(out, version_aus_cli(),
                         "bump_version --print weicht von cli __version__ ab")

    def test_spec_liest_die_version_aus_dem_cli_modul(self):
        txt = SPEC.read_text(encoding="utf-8")
        self.assertIn("axis_kamera_discovery_cli.py", txt)
        self.assertIn("__version__", txt)

    def test_release_nutzt_bump_version(self):
        self.assertIn("bump_version.py --print", RELEASE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
