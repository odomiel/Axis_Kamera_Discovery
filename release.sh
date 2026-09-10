#!/usr/bin/env bash
# release.sh - Formalisiert das Forgejo-Release fuer Axis_Kamera_Discovery.
#
# Ein gepushter Git-Tag "vX" ist bei Forgejo NOCH KEIN Release-Objekt. Dieses
# Skript erledigt die komplette Kette:
#   1. Vorbedingungen pruefen (sauberer Baum, HEAD gepusht, AppImage vorhanden)
#   2. annotierten Tag  vX  anlegen (falls noch nicht vorhanden) und pushen
#   3. Release-Objekt ueber die Forgejo-HTTP-API anlegen (HTTPS, ggf.
#      selbst-signiert -> curl -k), Release-Notes aus dem README-Changelog
#   4. das gebaute AppImage als Asset anhaengen
#   5. optional dasselbe Release auf GitHub anlegen (nur wenn dort ein
#      Push-Mirror + Token eingerichtet ist) - ein Mirror uebertraegt nur Refs,
#      keine Releases/Anhaenge, daher separat hochladen.
#
# Der Schreib-Token wird aus ~/.git-credentials gelesen und NIE ausgegeben.
#
# Aufruf:
#   ./release.sh                 # Version aus bump_version.py --print
#   ./release.sh --version 26.08.10b1
#   ./release.sh --dry-run       # nur pruefen/anzeigen, nichts veraendern
#   ./release.sh --notes-file X  # Release-Text aus Datei statt aus dem README
#   ./release.sh --no-github     # GitHub-Schritt ueberspringen
#
# GitHub-Ziel (Schritt 5) per Umgebung/Zugangsdaten:
#   * Token: $GITHUB_TOKEN oder ~/.git-credentials-Zeile fuer github.com
#   * Slug:  $GITHUB_SLUG (Konto/Repo), sonst <github-user>/<repo-name>
#
# Copyright (C) 2026 Mirik - GPL-3.0-or-later
set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration. Host, Owner und Token werden NICHT im Skript hinterlegt,
# sondern zur Laufzeit abgeleitet (siehe unten). Alles ueberschreibbar per
# Umgebung: FORGEJO_REMOTE / FORGEJO_BRANCH / FORGEJO_API / FORGEJO_OWNER /
# FORGEJO_REPO.
# ---------------------------------------------------------------------------
CRED_FILE="${HOME}/.git-credentials"
GIT_REMOTE="${FORGEJO_REMOTE:-forgejo}"
GIT_BRANCH="${FORGEJO_BRANCH:-main}"

cd "$(dirname "$(readlink -f "$0")")"

# ---------------------------------------------------------------------------
# Argumente
# ---------------------------------------------------------------------------
VERSION=""
NOTES_FILE=""
DRY_RUN=0
NO_GITHUB=0
while [ $# -gt 0 ]; do
    case "$1" in
        --version)    VERSION="${2:?--version braucht einen Wert}"; shift 2 ;;
        --notes-file) NOTES_FILE="${2:?--notes-file braucht einen Wert}"; shift 2 ;;
        --dry-run)    DRY_RUN=1; shift ;;
        --no-github)  NO_GITHUB=1; shift ;;
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
# Forgejo-Ziel aus der Umgebung ableiten (keine Host-/Owner-Literale im Skript):
#   * Owner/Repo aus der Git-Remote-URL
#   * Host:Port + Token aus ~/.git-credentials (wird nicht mitveroeffentlicht)
# ---------------------------------------------------------------------------
remote_url="$(git remote get-url "$GIT_REMOTE" 2>/dev/null || true)"
rest="${remote_url#*://}"; rest="${rest#*@}"           # Schema + Benutzer weg
rhost="${rest%%[:/]*}"; rpath="${rest#"$rhost"}"
rpath="${rpath#:}"                                     # Doppelpunkt (Port/scp-Form)
case "$rpath" in [0-9]*/*) rpath="${rpath#*/}" ;; esac # numerischen Port weg
rpath="${rpath#/}"; rpath="${rpath%.git}"
OWNER="${FORGEJO_OWNER:-${rpath%%/*}}"
REPO="${FORGEJO_REPO:-${rpath##*/}}"
[ -n "$OWNER" ] && [ -n "$REPO" ] || die "Owner/Repo nicht aus Remote '${GIT_REMOTE}' ableitbar."

