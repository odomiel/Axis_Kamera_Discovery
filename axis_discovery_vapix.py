# Axis IP Utility - VAPIX-Client zum Aendern von Kamera-Einstellungen.
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

import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

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
