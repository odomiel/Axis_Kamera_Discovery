"""Sicherheits-Invarianten aus dem Audit (2026-11-08) dauerhaft absichern.

Prueft am echten Verhalten (lokaler HTTP-Server auf 127.0.0.1, keine Kamera):
  - Befund 1: Basic-Auth ueber HTTP wird ab Werk abgelehnt (kein Klartext-Leck);
    per set_basic_over_http(True) wieder erlaubt.
  - Befund 2a: passwortsetzende Aktionen fallen im Modus 'auto' NICHT auf HTTP
    zurueck, wenn HTTPS nicht erreichbar ist.
  - Befund 4: CSV-Export maskiert fuehrende Formelzeichen.
  - Befund 7: Geraete-Sicherung/.cfg-Export entstehen mit Rechten 0600.

vapix ist stdlib-only, laesst sich also mit dem System-python3 testen.
"""

import base64
import http.server
import os
import pathlib
import stat
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import axis_kamera_discovery_vapix as vapix   # noqa: E402


class _BasicServer:
    """Lokaler Server, der Basic-Auth verlangt und gesehene Header protokolliert."""

    def __init__(self):
        gesehen = self.gesehen = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                auth = self.headers.get("Authorization", "")
                gesehen.append(auth)
                if not auth:
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="AXIS"')
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()

    def klartext_passwoerter(self):
        return [base64.b64decode(a.split()[1]).decode()
                for a in self.gesehen if a.startswith("Basic ")]


class TestBasicUeberHttp(unittest.TestCase):
    def tearDown(self):
        vapix.set_basic_over_http(False)   # globalen Schalter zuruecksetzen

    def test_basic_ueber_http_wird_abgelehnt(self):
        vapix.set_basic_over_http(False)
        with _BasicServer() as s:
            with self.assertRaises(vapix.BasicOverHttpRefused):
                vapix.set_user_password("127.0.0.1", "root", "AdminPasswort", "root",
                                        "NeuesPasswort!", scheme="http", port=s.port, timeout=3)
            self.assertEqual(s.klartext_passwoerter(), [],
                             "Passwort darf NICHT im Klartext an den Server gegangen sein")

    def test_opt_in_erlaubt_basic(self):
        vapix.set_basic_over_http(True)
        with _BasicServer() as s:
            vapix.set_user_password("127.0.0.1", "root", "AdminPasswort", "root",
                                    "NeuesPasswort!", scheme="http", port=s.port, timeout=3)
            self.assertIn("root:AdminPasswort", s.klartext_passwoerter())


class TestKeinHttpRueckfall(unittest.TestCase):
    def tearDown(self):
        vapix.set_basic_over_http(False)

    def test_auto_faellt_bei_passwortaktion_nicht_auf_http_zurueck(self):
        # 'auto' probiert HTTPS auf dem Port zuerst -> TLS scheitert am HTTP-Server
        # -> KEIN Rueckfall auf HTTP -> VapixError, und der Server sieht nichts.
        with _BasicServer() as s:
            with self.assertRaises(vapix.VapixError):
                vapix.set_user_password("127.0.0.1", "root", "AdminPasswort", "root",
                                        "NeuesPasswort!", scheme="auto", port=s.port, timeout=3)
            self.assertEqual(s.gesehen, [],
                             "Im auto-Modus darf das neue Passwort nicht ueber HTTP gehen")


class TestDateirechte(unittest.TestCase):
    def test_open_private_ist_0600(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "backup.json")
        open(p, "w").close()
        os.chmod(p, 0o644)                 # vorher welt-lesbar
        with vapix._open_private(p) as fh:
            fh.write("{}")
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)


class TestZertifikatPinning(unittest.TestCase):
    """Befund 3: Trust-on-First-Use-Pinning der Kamerazertifikate."""

    def setUp(self):
        # Pin-Speicher in ein temporaeres XDG-Verzeichnis umlenken (nicht den echten).
        self._alt = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
        vapix.set_pinning_enabled(True)

    def tearDown(self):
        vapix.set_pinning_enabled(True)
        if self._alt is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._alt

    def test_lernen_merken_abweichung(self):
        ip = "192.0.2.7"
        vapix._pin_verify_or_learn(ip, b"zert-A")       # lernt
        self.assertIsNotNone(vapix.known_fingerprint(ip))
        vapix._pin_verify_or_learn(ip, b"zert-A")       # gleich -> ok
        with self.assertRaises(vapix.CertMismatch):     # anders -> Abbruch
            vapix._pin_verify_or_learn(ip, b"zert-B")
        self.assertIsInstance(vapix.CertMismatch("x"), vapix.VapixError)

    def test_downgrade_wird_blockiert(self):
        ip = "192.0.2.8"
        self.assertFalse(vapix._pin_blocks_fallback(ip))
        vapix._pin_verify_or_learn(ip, b"zert-A")
        self.assertTrue(vapix._pin_blocks_fallback(ip))

    def test_vergessen(self):
        ip = "192.0.2.9"
        vapix._pin_verify_or_learn(ip, b"zert-A")
        self.assertEqual(vapix.forget_pins([ip]), 1)
        self.assertIsNone(vapix.known_fingerprint(ip))

    def test_abgeschaltet_lernt_nicht(self):
        ip = "192.0.2.10"
        vapix.set_pinning_enabled(False)
        vapix._pin_verify_or_learn(ip, b"zert-A")
        self.assertIsNone(vapix.known_fingerprint(ip))
        vapix._pin_verify_or_learn(ip, b"zert-B")       # kein Fehler

    def test_speicher_ist_0600(self):
        vapix._pin_verify_or_learn("192.0.2.11", b"zert-A")
        mode = stat.S_IMODE(os.stat(vapix._pin_path()).st_mode)
        self.assertEqual(mode, 0o600)


class TestCsvMaskierung(unittest.TestCase):
    def test_fuehrende_formelzeichen_maskiert(self):
        import axis_kamera_discovery_cli as cli
        for roh in ("=SUM(A1)", "+1", "-2", "@cmd", "\tx", "\rx"):
            self.assertTrue(cli._csv_safe(roh).startswith("'"),
                            f"{roh!r} muss maskiert werden")
        for harmlos in ("AXIS P1375", "192.168.1.10", ""):
            self.assertEqual(cli._csv_safe(harmlos), harmlos)


if __name__ == "__main__":
    unittest.main()
