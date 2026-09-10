#!/usr/bin/env bash
# release.sh - Formalisiert das Forgejo-Release fuer Axis_Kamera_Discovery.
#
# Ein gepushter Git-Tag "vX" ist bei Forgejo NOCH KEIN Release-Objekt. Dieses
# Skript erledigt die komplette Kette:
#   1. Vorbedingungen pruefen (sauberer Baum, HEAD gepusht, AppImage vorhanden)
#   2. annotierten Tag  vX  anlegen (falls noch nicht vorhanden) und pushen
#   3. Release-Objekt ueber die Forgejo-HTTP-API anlegen (HTTPS, ggf.
#      selbst-signiert -> curl -k), Release-Notes aus dem README-Changelog
#   4. das gebaute AppImage als Asset anhaengen - und, falls in dist/ eine
#      Windows-.exe zur aktuellen Version liegt (Axis_Kamera_Discovery[_cli]_<ver>.exe),
#      diese gleich mit
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
#   * Token: $GITHUB_TOKEN, sonst Token-Datei ($GITHUB_TOKEN_FILE bzw.
#            ~/.config/axis_kamera_discovery/github_token), sonst
#            ~/.git-credentials-Zeile fuer github.com, sonst "gh auth token"
#   * Slug:  $GITHUB_SLUG, sonst das github.com-Ziel des Forgejo-Push-Mirrors,
#            sonst <github-user>/<repo-name>
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

