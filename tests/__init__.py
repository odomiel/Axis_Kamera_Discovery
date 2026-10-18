"""Statische Bau- und Konsistenztests fuer Axis_Kamera_Discovery.

Geprueft wird ohne echten Build und ohne Fremdpakete -- es genuegt das
System-`python3`. Die Tests lesen die Verpackungsdateien (build_appimage.sh,
Axis_Kamera_Discovery.spec, THIRD_PARTY_LICENSES.md, release.sh, bump_version.py)
und die Module und stellen Invarianten sicher, die beim Entwickeln leicht
auseinanderlaufen:

  * Version einheitlich und im richtigen Format
  * jede gebuendelte Abhaengigkeit ist in THIRD_PARTY_LICENSES.md dokumentiert,
    und die Toolchain-Pins stimmen mit der Doku ueberein (Lizenz-Compliance)
  * das Build-Skript haelt seine kritischen Zusagen (Tcl/Tk nicht strippen,
    CA-Bundle, Update-Info, X-AppImage-Version, zsync)
  * die Windows-Spec buendelt Lizenzen und die noetigen Module
  * release.sh traegt keine Infrastruktur-Literale (oeffentlicher Spiegel)
  * kein versionierter Text verraet Heimatpfade/Forgejo-Host (Spiegel-Hygiene)
  * jeder Oberflaechentext existiert auf Deutsch UND Englisch
  * axis_kamera_discovery_vapix bleibt stdlib-only

Lauf:  python3 -m unittest discover -s tests -t .
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
