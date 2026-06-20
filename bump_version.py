#!/usr/bin/env python3
"""Erhoeht/setzt die Programmversion nach dem Schema JJ.MM.TT.

Regeln:
  * Erstes Release eines Tages  -> "JJ.MM.TT"   (z. B. 26.06.20)
  * Weitere Releases am selben Tag -> Suffix b1, b2, b3 ... hochzaehlend
    (z. B. 26.06.20b1, 26.06.20b2)

Die Version wird in axis_discovery_cli.py (__version__) gepflegt.
Aufruf:
  python3 bump_version.py            # naechste Version setzen und schreiben
  python3 bump_version.py --print    # nur die *aktuelle* Version ausgeben
  python3 bump_version.py --dry-run  # naechste Version berechnen, aber nicht schreiben
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent / "axis_discovery_cli.py"
_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']*)["\']', re.MULTILINE)
_PARSE_RE = re.compile(r'^(\d{2}\.\d{2}\.\d{2})(?:b(\d+))?$')


def read_version(text):
    match = _VERSION_RE.search(text)
    if not match:
        raise SystemExit("Konnte __version__ in axis_discovery_cli.py nicht finden.")
    return match.group(1)


def next_version(current, today=None):
    today = today or datetime.date.today().strftime("%y.%m.%d")
    match = _PARSE_RE.match(current or "")
    if match and match.group(1) == today:
        # gleicher Tag -> Suffix hochzaehlen (kein Suffix -> b1)
        n = int(match.group(2)) if match.group(2) else 0
        return f"{today}b{n + 1}"
    # neuer Tag (oder unbekanntes Altformat) -> Basisversion
    return today


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--print", dest="show", action="store_true",
                        help="nur aktuelle Version ausgeben")
    parser.add_argument("--dry-run", action="store_true",
                        help="naechste Version berechnen, aber Datei nicht aendern")
    args = parser.parse_args()

    text = VERSION_FILE.read_text(encoding="utf-8")
    current = read_version(text)

    if args.show:
        print(current)
        return

    new = next_version(current)

    if args.dry_run:
        print(new)
        return

    new_text = _VERSION_RE.sub(f'__version__ = "{new}"', text, count=1)
    VERSION_FILE.write_text(new_text, encoding="utf-8")
    print(new, file=sys.stdout)


if __name__ == "__main__":
    main()