# Hochzuladende Assets: AppImage + passende Windows-Exes aus dist/ (nur solche,
# deren Dateiname mit _<VERSION>.exe endet - also zur aktuellen Version gehoert;
# die PyInstaller-Spec haengt __version__ an: Axis_Kamera_Discovery[_cli]_<ver>.exe).
ASSETS=("$APPIMAGE")
shopt -s nullglob
for exe in dist/*_"${VERSION}".exe; do ASSETS+=("$exe"); done
shopt -u nullglob
if [ "${#ASSETS[@]}" -gt 1 ]; then
    info "Windows-Exes (dist/, Version ${VERSION}): ${ASSETS[*]:1}"
else
    info "Windows-Exe: keine passende in dist/ (nur AppImage wird veroeffentlicht)."
fi

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

# Ein Asset an das Forgejo-Release haengen (gleichnamiges vorher entfernen).
forgejo_put_asset() {  # <datei>
    local f="$1" base ex
    base="$(basename "$f")"
    ex="$(api "${REL_URL}/${REL_ID}/assets" | NAME="$base" python3 -c '
import json, sys, os
name = os.environ["NAME"]
try: data = json.load(sys.stdin)
except Exception: data = []
out = ""
for a in (data if isinstance(data, list) else []):
    if a.get("name") == name:
        out = str(a["id"]); break
print(out)')"
    if [ -n "$ex" ]; then
        api -X DELETE "${REL_URL}/${REL_ID}/assets/${ex}" >/dev/null
        info "Forgejo: altes Asset ${base} entfernt (${ex})."
    fi
    api -X POST -F "attachment=@${f};type=application/octet-stream" \
        "${REL_URL}/${REL_ID}/assets?name=${base}" >/dev/null
    info "Forgejo: Asset ${base} hochgeladen."
}

if [ "$DRY_RUN" = 1 ]; then
    info "[dry-run] Tag ${TAG} anlegen+pushen, Release anlegen, Assets hochladen: ${ASSETS[*]}"
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
# 3) Assets anhaengen: AppImage + evtl. passende Windows-Exes aus dist/
# ---------------------------------------------------------------------------
for a in "${ASSETS[@]}"; do forgejo_put_asset "$a"; done

info "Fertig: Release ${TAG} steht auf Forgejo bereit."

# ---------------------------------------------------------------------------
# 5) GitHub-Release (optional). Ein Push-Mirror uebertraegt nur Refs - Releases
#    und Anhaenge muessen separat hoch. Laeuft nur, wenn ein GitHub-Token +
#    Slug auffindbar sind; sonst wird der Schritt uebersprungen.
# ---------------------------------------------------------------------------
github_release() {
    local token ghuser slug cred tf
    # Token, in dieser Reihenfolge:
    #   1. $GITHUB_TOKEN
    #   2. Token-Datei: $GITHUB_TOKEN_FILE, sonst
    #      ~/.config/axis_kamera_discovery/github_token  (repo-eigenes Token,
    #      liegt ausserhalb des Repos -> nie mitveroeffentlicht)
    #   3. github.com-Zeile in ~/.git-credentials
    #   4. GitHub-CLI ("gh auth token")
    token="${GITHUB_TOKEN:-}"; ghuser=""
    if [ -z "$token" ]; then
        for tf in "${GITHUB_TOKEN_FILE:-}" "${XDG_CONFIG_HOME:-$HOME/.config}/axis_kamera_discovery/github_token"; do
            [ -n "$tf" ] && [ -f "$tf" ] || continue
            token="$(tr -d ' \t\r\n' < "$tf")"
            [ -n "$token" ] && break
        done
    fi
    if [ -z "$token" ] && [ -f "$CRED_FILE" ]; then
        cred="$(grep -aE '^https?://[^@]+@github\.com' "$CRED_FILE" | head -n1)"
        if [ -n "$cred" ]; then
            ghuser="$(printf '%s\n' "$cred" | sed -E 's#^https?://([^:]+):.*#\1#')"
            token="$(printf '%s\n' "$cred" | sed -E 's#^https?://[^:]+:([^@]+)@.*#\1#')"
        fi
    fi
    [ -n "$token" ] || token="$(gh auth token 2>/dev/null || true)"

    # Slug: $GITHUB_SLUG, sonst das github.com-Ziel des Forgejo-Push-Mirrors,
    # sonst <github-user>/<repo>.
    slug="${GITHUB_SLUG:-}"
    if [ -z "$slug" ]; then
        slug="$(api "${API_BASE}/api/v1/repos/${OWNER}/${REPO}/push_mirrors" | python3 -c '
import json, sys
try: data = json.load(sys.stdin)
except Exception: data = []
for m in (data if isinstance(data, list) else []):
    a = m.get("remote_address", "") if isinstance(m, dict) else ""
    if "github.com/" in a:
        s = a.split("github.com/", 1)[1]
        if s.endswith(".git"): s = s[:-4]
        print(s); break')"
    fi
    [ -n "$slug" ] || slug="${ghuser:+${ghuser}/${REPO}}"

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

    # d) Assets hochladen (AppImage + evtl. Windows-Exes); gleichnamiges vorher
    #    entfernen, danach per SHA-256 gegenpruefen (curl >=7.76 entfernt den
    #    Authorization-Kopf beim Redirect auf S3 selbst).
    gh_put_asset() {  # <datei>
        local f="$1" base ex up aid want got tmp
        base="$(basename "$f")"
        ex="$(gh_api "https://api.github.com/repos/${slug}/releases/${gid}/assets" \
            | NAME="$base" python3 -c '
import json, sys, os
name = os.environ["NAME"]
try: data = json.load(sys.stdin)
except Exception: data = []
out = ""
for a in (data if isinstance(data, list) else []):
    if a.get("name") == name:
        out = str(a["id"]); break
print(out)')"
        if [ -n "$ex" ]; then
            gh_api -X DELETE "https://api.github.com/repos/${slug}/releases/assets/${ex}" >/dev/null
            info "GitHub: altes Asset ${base} entfernt (${ex})."
        fi
        up="$(curl -sS --config <(printf 'header = "Authorization: Bearer %s"\n' "$token") \
            -H "Accept: application/vnd.github+json" -H "Content-Type: application/octet-stream" \
            --data-binary "@${f}" \
            "https://uploads.github.com/repos/${slug}/releases/${gid}/assets?name=${base}")"
        aid="$(printf '%s' "$up" | gh_id)"
        [ -n "$aid" ] || die "GitHub-Asset-Upload ${base} fehlgeschlagen. Antwort: ${up}"
        want="$(sha256sum "$f" | cut -d' ' -f1)"
        tmp="$(mktemp)"
        curl -sSL --config <(printf 'header = "Authorization: Bearer %s"\n' "$token") \
            -H "Accept: application/octet-stream" \
            "https://api.github.com/repos/${slug}/releases/assets/${aid}" -o "$tmp"
        got="$(sha256sum "$tmp" | cut -d' ' -f1)"; rm -f "$tmp"
        [ "$want" = "$got" ] || die "SHA-256 von ${base} weicht ab (lokal ${want} != remote ${got})."
        info "GitHub: Asset ${base} hochgeladen + verifiziert (sha256 ${got})."
    }
    for a in "${ASSETS[@]}"; do gh_put_asset "$a"; done
    info "Fertig: Release ${TAG} steht auch auf GitHub (${slug}) bereit."
}

[ "$NO_GITHUB" = 1 ] || github_release
