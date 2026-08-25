#!/usr/bin/env bash
# release.sh - Formalisiert das Forgejo-Release fuer Axis_Kamera_Discovery.
#
# Ein gepushter Git-Tag "vX" ist bei Forgejo NOCH KEIN Release-Objekt. Dieses
# Skript erledigt die komplette Kette:
#   1. Vorbedingungen pruefen (sauberer Baum, HEAD gepusht, AppImage vorhanden)
#   2. annotierten Tag  vX  anlegen (falls noch nicht vorhanden) und pushen
#   3. Release-Objekt ueber die Forgejo-HTTP-API anlegen (HTTPS,
#      selbst-signiert -> curl -k), Release-Notes aus dem README-Changelog
#   4. das gebaute AppImage als Asset anhaengen
#
# Der Schreib-Token wird aus ~/.git-credentials gelesen und NIE ausgegeben.
#
# Aufruf:
#   ./release.sh                 # Version aus bump_version.py --print
#   ./release.sh --version 26.08.10b1
#   ./release.sh --dry-run       # nur pruefen/anzeigen, nichts veraendern
#   ./release.sh --notes-file X  # Release-Text aus Datei statt aus dem README
#
# Copyright (C) 2026 Mirik - GPL-3.0-or-later
set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration (siehe CLAUDE.md, Abschnitt "Releasing")
# ---------------------------------------------------------------------------
API_BASE="https://forgejo.invalid"
API_OWNER="owner"
API_REPO="Axis_Kamera_Discovery"
CRED_FILE="${HOME}/.git-credentials"
CRED_HOST="forgejo.invalid"     # so steht der Host in git-credentials
GIT_REMOTE="forgejo"
GIT_BRANCH="main"

cd "$(dirname "$(readlink -f "$0")")"

# ---------------------------------------------------------------------------
# Argumente
# ---------------------------------------------------------------------------
VERSION=""
NOTES_FILE=""
DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --version)    VERSION="${2:?--version braucht einen Wert}"; shift 2 ;;
        --notes-file) NOTES_FILE="${2:?--notes-file braucht einen Wert}"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        -h|--help)    grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unbekannte Option: $1" >&2; exit 2 ;;
    esac
done

die()  { echo "FEHLER: $*" >&2; exit 1; }
info() { echo ">> $*"; }

# ---------------------------------------------------------------------------
# Version + AppImage bestimmen
# ---------------------------------------------------------------------------
[ -n "$VERSION" ] || VERSION="$(python3 bump_version.py --print)"
[ -n "$VERSION" ] || die "Konnte Version nicht ermitteln."
TAG="v${VERSION}"
APPIMAGE="Axis_Kamera_Discovery-${VERSION}-x86_64.AppImage"

info "Version:  ${VERSION}"
info "Tag:      ${TAG}"
info "AppImage: ${APPIMAGE}"

[ -f "$APPIMAGE" ] || die "AppImage '${APPIMAGE}' fehlt - erst bauen (./build_appimage.sh)."

# ---------------------------------------------------------------------------
# Vorbedingungen: sauberer Baum + HEAD gepusht
# ---------------------------------------------------------------------------
[ -z "$(git status --porcelain)" ] || die "Arbeitsbaum ist nicht sauber (erst committen/pushen)."

git fetch -q "$GIT_REMOTE" "$GIT_BRANCH" || die "git fetch ${GIT_REMOTE} fehlgeschlagen."
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "${GIT_REMOTE}/${GIT_BRANCH}")"
[ "$LOCAL" = "$REMOTE" ] || die "HEAD ist nicht auf ${GIT_REMOTE}/${GIT_BRANCH} gepusht (erst 'git push')."

# ---------------------------------------------------------------------------
# Release-Notes ermitteln (Datei > README-Changelog-Zeile > Fallback)
# ---------------------------------------------------------------------------
if [ -n "$NOTES_FILE" ]; then
    [ -f "$NOTES_FILE" ] || die "notes-file '${NOTES_FILE}' nicht gefunden."
    NOTES="$(cat "$NOTES_FILE")"
