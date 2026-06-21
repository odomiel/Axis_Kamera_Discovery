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


def _build_opener(host_port, username, password):
    """Opener mit Digest-/Basic-Auth und ungepruefter HTTPS-Verbindung."""
    pwmgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    # Realm None -> gilt fuer alle; URL ohne Schema deckt http und https ab.
    pwmgr.add_password(None, host_port, username, password)
    return urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(pwmgr),
        urllib.request.HTTPBasicAuthHandler(pwmgr),
        urllib.request.HTTPSHandler(context=_SSL_CONTEXT),
    )


def _request(ip, username, password, path, scheme="http", port=None, timeout=10):
    """Fuehrt einen GET-Aufruf aus und liefert den Antworttext (str).

    Wirft VapixError bei Netzwerk-/Auth-/HTTP-Fehlern.
    """
    if port is None:
        port = DEFAULT_PORTS[scheme]
    host_port = f"{ip}:{port}"
    url = f"{scheme}://{host_port}{path}"
    opener = _build_opener(host_port, username, password)
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


def _request_auto(ip, username, password, path, scheme="auto", port=None, timeout=10):
    """Wie _request, aber 'auto' probiert erst HTTPS, dann HTTP."""
    if scheme != "auto":
        return _request(ip, username, password, path, scheme, port, timeout)
    try:
        return _request(ip, username, password, path, "https", port, timeout)
    except VapixError:
        return _request(ip, username, password, path, "http", port, timeout)


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