# Token + Host:Port aus der passenden ~/.git-credentials-Zeile (NIE ausgeben).
[ -f "$CRED_FILE" ] || die "Kein ${CRED_FILE} - kein Forgejo-Token verfuegbar."
cred_line="$(grep -aE "^https?://${OWNER}:[^@]+@" "$CRED_FILE" | head -n1)"
[ -n "$cred_line" ] || die "Keine Zugangsdaten fuer '${OWNER}' in ${CRED_FILE}."
TOKEN="$(printf '%s\n' "$cred_line" | sed -E 's#^https?://[^:]+:([^@]+)@.*#\1#')"
hostport="$(printf '%s\n' "$cred_line" | sed -E 's#^https?://[^@]+@(.*)$#\1#; s/%3[aA]/:/')"
[ -n "$TOKEN" ] && [ -n "$hostport" ] || die "Token/Host nicht aus ${CRED_FILE} lesbar."
API_BASE="${FORGEJO_API:-https://${hostport}}"

# gemeinsamer curl-Aufruf gegen die (ggf. selbst-signierte) API
api() { curl -ksS -H "Authorization: token ${TOKEN}" "$@"; }
REL_URL="${API_BASE}/api/v1/repos/${OWNER}/${REPO}/releases"

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
EXIST_ID="$(api "${REL_URL}/${REL_ID}/assets" | APPIMAGE="$APPIMAGE" python3 -c '
import json, sys, os
name = os.path.basename(os.environ["APPIMAGE"])
try:
    data = json.load(sys.stdin)
except Exception:
    data = []
out = ""
for a in data:
    if a.get("name") == name:
        out = str(a["id"])
        break
print(out)')"

if [ -n "$EXIST_ID" ]; then
    api -X DELETE "${REL_URL}/${REL_ID}/assets/${EXIST_ID}" >/dev/null
    info "Vorhandenes gleichnamiges Asset entfernt (${EXIST_ID})."
fi

api -X POST \
    -F "attachment=@${APPIMAGE};type=application/octet-stream" \
    "${REL_URL}/${REL_ID}/assets?name=${APPIMAGE}" >/dev/null
info "Asset ${APPIMAGE} hochgeladen."

info "Fertig: Release ${TAG} steht auf Forgejo bereit."

