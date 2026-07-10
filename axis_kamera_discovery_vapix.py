# Axis_Kamera_Discovery - VAPIX-Client zum Aendern von Kamera-Einstellungen.
# Copyright (C) 2026 Mirik
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Kommunikation mit Axis-Kameras ueber die VAPIX-HTTP-API.

Nutzt nur die Standardbibliothek (urllib/ssl/hashlib), damit im AppImage keine
weiteren Pakete noetig sind. HTTPS wird mit einem ungeprueften SSL-Kontext
gesprochen, weil Axis-Geraete in der Regel selbstsignierte Zertifikate nutzen.
Authentifizierung per HTTP-Digest (mit Basic als Rueckfall).
"""

import csv
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Axis-Geraete haben meist selbstsignierte Zertifikate -> Zertifikatspruefung aus.
_SSL_CONTEXT = ssl._create_unverified_context()

# Standard-Ports je Schema
DEFAULT_PORTS = {"http": 80, "https": 443}


class VapixError(Exception):
    """Fehler bei einem VAPIX-Aufruf (Netzwerk, Auth oder Geraeteantwort)."""


def _build_opener(host_port, username, password, auth=True):
    """Opener mit ungepruefter HTTPS-Verbindung.

    Mit auth=True zusaetzlich Digest-/Basic-Auth; mit auth=False ganz ohne
    Authentifizierung (fuer werksneue Geraete ohne gesetztes Passwort).
    """
    handlers = [urllib.request.HTTPSHandler(context=_SSL_CONTEXT)]
    if auth:
        pwmgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        # Realm None -> gilt fuer alle; URL ohne Schema deckt http und https ab.
        pwmgr.add_password(None, host_port, username, password)
        handlers = [
            urllib.request.HTTPDigestAuthHandler(pwmgr),
            urllib.request.HTTPBasicAuthHandler(pwmgr),
        ] + handlers
    return urllib.request.build_opener(*handlers)


def _request(ip, username, password, path, scheme="http", port=None, timeout=10, auth=True):
    """Fuehrt einen GET-Aufruf aus und liefert den Antworttext (str).

    Wirft VapixError bei Netzwerk-/Auth-/HTTP-Fehlern. Mit auth=False ohne
    Authentifizierung (werksneue Geraete).
    """
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}{path}"
    opener = _build_opener(host_port, username, password, auth=auth)
    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        raise VapixError(f"HTTP-Fehler {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        raise VapixError(f"Nicht erreichbar: {exc.reason}")
    except (TimeoutError, OSError) as exc:
        raise VapixError(f"Verbindungsfehler: {exc}")


def _request_auto(ip, username, password, path, scheme="auto", port=None, timeout=10, auth=True):
    """Wie _request, aber 'auto' probiert erst HTTPS, dann HTTP."""
    if scheme != "auto":
        return _request(ip, username, password, path, scheme, port, timeout, auth)
    try:
        return _request(ip, username, password, path, "https", port, timeout, auth)
    except VapixError:
        return _request(ip, username, password, path, "http", port, timeout, auth)


def _post_form(ip, username, password, path, fields, scheme, port, timeout):
    """POSTet x-www-form-urlencoded und liefert den Antworttext."""
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}{path}"
    body = urllib.parse.urlencode(fields).encode("utf-8")
    opener = _build_opener(host_port, username, password)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        raise VapixError(f"HTTP-Fehler {exc.code}: {exc.reason}")
    except urllib.error.URLError as exc:
        raise VapixError(f"Nicht erreichbar: {exc.reason}")
    except (TimeoutError, OSError) as exc:
        raise VapixError(f"Verbindungsfehler: {exc}")


def _post_form_auto(ip, username, password, path, fields, scheme="auto", port=None, timeout=30):
    """Wie _post_form, aber 'auto' probiert erst HTTPS, dann HTTP."""
    if scheme != "auto":
        return _post_form(ip, username, password, path, fields, scheme, port, timeout)
    try:
        return _post_form(ip, username, password, path, fields, "https", port, timeout)
    except VapixError:
        return _post_form(ip, username, password, path, fields, "http", port, timeout)


def _http_error_detail(exc) -> str:
    """Liefert eine kurze, lesbare Ursache aus dem Body einer HTTPError-Antwort.

    AXIS-JSON-APIs betten die eigentliche Fehlermeldung meist als JSON
    (``error.message``) oder Klartext in den Body ein — auch bei HTTP 500.
    """
    try:
        raw = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 - Body evtl. nicht lesbar
        return ""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except ValueError:
        return raw[:200]
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)[:200]
    if err:
        return str(err)[:200]
    return raw[:200]


def _post_json(ip, username, password, path, obj, scheme, port, timeout):
    """POSTet einen JSON-Body und liefert die geparste JSON-Antwort (Dict).

    Fuer die JSON-Steuer-APIs neuerer AXIS-Funktionen (z. B. VMD4). Leere Antworten
    ergeben ``{}``; nicht-JSON-Antworten werfen VapixError.
    """
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}{path}"
    body = json.dumps(obj).encode("utf-8")
    opener = _build_opener(host_port, username, password)
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        # AXIS-JSON-APIs liefern die eigentliche Ursache oft im Fehler-Body mit --
        # unbedingt anzeigen (z. B. bei 500 vom VMD4-control.cgi).
        detail = _http_error_detail(exc)
        raise VapixError(f"HTTP-Fehler {exc.code}: {exc.reason}"
                         + (f" — {detail}" if detail else ""))
    except urllib.error.URLError as exc:
        raise VapixError(f"Nicht erreichbar: {exc.reason}")
    except (TimeoutError, OSError) as exc:
        raise VapixError(f"Verbindungsfehler: {exc}")
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except ValueError:
        raise VapixError(f"Unerwartete Antwort: {text.strip()[:200]}")


def _post_json_auto(ip, username, password, path, obj, scheme="auto", port=None, timeout=30):
    """Wie _post_json, aber 'auto' probiert erst HTTPS, dann HTTP."""
    if scheme != "auto":
        return _post_json(ip, username, password, path, obj, scheme, port, timeout)
    try:
        return _post_json(ip, username, password, path, obj, "https", port, timeout)
    except VapixError:
        return _post_json(ip, username, password, path, obj, "http", port, timeout)


def is_unconfigured(ip, scheme="auto", port=None, timeout=10):
    """True, wenn das Geraet ohne Authentifizierung antwortet (Auslieferungszustand).

    Ein werksneues Axis-Geraet hat kein Passwort gesetzt und beantwortet einen
    unauthentifizierten VAPIX-Aufruf mit 200; ein konfiguriertes Geraet mit 401.
    """
    schemes = ["https", "http"] if scheme == "auto" else [scheme]
    path = "/axis-cgi/pwdgrp.cgi?action=get"
    for sc in schemes:
        p = port if port else DEFAULT_PORTS[sc]
        url = f"{sc}://{ip}:{p}{path}"
        opener = _build_opener(f"{ip}:{p}", "", "", auth=False)
        try:
            with opener.open(url, timeout=timeout) as resp:
                resp.read()
            return True  # 200 ohne Auth -> unkonfiguriert
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return False  # Auth verlangt -> konfiguriert
            continue  # anderer HTTP-Fehler: naechstes Schema versuchen
        except (urllib.error.URLError, TimeoutError, OSError):
            continue  # nicht erreichbar ueber dieses Schema
    return False


def _parse_param_list(text):
    """Wandelt die 'root.Gruppe.Name=Wert'-Zeilen von param.cgi in ein Dict."""
    result = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def get_device_info(ip, username, password, scheme="auto", port=None, timeout=10):
    """Liest Modell und Seriennummer (lesender Test der Verbindung/Auth)."""
    path = (
        "/axis-cgi/param.cgi?action=list"
        "&group=Brand.ProdShortName,Properties.System.SerialNumber"
    )
    params = _parse_param_list(
        _request_auto(ip, username, password, path, scheme, port, timeout)
    )
    return {
        "model": params.get("root.Brand.ProdShortName", "?"),
        "serial": params.get("root.Properties.System.SerialNumber", "?"),
    }


def _update_params(ip, username, password, params, scheme, port, timeout):
    """Ruft param.cgi?action=update mit den uebergebenen Parametern auf."""
    query = urllib.parse.urlencode(params)
    path = f"/axis-cgi/param.cgi?action=update&{query}"
    text = _request_auto(ip, username, password, path, scheme, port, timeout)
    # Erfolgreiche Updates antworten mit "OK"; Fehler beginnen mit "# Error".
    if "OK" not in text:
        raise VapixError(f"Geraet meldete: {text.strip() or '(leere Antwort)'}")
    return text.strip()


def set_static_ip(ip, username, password, new_ip, subnet_mask, gateway,
                  scheme="auto", port=None, timeout=10):
    """Stellt die Kamera auf eine feste IP-Adresse um (BootProto=none)."""
    params = {
        "Network.BootProto": "none",
        "Network.IPAddress": new_ip,
        "Network.SubnetMask": subnet_mask,
    }
    if gateway:
        params["Network.DefaultRouter"] = gateway
    return _update_params(ip, username, password, params, scheme, port, timeout)


def set_dhcp(ip, username, password, scheme="auto", port=None, timeout=10):
    """Stellt die Kamera auf DHCP um (BootProto=dhcp)."""
    params = {"Network.BootProto": "dhcp"}
    return _update_params(ip, username, password, params, scheme, port, timeout)


def next_ip(ip_str, step=1):
    """Liefert die um 'step' erhoehte IPv4-Adresse als String (fuer Start-IP-Modus)."""
    parts = [int(p) for p in ip_str.split(".")]
    if len(parts) != 4:
        raise ValueError(f"Ungueltige IPv4-Adresse: {ip_str}")
    value = (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]
    value += step
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


# =====================================================================
# Benutzerverwaltung (regulaere Axis-Benutzer ueber pwdgrp.cgi)
# =====================================================================

# Rolle -> Axis-Sekundaergruppen (sgrp). "users" ist die Primaergruppe.
USER_ROLES = {
    "administrator": "admin:operator:viewer:ptz",
    "operator": "operator:viewer:ptz",
    "viewer": "viewer",
}

# Werks-/Standard-Zugangsdaten (Benutzer, Passwort), die im Auslieferungszustand
# durchprobiert werden. Aeltere Axis-Geraete (z. B. M7001) antworten auf root/pass.
DEFAULT_CREDENTIALS = [
    ("root", "pass"),
    ("root", "root"),
    ("root", "admin"),
    ("root", ""),
]


def add_user(ip, username, password, new_user, new_password, role="viewer",
             scheme="auto", port=None, timeout=10, authenticate=True):
    """Legt einen regulaeren Axis-Benutzer mit der gewuenschten Rolle an.

    Mit authenticate=False ohne Anmeldung (werksneue Kamera, Erstbenutzer).
    """
    # Der Benutzer "root" gehoert in die Primaergruppe "root" (Pflicht fuer den
    # Erstadmin werksneuer AXIS-OS-Geraete), alle anderen in "users".
    # Wichtig: KEIN comment-Parameter senden -- das laesst den Erstadmin auf
    # AXIS OS < 11.5 fehlschlagen ("not a valid initial admin user").
    params = {
        "action": "add",
        "user": new_user,
        "pwd": new_password,
        "grp": "root" if new_user == "root" else "users",
        "sgrp": USER_ROLES.get(role, "viewer"),
    }
    path = f"/axis-cgi/pwdgrp.cgi?{urllib.parse.urlencode(params)}"
    text = _request_auto(ip, username, password, path, scheme, port, timeout,
                         auth=authenticate)
    if "Error" in text:
        raise VapixError(f"Geraet meldete: {text.strip()}")
    return f"Benutzer '{new_user}' angelegt ({role})"


def set_user_password(ip, username, password, target_user, new_password,
                      scheme="auto", port=None, timeout=10, authenticate=True):
    """Aendert das Passwort eines bestehenden regulaeren Axis-Benutzers."""
    params = {"action": "update", "user": target_user, "pwd": new_password}
    path = f"/axis-cgi/pwdgrp.cgi?{urllib.parse.urlencode(params)}"
    text = _request_auto(ip, username, password, path, scheme, port, timeout,
                         auth=authenticate)
    if "Error" in text:
        raise VapixError(f"Geraet meldete: {text.strip()}")
    return f"Passwort von '{target_user}' geaendert"


def add_or_set_user(ip, username, password, new_user, new_password, role="viewer",
                    factory=False, scheme="auto", port=None, timeout=10):
    """Legt einen Benutzer an; mit factory=True wird der Auslieferungszustand
    behandelt: erst ohne Anmeldung, dann mit Standard-Zugangsdaten; existiert der
    Benutzer bereits, wird stattdessen dessen Passwort gesetzt (als Administrator).
    """
    if not factory:
        return add_user(ip, username, password, new_user, new_password, role,
                        scheme, port, timeout)
    attempts = [("", "", False)] + [(u, p, True) for u, p in DEFAULT_CREDENTIALS]
    last = None
    for usr, pwd, auth in attempts:
        try:
            try:
                return add_user(ip, usr, pwd, new_user, new_password,
                                "administrator", scheme, port, timeout, authenticate=auth)
            except VapixError:
                if not auth:
                    raise  # ohne Anmeldung kein Update-Fallback (moderne Geraete)
                return (set_user_password(ip, usr, pwd, new_user, new_password,
                                          scheme, port, timeout, authenticate=auth)
                        + " (vorhandener Benutzer, Passwort gesetzt)")
        except VapixError as exc:
            last = exc
    raise last if last is not None else VapixError("kein Zugang moeglich")


# =====================================================================
# ONVIF-Benutzerverwaltung (ONVIF Device Service per SOAP)
# =====================================================================

ONVIF_LEVELS = ("Administrator", "Operator", "User")

# ONVIF-Benutzer werden ueber den VAPIX-SOAP-Endpoint /vapix/services verwaltet
# (HTTP-Digest mit VAPIX-Admin), NICHT ueber /onvif/device_service (das ONVIF-
# Auth/WS-Security verlangen wuerde). Genau so macht es der Axis Device Manager.
_ONVIF_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope '
    'xmlns:tt="http://www.onvif.org/ver10/schema" '
    'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
    'xmlns:soap="http://www.w3.org/2003/05/soap-envelope">'
    '<soap:Body>{body}</soap:Body></soap:Envelope>'
)


def _xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&apos;"))


def _extract_soap_fault(text):
    """Holt eine lesbare Fehlermeldung aus einer SOAP-Fault-Antwort.

    Praefix-unabhaengig (z. B. <SOAP-ENV:Text>, <s:Text>, <faultstring>),
    SOAP 1.2 (Reason/Text) zuerst, dann SOAP 1.1 (faultstring).
    """
    for pat in (r"<(?:[\w-]+:)?Text[^>]*>([^<]+)</(?:[\w-]+:)?Text>",
                r"<(?:[\w-]+:)?faultstring[^>]*>([^<]+)</(?:[\w-]+:)?faultstring>"):
        m = re.search(pat, text)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def _onvif_post(ip, username, password, inner, scheme, port, timeout):
    """POSTet einen SOAP-Body an den VAPIX-Services-Endpoint (HTTP-Digest-Auth)."""
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}/vapix/services"
    body = _ONVIF_ENVELOPE.format(body=inner).encode("utf-8")
    opener = _build_opener(host_port, username, password)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "text/xml"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        detail = exc.read().decode("utf-8", errors="replace")
        reason = _extract_soap_fault(detail) or f"HTTP {exc.code}: {exc.reason}"
        raise VapixError(f"ONVIF-Fehler: {reason}")
    except urllib.error.URLError as exc:
        raise VapixError(f"Nicht erreichbar: {exc.reason}")
    except (TimeoutError, OSError) as exc:
        raise VapixError(f"Verbindungsfehler: {exc}")


def _onvif_post_auto(ip, username, password, inner, scheme, port, timeout):
    """Wie _onvif_post, aber 'auto' probiert erst HTTPS, dann HTTP."""
    if scheme != "auto":
        return _onvif_post(ip, username, password, inner, scheme, port, timeout)
    try:
        return _onvif_post(ip, username, password, inner, "https", port, timeout)
    except VapixError:
        return _onvif_post(ip, username, password, inner, "http", port, timeout)


def _check_onvif_response(text):
    """Wirft VapixError, wenn die SOAP-Antwort einen Fault enthaelt."""
    if "Fault" in text:
        raise VapixError(f"ONVIF-Fehler: {_extract_soap_fault(text) or text.strip()}")


def add_onvif_user(ip, username, password, new_user, new_password,
                   level="Administrator", scheme="auto", port=None, timeout=10):
    """Legt einen ONVIF-Benutzer an (ONVIF CreateUsers ueber /vapix/services)."""
    inner = (
        '<tds:CreateUsers xmlns="http://www.onvif.org/ver10/device/wsdl"><User>'
        f"<tt:Username>{_xml_escape(new_user)}</tt:Username>"
        f"<tt:Password>{_xml_escape(new_password)}</tt:Password>"
        f"<tt:UserLevel>{level}</tt:UserLevel>"
        "</User></tds:CreateUsers>"
    )
    _check_onvif_response(
        _onvif_post_auto(ip, username, password, inner, scheme, port, timeout))
    return f"ONVIF-Benutzer '{new_user}' angelegt ({level})"


def set_onvif_user_password(ip, username, password, target_user, new_password,
                            level="Administrator", scheme="auto", port=None, timeout=10):
    """Aendert Passwort/Stufe eines ONVIF-Benutzers (ONVIF SetUser ueber /vapix/services)."""
    inner = (
        '<tds:SetUser xmlns="http://www.onvif.org/ver10/device/wsdl"><User>'
        f"<tt:Username>{_xml_escape(target_user)}</tt:Username>"
        f"<tt:Password>{_xml_escape(new_password)}</tt:Password>"
        f"<tt:UserLevel>{level}</tt:UserLevel>"
        "</User></tds:SetUser>"
    )
    _check_onvif_response(
        _onvif_post_auto(ip, username, password, inner, scheme, port, timeout))
    return f"ONVIF-Passwort von '{target_user}' geaendert"


def parse_user_list(path, onvif=False):
    """Liest eine Benutzerliste fuer den Stapel-Import aus einer Textdatei.

    Format: eine Zeile je Benutzer, kommagetrennt (CSV -- Passwoerter mit Komma
    in Anfuehrungszeichen setzen):

        Name,Passwort[,Rolle]

    Leerzeilen und mit '#' beginnende Zeilen werden uebersprungen. Fehlt die
    Rolle/Stufe, gilt der niedrigste Rang (regulaer 'viewer', ONVIF 'User').
    Gueltige Rollen (regulaer): administrator/operator/viewer; Stufen (ONVIF):
    Administrator/Operator/User -- Gross-/Kleinschreibung egal. Liefert eine
    Liste von Dicts {name, password, role}. Wirft VapixError bei Datei- oder
    Formatfehlern (mit Zeilennummern), damit nichts Halbfertiges angelegt wird.
    """
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except OSError as exc:
        raise VapixError(f"Datei nicht lesbar: {exc}")
    if onvif:
        valid = {lvl.lower(): lvl for lvl in ONVIF_LEVELS}
        default = "User"
    else:
        valid = {role: role for role in USER_ROLES}
        default = "viewer"
    users = []
    errors = []
    for num, row in enumerate(rows, 1):
        if not row:
            continue
        name = row[0].strip()
        if not name or name.startswith("#"):
            continue
        if len(row) < 2 or not row[1]:
            errors.append(f"Zeile {num}: Passwort fehlt")
            continue
        password = row[1]
        role_raw = row[2].strip() if len(row) >= 3 else ""
        if role_raw:
            role = valid.get(role_raw.lower())
            if role is None:
                errors.append(f"Zeile {num}: ungueltige Rolle/Stufe '{role_raw}'")
                continue
        else:
            role = default
        users.append({"name": name, "password": password, "role": role})
    if errors:
        raise VapixError("; ".join(errors))
    if not users:
        raise VapixError("Keine Benutzer in der Datei gefunden.")
    return users


# =====================================================================
# Firmware-Update
# =====================================================================

def _multipart_body(parts):
    """Baut einen multipart/form-data-Body.

    parts: Liste von (name, filename|None, content_type|None, data:bytes|str).
    Liefert (body_bytes, boundary).
    """
    boundary = "----AxisIPUtil" + os.urandom(12).hex()
    bb = boundary.encode("ascii")
    crlf = b"\r\n"
    buf = []
    for name, filename, ctype, data in parts:
        disp = f'form-data; name="{name}"'
        if filename is not None:
            disp += f'; filename="{filename}"'
        buf.append(b"--" + bb)
        buf.append(b"Content-Disposition: " + disp.encode("utf-8"))
        if ctype:
            buf.append(b"Content-Type: " + ctype.encode("ascii"))
        buf.append(b"")
        buf.append(data if isinstance(data, bytes) else data.encode("utf-8"))
    buf.append(b"--" + bb + b"--")
    buf.append(b"")
    return crlf.join(buf), boundary


def _post_multipart(ip, username, password, path, parts, scheme, port, timeout):
    """POSTet einen multipart/form-data-Body und liefert den Antworttext."""
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}{path}"
    body, boundary = _multipart_body(parts)
    opener = _build_opener(host_port, username, password)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_fw_response(resp):
    """Wertet die JSON-Antwort von firmwaremanagement.cgi aus."""
    try:
        obj = json.loads(resp)
    except ValueError:
        # kein JSON -> grobe Heuristik
        if re.search(r"error|fail", resp, re.IGNORECASE):
            raise VapixError(f"Geraet meldete: {resp.strip()[:200]}")
        return "Firmware-Upgrade gestartet"
    if isinstance(obj, dict) and obj.get("error"):
        err = obj["error"]
        raise VapixError(f"Fehler {err.get('code', '?')}: {err.get('message', err)}")
    version = ""
    if isinstance(obj, dict):
        version = obj.get("data", {}).get("firmwareVersion", "")
    return "Firmware aktualisiert" + (f" auf {version}" if version else "")


def _resolve_scheme(ip, username, password, scheme, port, timeout):
    """Ermittelt ein Schema (https/http), ueber das die Kamera erreichbar ist."""
    schemes = ["https", "http"] if scheme == "auto" else [scheme]
    for sc in schemes:
        p = port if port else DEFAULT_PORTS[sc]
        url = f"{sc}://{ip}:{p}/axis-cgi/param.cgi?action=list&group=Properties.Firmware.Version"
        opener = _build_opener(f"{ip}:{p}", username, password)
        try:
            with opener.open(url, timeout=timeout) as r:
                r.read()
            return sc
        except urllib.error.HTTPError:
            return sc  # verbunden (z. B. 401) -> Schema funktioniert
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return None


def _has_firmware_api(ip, username, password, scheme, port, timeout):
    """Prueft mit einem kleinen JSON-Aufruf, ob firmwaremanagement.cgi existiert."""
    p = port if port else DEFAULT_PORTS[scheme]
    url = f"{scheme}://{ip}:{p}/axis-cgi/firmwaremanagement.cgi"
    body = json.dumps({"apiVersion": "1.0", "context": "probe", "method": "status"})
    opener = _build_opener(f"{ip}:{p}", username, password)
    req = urllib.request.Request(url, data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=timeout) as r:
            r.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code not in (404, 501)  # existiert, nur z. B. 401/400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False  # CGI fehlt / Verbindung zurueckgesetzt -> Legacy


def _modern_upgrade(ip, username, password, filename, data, factory_default,
                    scheme, port, timeout):
    payload = json.dumps({
        "apiVersion": "1.0", "context": "axisiputil", "method": "upgrade",
        "params": {"factoryDefaultMode": "hard" if factory_default else "none"},
    })
    parts = [("payload", None, None, payload),
             ("file", filename, "application/octet-stream", data)]
    try:
        resp = _post_multipart(ip, username, password,
                               "/axis-cgi/firmwaremanagement.cgi",
                               parts, scheme, port, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        raise VapixError(f"HTTP-Fehler {exc.code}: {exc.reason}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return "Firmware hochgeladen - Geraet startet neu (bitte Status pruefen)"
    return _parse_fw_response(resp)


def _legacy_upgrade(ip, username, password, filename, data, scheme, port, timeout):
    """Aelterer Upgrade-Weg (firmwareupgrade.cgi) fuer Geraete ohne die JSON-API.

    Aeltere Geraete trennen die Verbindung, sobald sie mit dem Flashen beginnen
    -- das wird daher als Erfolg (Neustart laeuft) gewertet.
    """
    parts = [("file", filename, "application/octet-stream", data)]
    try:
        resp = _post_multipart(ip, username, password, "/axis-cgi/firmwareupgrade.cgi",
                               parts, scheme, port, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise VapixError("Authentifizierung fehlgeschlagen (Benutzer/Passwort?).")
        raise VapixError(f"HTTP-Fehler {exc.code}: {exc.reason}")
    except (urllib.error.URLError, TimeoutError, OSError):
        return "Firmware hochgeladen (Legacy) - Verbindung getrennt, Geraet flasht/startet neu (bitte pruefen)"
    if re.search(r"error|fail", resp, re.IGNORECASE):
        raise VapixError(f"Geraet meldete: {resp.strip()[:200]}")
    return "Firmware hochgeladen (Legacy) - Geraet startet neu"


def upgrade_firmware(ip, username, password, firmware_path, scheme="auto",
                     port=None, timeout=600, factory_default=False):
    """Spielt eine Firmware-Datei auf die Kamera auf.

    Ermittelt zuerst per kleinem Probe-Request, ob die moderne JSON-API
    (firmwaremanagement.cgi) vorhanden ist; sonst Legacy (firmwareupgrade.cgi),
    damit die grosse Datei nicht an einen nicht vorhandenen Endpoint geht. Das
    Geraet startet nach dem Upgrade selbsttaetig neu.
    """
    with open(firmware_path, "rb") as f:
        data = f.read()
    filename = os.path.basename(firmware_path)

    sc = _resolve_scheme(ip, username, password, scheme, port, timeout=15)
    if sc is None:
        raise VapixError("Kamera nicht erreichbar.")
    if _has_firmware_api(ip, username, password, sc, port, timeout=15):
        return _modern_upgrade(ip, username, password, filename, data,
                               factory_default, sc, port, timeout)
    return _legacy_upgrade(ip, username, password, filename, data, sc, port, timeout)


# =====================================================================
# Axis-Device-Manager-Konfigurationsdateien (.cfg / AcmDeviceParameterExport)
# =====================================================================

def parse_adm_config(path):
    """Liest eine ADM-.cfg (XML) und liefert Modell, Firmware, Parameter, Profile.

    Wirft VapixError bei ungueltigem Format.
    """
    try:
        with open(path, "rb") as f:
            root = ET.fromstring(f.read())
    except (OSError, ET.ParseError) as exc:
        raise VapixError(f"Datei nicht lesbar/kein gueltiges XML: {exc}")
    if root.tag != "AcmDeviceParameterExport":
        raise VapixError("Keine ADM-Konfigurationsdatei (AcmDeviceParameterExport).")

    params = {}
    for p in root.findall("./ParameterList/Parameter"):
        name = (p.findtext("Name") or "").strip()
        if name:
            params[name] = p.findtext("Value") or ""
    profiles = []
    for sp in root.findall("./StreamProfileList/StreamProfile"):
        name = (sp.findtext("Name") or "").strip()
        if name:
            profiles.append({
                "name": name,
                "description": sp.findtext("Description") or "",
                "parameters": sp.findtext("Parameters") or "",
            })
    # Bewegungserkennung (VMD4): ADM legt die Konfiguration als JSON-Blob unter
    # <Vmd4><Vmd4Configuration> ab (kein param.cgi -> eigene Steuer-API).
    vmd4 = None
    vmd4_text = (root.findtext("./Vmd4/Vmd4Configuration") or "").strip()
    if vmd4_text:
        try:
            vmd4 = json.loads(vmd4_text)
        except ValueError as exc:
            raise VapixError(f"Vmd4-Konfiguration ist kein gueltiges JSON: {exc}")
    return {
        "model": root.findtext("Model") or "",
        "firmware": root.findtext("FirmwareVersion") or "",
        "parameters": params,
        "profiles": profiles,
        "vmd4": vmd4,
    }


# Schreibgeschuetzte VAPIX-Parametergruppen: param.cgi?action=update akzeptiert sie
# nicht. AXIS-Device-Manager-Exporte schreiben sie dennoch mit (dumpen alles) --
# wird die Gruppe mitgesendet, lehnt die Kamera den GESAMTEN Update-Batch ab
# (AXIS OS 12: HTTP 401 "Basic realm=..."). Daher vor dem Anwenden herausfiltern.
READONLY_PARAM_PREFIXES = ("Properties.",)


def _writable_params(params):
    """Entfernt schreibgeschuetzte (Properties.*) Parameter aus einem Param-Dict."""
    return {k: v for k, v in params.items()
            if not k.startswith(READONLY_PARAM_PREFIXES)}


def apply_parameters(ip, username, password, params, scheme="auto", port=None, timeout=30):
    """Setzt eine Reihe von param.cgi-Parametern (per POST) in einem Aufruf.

    Schreibgeschuetzte ``Properties.*``-Parameter werden ignoriert (sonst weist die
    Kamera den kompletten Batch mit 401 ab).
    """
    params = _writable_params(params)
    if not params:
        return 0
    fields = {"action": "update"}
    fields.update(params)
    text = _post_form_auto(ip, username, password, "/axis-cgi/param.cgi",
                           fields, scheme, port, timeout)
    if re.search(r"#\s*Error|^Error", text, re.IGNORECASE | re.MULTILINE):
        raise VapixError(f"param.cgi meldete: {text.strip()[:200]}")
    return len(params)


def _existing_stream_profiles(ip, username, password, scheme, port, timeout):
    """Liefert {Profilname: 'S#'} der vorhandenen Stream-Profile (param.cgi).

    Funktioniert sowohl bei modernen als auch aelteren Geraeten -- beide pflegen
    die Profile im param.cgi-Baum 'StreamProfile.S#'.
    """
    text = _request_auto(ip, username, password,
                         "/axis-cgi/param.cgi?action=list&group=StreamProfile",
                         scheme, port, timeout)
    mapping = {}
    for line in text.splitlines():
        m = re.match(r"root\.StreamProfile\.(S\d+)\.Name=(.+)$", line.strip())
        if m:
            mapping[m.group(2).strip()] = m.group(1)
    return mapping


def _sp_update(ip, username, password, sid, profile, scheme, port, timeout):
    """Ueberschreibt ein vorhandenes Profil StreamProfile.<sid> in place."""
    fields = {
        "action": "update",
        f"StreamProfile.{sid}.Name": profile["name"],
        f"StreamProfile.{sid}.Description": profile["description"],
        f"StreamProfile.{sid}.Parameters": profile["parameters"],
    }
    text = _post_form(ip, username, password, "/axis-cgi/param.cgi",
                      fields, scheme, port, timeout)
    if re.search(r"#\s*Error|failed", text, re.IGNORECASE):
        raise VapixError(f"Profil '{profile['name']}': {text.strip()[:120]}")


def _sp_add(ip, username, password, profile, scheme, port, timeout):
    """Legt ein neues Stream-Profil per param.cgi an (modern wie legacy)."""
    fields = {
        "action": "add",
        "template": "streamprofile",
        "group": "StreamProfile",
        "StreamProfile.S.Name": profile["name"],
        "StreamProfile.S.Description": profile["description"],
        "StreamProfile.S.Parameters": profile["parameters"],
    }
    text = _post_form(ip, username, password, "/axis-cgi/param.cgi",
                      fields, scheme, port, timeout)
    if re.search(r"#\s*Error|failed", text, re.IGNORECASE):
        raise VapixError(f"Profil '{profile['name']}': {text.strip()[:120]}")


def apply_stream_profiles(ip, username, password, profiles, scheme, port, timeout):
    """Wendet Stream-Profile an: vorhandene (gleicher Name) werden ueberschrieben,
    neue angelegt. Einheitlich ueber param.cgi. Liefert
    (angelegt, ueberschrieben, fehlgeschlagen).
    """
    if not profiles:
        return (0, 0, 0)
    existing = _existing_stream_profiles(ip, username, password, scheme, port, timeout)
    created = updated = failed = 0
    for prof in profiles:
        try:
            sid = existing.get(prof["name"])
            if sid:
                _sp_update(ip, username, password, sid, prof, scheme, port, timeout)
                updated += 1
            else:
                _sp_add(ip, username, password, prof, scheme, port, timeout)
                created += 1
        except VapixError:
            failed += 1
    return (created, updated, failed)


# ---------------------------------------------------------------------
# VMD4 (Video Motion Detection 4) — die ACAP-Anwendung hat eine eigene JSON-
# Steuer-API (nicht param.cgi). ADM exportiert/importiert die Konfiguration darueber.
# ---------------------------------------------------------------------
VMD4_CONTROL_PATH = "/local/vmd/control.cgi"
VMD4_API_VERSION = "1.4"
VMD4_PACKAGE = "vmd"


def _app_control(ip, username, password, action, package, scheme, port, timeout):
    """Startet/stoppt eine ACAP-Anwendung ueber applications/control.cgi.

    Liefert den (Klartext-)Antworttext. Wirft VapixError bei HTTP-/Netzwerkfehler.
    """
    path = f"/axis-cgi/applications/control.cgi?action={action}&package={package}"
    return _request_auto(ip, username, password, path, scheme, port, timeout)


def _vmd4_ping(ip, username, password, scheme, port, timeout):
    """True, wenn die VMD4-Steuer-API antwortet (App laeuft). Ein gestopptes ACAP
    liefert an seinem control.cgi einen generischen HTTP 500."""
    try:
        data = _post_json_auto(
            ip, username, password, VMD4_CONTROL_PATH,
            {"apiVersion": VMD4_API_VERSION, "method": "getSupportedVersions"},
            scheme, port, timeout)
        return isinstance(data, dict) and (
            "data" in data or "apiVersion" in data or "error" in data)
    except VapixError:
        return False


def _ensure_vmd_running(ip, username, password, scheme, port, timeout):
    """Stellt sicher, dass die VMD-Anwendung laeuft — sonst antwortet ihr
    control.cgi mit HTTP 500. Startet sie bei Bedarf und wartet, bis die Steuer-API
    erreichbar ist. Wirft VapixError, wenn das nicht gelingt.
    """
    if _vmd4_ping(ip, username, password, scheme, port, timeout):
        return
    try:
        _app_control(ip, username, password, "start", VMD4_PACKAGE, scheme, port, timeout)
    except VapixError as exc:
        raise VapixError(
            "VMD4-Anwendung ist nicht aktiv und liess sich nicht starten "
            f"({exc}). Ist 'AXIS Video Motion Detection' auf der Kamera installiert?")
    for _ in range(8):                     # App braucht nach dem Start einen Moment
        time.sleep(1)
        if _vmd4_ping(ip, username, password, scheme, port, timeout):
            return
    raise VapixError("VMD4-Anwendung wurde gestartet, antwortet aber nicht "
                     "rechtzeitig — bitte erneut versuchen.")


def _vmd4_api_version(ip, username, password, scheme, port, timeout):
    """Ermittelt die hoechste von der Kamera unterstuetzte VMD4-API-Version.

    Verschiedene Firmware unterstuetzt verschiedene Versionen. Faellt bei nicht
    verfuegbarer Auskunft auf ``VMD4_API_VERSION`` zurueck. (getSupportedVersions
    selbst verlangt ein ``apiVersion``-Feld, sonst Fehler 2003.)
    """
    try:
        data = _post_json_auto(
            ip, username, password, VMD4_CONTROL_PATH,
            {"apiVersion": "1.0", "method": "getSupportedVersions"},
            scheme, port, timeout)
        versions = (data.get("data") or {}).get("apiVersions") or []
    except VapixError:
        versions = []
    valid = [v for v in versions if isinstance(v, str)
             and all(p.isdigit() for p in v.split("."))]
    if valid:
        return max(valid, key=lambda v: tuple(int(p) for p in v.split(".")))
    return VMD4_API_VERSION


def apply_vmd4_config(ip, username, password, vmd4, scheme="auto", port=None, timeout=30):
    """Wendet eine VMD4-(Bewegungserkennung)-Konfiguration an.

    'vmd4' ist das geparste Konfigurationsobjekt (parse_adm_config()['vmd4'] —
    cameras/profiles/…). Startet bei Bedarf zuerst die VMD-Anwendung und nutzt dann
    die JSON-Steuer-API (POST /local/vmd/control.cgi, method 'setConfiguration').
    Wirft VapixError, wenn die Anwendung fehlt/nicht startet oder die Konfiguration
    abgelehnt wird.
    """
    _ensure_vmd_running(ip, username, password, scheme, port, timeout)
    api_version = _vmd4_api_version(ip, username, password, scheme, port, timeout)
    body = {"apiVersion": api_version, "context": "axis-discovery",
            "method": "setConfiguration", "params": vmd4}
    data = _post_json_auto(ip, username, password, VMD4_CONTROL_PATH, body,
                           scheme, port, timeout)
    err = data.get("error") if isinstance(data, dict) else None
    if err:
        detail = err.get("message") if isinstance(err, dict) else err
        raise VapixError(f"VMD4 lehnte die Konfiguration ab: {detail}")
    return True


def read_vmd4_config(ip, username, password, scheme="auto", port=None, timeout=30):
    """Liest die aktuelle VMD4-(Bewegungserkennung)-Konfiguration (getConfiguration).

    Liefert das Konfigurationsobjekt (cameras/profiles/…) oder ``None``, wenn die
    VMD-Anwendung nicht vorhanden/aktiv ist. **Ohne Seiteneffekt** — anders als der
    Import wird die App hier nicht gestartet (ein gestopptes ACAP liefert 500, das
    wird als „nicht verfuegbar" behandelt).
    """
    try:
        api_version = _vmd4_api_version(ip, username, password, scheme, port, timeout)
        data = _post_json_auto(
            ip, username, password, VMD4_CONTROL_PATH,
            {"apiVersion": api_version, "context": "axis-discovery",
             "method": "getConfiguration"},
            scheme, port, timeout)
    except VapixError:
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    cfg = data.get("data")
    return cfg if isinstance(cfg, dict) else None


def apply_adm_config(ip, username, password, config, scheme="auto", port=None,
                     timeout=30, with_profiles=True):
    """Wendet eine geparste ADM-Konfiguration an (Parameter, optional Profile,
    optional Bewegungserkennung/VMD4).

    'config' ist das Dict aus parse_adm_config(). Liefert eine Ergebnis-Meldung.
    Schlaegt die VMD4-Uebernahme fehl, wird VapixError geworfen (die Meldung nennt
    zusaetzlich, was zuvor bereits erfolgreich angewendet wurde).
    """
    sc = _resolve_scheme(ip, username, password, scheme, port, timeout=15) or scheme
    count = apply_parameters(ip, username, password, config.get("parameters", {}),
                             sc, port, timeout)
    msg = f"{count} Parameter angewendet"
    if with_profiles and config.get("profiles"):
        created, updated, failed = apply_stream_profiles(
            ip, username, password, config["profiles"], sc, port, timeout)
        msg += (f"; Profile: {created} angelegt, {updated} ueberschrieben, "
                f"{failed} fehlgeschlagen")
    if config.get("vmd4") is not None:
        try:
            apply_vmd4_config(ip, username, password, config["vmd4"], sc, port, timeout)
            msg += "; Bewegungserkennung (VMD4) angewendet"
        except VapixError as exc:
            raise VapixError(f"{msg}; Bewegungserkennung (VMD4) fehlgeschlagen: {exc}")
    return msg


# ---------------------------------------------------------------------
# Konfiguration AUSLESEN und als ADM-.cfg speichern (Umkehrung von oben)
# ---------------------------------------------------------------------

def _stream_profiles_from_params(full_params):
    """Baut die Stream-Profil-Liste aus dem vollstaendigen param.cgi-Baum.

    'full_params' ist {root.Gruppe.Name: Wert}. Liefert je StreamProfile.S#
    ein Dict {name, description, parameters} -- gleiches Format wie
    parse_adm_config()['profiles'].
    """
    sids = {}
    for key, value in full_params.items():
        m = re.match(r"root\.StreamProfile\.(S\d+)\.(Name|Description|Parameters)$", key)
        if m:
            sids.setdefault(m.group(1), {})[m.group(2)] = value
    profiles = []
    for sid in sorted(sids):
        d = sids[sid]
        name = (d.get("Name") or "").strip()
        if name:
            profiles.append({
                "name": name,
                "description": d.get("Description", ""),
                "parameters": d.get("Parameters", ""),
            })
    return profiles


def read_device_config(ip, username, password, scheme="auto", port=None, timeout=30):
    """Liest die komplette Geraetekonfiguration (param.cgi?action=list).

    Liefert ein Dict im selben Format wie parse_adm_config() (model, firmware,
    parameters, profiles). Die Parameternamen sind ohne 'root.'-Praefix
    gespeichert -- genau so, wie param.cgi?action=update sie erwartet und die
    .cfg-Datei sie ablegt, sodass write_adm_config()/parse_adm_config()/
    apply_adm_config() einen sauberen Round-Trip ergeben.
    """
    text = _request_auto(ip, username, password,
                         "/axis-cgi/param.cgi?action=list", scheme, port, timeout)
    full = _parse_param_list(text)
    if not full:
        raise VapixError("Keine Parameter erhalten (leere Antwort von param.cgi).")
    params = {}
    for key, value in full.items():
        if key.startswith("root."):
            params[key[len("root."):]] = value
    return {
        "model": full.get("root.Brand.ProdShortName", ""),
        "firmware": full.get("root.Properties.Firmware.Version", ""),
        "parameters": params,
        "profiles": _stream_profiles_from_params(full),
        "vmd4": read_vmd4_config(ip, username, password, scheme, port, timeout),
    }


def write_adm_config(path, config, selected_params=None, with_profiles=True,
                     with_vmd4=True):
    """Schreibt eine ADM-.cfg (AcmDeviceParameterExport) aus einer Konfiguration.

    'config' ist das Dict aus read_device_config()/parse_adm_config(). Ist
    'selected_params' (eine Menge von Namen) gesetzt, werden nur diese
    Parameter exportiert, sonst alle. 'with_profiles' steuert die Stream-Profile,
    'with_vmd4' die Bewegungserkennung (nur geschrieben, wenn ``config['vmd4']``
    vorhanden ist). Liefert die Anzahl geschriebener Parameter.
    """
    params = config.get("parameters", {})
    names = [n for n in sorted(params)
             if selected_params is None or n in selected_params]
    root = ET.Element("AcmDeviceParameterExport")
    ET.SubElement(root, "Model").text = config.get("model", "") or ""
    ET.SubElement(root, "FirmwareVersion").text = config.get("firmware", "") or ""
    plist = ET.SubElement(root, "ParameterList")
    for name in names:
        p = ET.SubElement(plist, "Parameter")
        ET.SubElement(p, "Name").text = name
        ET.SubElement(p, "Value").text = params[name]
    splist = ET.SubElement(root, "StreamProfileList")
    if with_profiles:
        for prof in config.get("profiles", []):
            sp = ET.SubElement(splist, "StreamProfile")
            ET.SubElement(sp, "Name").text = prof.get("name", "")
            ET.SubElement(sp, "Description").text = prof.get("description", "")
            ET.SubElement(sp, "Parameters").text = prof.get("parameters", "")
    # Bewegungserkennung (VMD4) als eigener Block, kompaktes JSON wie im ADM-Export.
    if with_vmd4 and config.get("vmd4") is not None:
        ET.SubElement(root, "Vmd2")
        vmd4 = ET.SubElement(root, "Vmd4")
        ET.SubElement(vmd4, "Vmd4Configuration").text = json.dumps(
            config["vmd4"], separators=(",", ":"))
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    try:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    except OSError as exc:
        raise VapixError(f"Datei nicht schreibbar: {exc}")
    return len(names)