else
    # Changelog-Zeile "| <version> | <text> |" aus README ziehen, Text isolieren.
    NOTES="$(awk -F'|' -v v="$VERSION" '
        { gsub(/^[ \t]+|[ \t]+$/, "", $2) }
        $2 == v { s=$3; sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); print s; exit }
    ' README.md)"
    [ -n "$NOTES" ] || NOTES="Axis_Kamera_Discovery ${VERSION}"
fi

# ---------------------------------------------------------------------------
# Token aus ~/.git-credentials lesen (NIE ausgeben)
# ---------------------------------------------------------------------------
[ -f "$CRED_FILE" ] || die "Kein ${CRED_FILE} - kein Forgejo-Token verfuegbar."
# git speichert das Schema als http:// (nicht https://) - Schema locker matchen.
TOKEN="$(sed -n "s#^https\\?://${API_OWNER}:\\([^@]*\\)@${CRED_HOST}.*#\\1#p" "$CRED_FILE" | head -n1)"
[ -n "$TOKEN" ] || die "Token fuer ${API_OWNER}@${CRED_HOST} nicht in ${CRED_FILE} gefunden."

# gemeinsamer curl-Aufruf gegen die selbst-signierte API
api() { curl -ksS -H "Authorization: token ${TOKEN}" "$@"; }
REL_URL="${API_BASE}/api/v1/repos/${API_OWNER}/${API_REPO}/releases"

if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] Tag ${TAG} anlegen+pushen, Release anlegen, Asset ${APPIMAGE} hochladen."
    info "[dry-run] Release-Notes:"
    echo "----"; echo "$NOTES"; echo "----"
    exit 0
fi

# ---------------------------------------------------------------------------
# 1) Tag anlegen (idempotent) + pushen
# ---------------------------------------------------------------------------
if git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null; then
    info "Tag ${TAG} existiert bereits lokal - ueberspringe Anlegen."
else
    git tag -a "$TAG" -m "$TAG"
    info "Tag ${TAG} angelegt."
fi
git push -q "$GIT_REMOTE" "refs/tags/${TAG}"
info "Tag ${TAG} gepusht."

# ---------------------------------------------------------------------------
# 2) Release-Objekt anlegen (falls schon vorhanden: dessen id nehmen)
# ---------------------------------------------------------------------------
# JSON-Body sicher aus Strings bauen (python3 uebernimmt das Escaping).
BODY="$(TAG="$TAG" VER="$VERSION" NOTES="$NOTES" python3 -c '
import json, os
print(json.dumps({"tag_name": os.environ["TAG"],
                  "name": os.environ["VER"],
                  "body": os.environ["NOTES"]}))')"

RESP="$(api -H "Content-Type: application/json" -X POST -d "$BODY" "$REL_URL")"
REL_ID="$(printf '%s' "$RESP" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("id",""))
except Exception: print("")')"

if [ -z "$REL_ID" ]; then
    # evtl. existiert das Release schon -> per Tag nachschlagen
    REL_ID="$(api "${REL_URL}/tags/${TAG}" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("id",""))
except Exception: print("")')"
fi
[ -n "$REL_ID" ] || die "Konnte Release nicht anlegen/finden. Antwort: ${RESP}"
info "Release-ID: ${REL_ID}"

# ---------------------------------------------------------------------------
# 3) AppImage als Asset anhaengen (gleichnamiges vorher entfernen -> re-upload)
# ---------------------------------------------------------------------------
EXIST_ID="$(api "${REL_URL}/${REL_ID}/assets" | python3 -c '
import json, sys, os
name = os.path.basename(os.environ["APPIMAGE"])
try: data = json.load(sys.stdin)
except Exception: data = []
print(next((str(a["id"]) for a in data if a.get("name")==name), ""))' APPIMAGE="$APPIMAGE")

if [ -n "$EXIST_ID" ]; then
    api -X DELETE "${REL_URL}/${REL_ID}/assets/${EXIST_ID}" >/dev/null
    info "Vorhandenes gleichnamiges Asset entfernt (${EXIST_ID})."
fi

api -X POST \
    -F "attachment=@${APPIMAGE};type=application/octet-stream" \
    "${REL_URL}/${REL_ID}/assets?name=${APPIMAGE}" >/dev/null
info "Asset ${APPIMAGE} hochgeladen."

info "Fertig: Release ${TAG} steht auf Forgejo bereit."