# ---------------------------------------------------------------------------
# 5) GitHub-Release (optional). Ein Push-Mirror uebertraegt nur Refs - Releases
#    und Anhaenge muessen separat hoch. Laeuft nur, wenn ein GitHub-Token +
#    Slug auffindbar sind; sonst wird der Schritt uebersprungen.
# ---------------------------------------------------------------------------
github_release() {
    local token ghuser slug cred
    token="${GITHUB_TOKEN:-}"; ghuser=""
    if [ -z "$token" ] && [ -f "$CRED_FILE" ]; then
        cred="$(grep -aE '^https?://[^@]+@github\.com' "$CRED_FILE" | head -n1)"
        if [ -n "$cred" ]; then
            ghuser="$(printf '%s\n' "$cred" | sed -E 's#^https?://([^:]+):.*#\1#')"
            token="$(printf '%s\n' "$cred" | sed -E 's#^https?://[^:]+:([^@]+)@.*#\1#')"
        fi
    fi
    slug="${GITHUB_SLUG:-${ghuser:+${ghuser}/${REPO}}}"
    if [ -z "$token" ] || [ -z "$slug" ]; then
        info "GitHub nicht konfiguriert (kein Token/Slug) - ueberspringe GitHub-Release."
        return 0
    fi
    info "GitHub-Ziel: ${slug}"

    # Token nur ueber --config (aus einem Builtin-printf) - nie als Argument (ps).
    gh_api() { curl -sS --config <(printf 'header = "Authorization: Bearer %s"\n' "$token") \
        -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "$@"; }
    gh_id() { python3 -c 'import json,sys
try: d=json.load(sys.stdin); print(d.get("id","") if isinstance(d,dict) else "")
except Exception: print("")'; }

    # a) Mirror-Sync anstossen (Forgejo -> GitHub)
    if api -X POST "${API_BASE}/api/v1/repos/${OWNER}/${REPO}/push_mirrors-sync" >/dev/null 2>&1; then
        info "Mirror-Sync angestossen."
    else
        info "Mirror-Sync-Aufruf ohne Erfolg (Mirror evtl. nicht eingerichtet) - versuche trotzdem."
    fi

    # b) Warten, bis der Tag drueben ist (max ~120 s)
    local i code="000"
    for i in $(seq 1 20); do
        code="$(gh_api -o /dev/null -w '%{http_code}' \
            "https://api.github.com/repos/${slug}/git/ref/tags/${TAG}")"
        [ "$code" = "200" ] && break
        sleep 6
    done
    [ "$code" = "200" ] || die "Tag ${TAG} ist nach ~120s nicht auf GitHub (${slug}) - Mirror/Token pruefen."
    info "Tag ${TAG} ist auf GitHub sichtbar."

    # c) Release anlegen (prerelease bei bN-Suffix); falls vorhanden -> id holen
    local pre="false"; case "$VERSION" in *b[0-9]*) pre="true" ;; esac
    local body resp gid
    body="$(TAG="$TAG" VER="$VERSION" NOTES="$NOTES" PRE="$pre" python3 -c '
import json, os
print(json.dumps({"tag_name": os.environ["TAG"], "name": os.environ["VER"],
                  "body": os.environ["NOTES"], "prerelease": os.environ["PRE"]=="true",
                  "draft": False}))')"
    resp="$(gh_api -X POST -d "$body" "https://api.github.com/repos/${slug}/releases")"
    gid="$(printf '%s' "$resp" | gh_id)"
    [ -n "$gid" ] || gid="$(gh_api "https://api.github.com/repos/${slug}/releases/tags/${TAG}" | gh_id)"
    [ -n "$gid" ] || die "GitHub-Release nicht anlegbar/gefunden. Antwort: ${resp}"
    info "GitHub-Release-ID: ${gid}"

    # d) Asset hochladen (gleichnamiges vorher entfernen -> re-upload)
    local ex
    ex="$(gh_api "https://api.github.com/repos/${slug}/releases/${gid}/assets" \
        | APPIMAGE="$APPIMAGE" python3 -c '
import json, sys, os
name = os.path.basename(os.environ["APPIMAGE"])
try: data = json.load(sys.stdin)
except Exception: data = []
out = ""
for a in (data if isinstance(data, list) else []):
    if a.get("name") == name:
        out = str(a["id"]); break
print(out)')"
    if [ -n "$ex" ]; then
        gh_api -X DELETE "https://api.github.com/repos/${slug}/releases/assets/${ex}" >/dev/null
        info "Vorhandenes GitHub-Asset entfernt (${ex})."
    fi
    local up aid
    up="$(curl -sS --config <(printf 'header = "Authorization: Bearer %s"\n' "$token") \
        -H "Accept: application/vnd.github+json" -H "Content-Type: application/octet-stream" \
        --data-binary "@${APPIMAGE}" \
        "https://uploads.github.com/repos/${slug}/releases/${gid}/assets?name=${APPIMAGE}")"
    aid="$(printf '%s' "$up" | gh_id)"
    [ -n "$aid" ] || die "GitHub-Asset-Upload fehlgeschlagen. Antwort: ${up}"
    info "GitHub-Asset hochgeladen (id ${aid})."

    # e) Gegenprobe: zurueckladen und SHA-256 vergleichen (curl >=7.76 entfernt den
    #    Authorization-Kopf beim Redirect auf S3 selbst).
    local want got tmp
    want="$(sha256sum "$APPIMAGE" | cut -d' ' -f1)"
    tmp="$(mktemp)"
    curl -sSL --config <(printf 'header = "Authorization: Bearer %s"\n' "$token") \
        -H "Accept: application/octet-stream" \
        "https://api.github.com/repos/${slug}/releases/assets/${aid}" -o "$tmp"
    got="$(sha256sum "$tmp" | cut -d' ' -f1)"; rm -f "$tmp"
    [ "$want" = "$got" ] || die "SHA-256 des GitHub-Assets weicht ab (lokal ${want} != remote ${got})."
    info "GitHub-Asset verifiziert (sha256 ${got})."
    info "Fertig: Release ${TAG} steht auch auf GitHub (${slug}) bereit."
}

[ "$NO_GITHUB" = 1 ] || github_release
