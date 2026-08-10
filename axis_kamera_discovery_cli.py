# Axis_Kamera_Discovery - findet Axis-Netzwerkkameras per Zeroconf/mDNS.
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

from zeroconf import ServiceBrowser, Zeroconf, IPVersion
import time
import csv
import webbrowser
from prettytable import PrettyTable
import argparse
import getpass
import os
import re

import axis_kamera_discovery_vapix as vapix

# Versionsschema: JJ.MM.TT, bei mehreren Releases am selben Tag b1, b2, ...
# (wird von bump_version.py gepflegt)
__version__ = "26.08.10"

FIELD_NAMES = [
    "Name",
    "IP Adresse: Zeroconfig",
    "IP Adresse: Konfiguriert",
    "IPv6 Adresse",
    "Port",
    "Hostname",
    "MAC-Adresse/Seriennummer",
]

class AxisDiscovery:
    def __init__(self):
        self.zeroconf = Zeroconf()
        self.services = []
        self._seen = set()  # bereits erfasste mDNS-Namen (gegen Doppel-Eintraege)

    def on_service_state_change(self, zeroconf, service_type, name, state_change):
        if state_change is Zeroconf.StateChange.Added:
            self.add_service(zeroconf, service_type, name)

    def add_service(self, zeroconf, service_type, name):
        # Doppelte Ankuendigungen desselben Dienstes ignorieren
        if name in self._seen:
            return
        info = zeroconf.get_service_info(service_type, name)
        if info:
            self._seen.add(name)
            # zeroconf liefert ueber .addresses aus Kompatibilitaetsgruenden nur
            # IPv4 -> IPv4 und IPv6 getrennt ueber parsed_addresses() erkennen.
            ipv4 = info.parsed_addresses(IPVersion.V4Only)
            ipv6 = info.parsed_addresses(IPVersion.V6Only)

            # Filtern Sie den zusätzlichen Teil aus dem Namen
            name = name.replace("._axis-video._tcp.local.", "")
            # Seriennummer/MAC aus dem Namen entfernen -> nur der Kameratyp bleibt
            # (mDNS-Name ist z. B. "AXIS M7001 - ACCC8E07ADC9")
            name = name.rsplit(" - ", 1)[0].strip()

            # Konvertieren Sie Byte-Objekte in Strings für die MAC-Adresse/Seriennummer
            # (Wert kann fehlen oder None sein -> leerer String).
            mac_address = (info.properties.get(b'macaddress') or b'').decode('utf-8', 'replace')

            # IPv4-Adressen trennen: Zeroconf/Link-Local (169.254.x.x) vs. konfiguriert
            zeroconf_ips = [a for a in ipv4 if a.startswith("169.254.")]
            configured_ips = [a for a in ipv4 if not a.startswith("169.254.")]

            service_info = {
                "Name": name,
                "IP Adresse: Zeroconfig": ', '.join(zeroconf_ips),
                "IP Adresse: Konfiguriert": ', '.join(configured_ips),
                "IPv6 Adresse": ', '.join(ipv6),
                "Port": info.port,
                "Hostname": info.server,
                "MAC-Adresse/Seriennummer": mac_address  # Hier haben wir den String-Wert
            }
            self.services.append(service_info)

    def remove_service(self, zeroconf, service_type, name):
        pass

    def update_service(self, zeroconf, service_type, name):
        pass

    def start(self):
        ServiceBrowser(self.zeroconf, "_axis-video._tcp.local.", listener=self)

    def search(self, timeout=10):
        time.sleep(timeout)

    def stop(self):
        self.zeroconf.close()

def discover_axis_cameras(show_in_console=True, timeout=10):
    discovery = AxisDiscovery()
    discovery.start()
    discovery.search(timeout)
    discovery.stop()

    if show_in_console:
        if discovery.services:
            table = PrettyTable()
            table.field_names = FIELD_NAMES

            for camera in discovery.services:
                table.add_row([camera.get(field, "") for field in FIELD_NAMES])

            print("Axis Cameras Found:")
            print(table)
        else:
            print("No Axis Cameras Found.")

    return discovery.services

def export_to_text_file(axis_cameras, output_file, columns=None):
    if columns is None:
        columns = FIELD_NAMES
    if axis_cameras:
        table = PrettyTable()
        table.field_names = columns

        for camera in axis_cameras:
            table.add_row([camera.get(field, "") for field in columns])

        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(str(table))
        print(f"Axis Cameras Found. Exported to {output_file}")
    else:
        print("No Axis Cameras Found.")

def export_to_csv(axis_cameras, output_file, columns=None):
    if columns is None:
        columns = FIELD_NAMES
    if axis_cameras:
        with open(output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            for camera in axis_cameras:
                writer.writerow({field: camera.get(field, "") for field in columns})
        print(f"Axis Cameras Found. Exported to {output_file}")
    else:
        print("No Axis Cameras Found.")

def export_results(axis_cameras, output_file, fmt=None, columns=None):
    """Exportiert je nach Format/Dateiendung als CSV oder Texttabelle.
    
    Args:
        axis_cameras: Liste der zu exportierenden Kameras
        output_file: Ausgabedatei-Pfad
        fmt: Format ('csv' oder 'txt'), wird aus Dateiendung abgeleitet falls None
        columns: Liste der zu exportierenden Spalten, standardmaessig FIELD_NAMES
    """
    if fmt is None:
        fmt = "csv" if output_file.lower().endswith(".csv") else "txt"
    if fmt == "csv":
        export_to_csv(axis_cameras, output_file, columns)
    else:
        export_to_text_file(axis_cameras, output_file, columns)

def get_first_ip(camera):
    """Erste erreichbare IP einer Kamera: bevorzugt konfiguriert, sonst Zeroconf."""
    for field in ("IP Adresse: Konfiguriert", "IP Adresse: Zeroconfig"):
        ip = camera.get(field, "").split(",")[0].strip()
        if ip:
            return ip
    return ""

def open_cameras(cameras, already_opened=None):
    """Oeffnet die Weboberflaeche jeder Kamera im Browser (je IP nur einmal)."""
    if already_opened is None:
        already_opened = set()
    for camera in cameras:
        ip = get_first_ip(camera)
        if ip and ip not in already_opened:
            webbrowser.open(f"http://{ip}")
            already_opened.add(ip)
    return already_opened

def print_version():
    print(f"Axis_Kamera_Discovery CLI Version {__version__}")

# ===================================================================
# Kamera-Konfiguration ueber die Kommandozeile (nutzt axis_kamera_discovery_vapix)
# ===================================================================

def _conn_kwargs(args):
    """Verbindungs-/Auth-Parameter aus den Argumenten; fragt Passwort ab, falls noetig."""
    password = args.password
    if password is None and not getattr(args, "factory", False):
        password = getpass.getpass(f"Passwort fuer {args.user}: ")
    return {
        "username": args.user,
        "password": password or "",
        "scheme": args.scheme,
        "port": args.port,
        "timeout": args.conn_timeout,
    }

def _run_over_ips(ips, op):
    """Fuehrt op(ip) je Kamera aus und gibt das Ergebnis aus. Liefert Exitcode."""
    failed = 0
    for ip in ips:
        try:
            print(f"[OK]     {ip}: {op(ip)}")
        except vapix.VapixError as exc:
            print(f"[FEHLER] {ip}: {exc}")
            failed += 1
    return 1 if failed else 0

def cmd_set_ip(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.set_static_ip(
        ip, new_ip=args.new_ip, subnet_mask=args.mask, gateway=args.gateway, **k))

def cmd_set_dhcp(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.set_dhcp(ip, **k))

def cmd_set_ipv6(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.set_ipv6_config(
        ip, mode=args.mode, address=args.address, router=args.router, **k))

def cmd_ipv6_show(args):
    k = _conn_kwargs(args)
    def op(ip):
        cfg = vapix.read_ipv6_config(ip, **k)
        state = "aktiv" if cfg["enabled"] else "deaktiviert"
        addrs = ", ".join(cfg["addresses"]) or "(keine)"
        return f"IPv6 {state}; Adressen: {addrs}"
    return _run_over_ips(args.ips, op)

def cmd_user_add(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.add_or_set_user(
        ip, new_user=args.name, new_password=args.new_password, role=args.role,
        factory=args.factory, **k))

def cmd_user_passwd(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.set_user_password(
        ip, target_user=args.name, new_password=args.new_password, **k))

def cmd_onvif_add(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.add_onvif_user(
        ip, new_user=args.name, new_password=args.new_password, level=args.level, **k))

def cmd_onvif_passwd(args):
    k = _conn_kwargs(args)
    return _run_over_ips(args.ips, lambda ip: vapix.set_onvif_user_password(
        ip, target_user=args.name, new_password=args.new_password, level=args.level, **k))

def _run_user_import(args, onvif):
    if not os.path.isfile(args.file):
        print(f"[FEHLER] Datei nicht gefunden: {args.file}")
        return 1
    try:
        users = vapix.parse_user_list(args.file, onvif=onvif)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {exc}")
        return 1
    kind = "ONVIF-Benutzer" if onvif else "Benutzer"
    print(f"{len(users)} {kind} aus {args.file} geladen.")
    k = _conn_kwargs(args)
    failed = 0
    for ip in args.ips:
        for u in users:
            try:
                if onvif:
                    msg = vapix.add_onvif_user(ip, new_user=u["name"],
                                               new_password=u["password"],
                                               level=u["role"], **k)
                else:
                    msg = vapix.add_or_set_user(ip, new_user=u["name"],
                                                new_password=u["password"],
                                                role=u["role"],
                                                factory=getattr(args, "factory", False), **k)
                print(f"[OK]     {ip} / {u['name']}: {msg}")
            except vapix.VapixError as exc:
                print(f"[FEHLER] {ip} / {u['name']}: {exc}")
                failed += 1
    return 1 if failed else 0

def cmd_user_import(args):
    return _run_user_import(args, onvif=False)

def cmd_onvif_import(args):
    return _run_user_import(args, onvif=True)

def cmd_firmware(args):
    if not os.path.isfile(args.file):
        print(f"[FEHLER] Datei nicht gefunden: {args.file}")
        return 1
    k = _conn_kwargs(args)
    k["timeout"] = max(600, args.conn_timeout)  # Firmware-Upload braucht lange
    return _run_over_ips(args.ips, lambda ip: vapix.upgrade_firmware(
        ip, firmware_path=args.file, factory_default=args.factory_default, **k))

def cmd_config(args):
    try:
        cfg = vapix.parse_adm_config(args.file)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {exc}")
        return 1
    vmd4_note = ", Bewegungserkennung (VMD4)" if cfg.get("vmd4") is not None else ""
    print(f"Konfiguration: Modell {cfg['model'] or '?'}, FW {cfg['firmware'] or '?'}, "
          f"{len(cfg['parameters'])} Parameter, {len(cfg['profiles'])} "
          f"Stream-Profil(e){vmd4_note}")
    k = _conn_kwargs(args)
    k["timeout"] = max(30, args.conn_timeout)
    return _run_over_ips(args.ips, lambda ip: vapix.apply_adm_config(
        ip, config=cfg, with_profiles=not args.no_profiles,
        with_vmd4=not args.no_vmd4, **k))

def cmd_config_export(args):
    if len(args.ips) != 1:
        print("[FEHLER] config-export erwartet genau eine IP-Adresse.")
        return 1
    ip = args.ips[0]
    k = _conn_kwargs(args)
    k["timeout"] = max(30, args.conn_timeout)
    try:
        cfg = vapix.read_device_config(ip, **k)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {ip}: {exc}")
        return 1
    selected = None
    if args.grep:
        try:
            rx = re.compile(args.grep, re.IGNORECASE)
        except re.error as exc:
            print(f"[FEHLER] Ungueltiges Suchmuster: {exc}")
            return 1
        selected = {n for n in cfg["parameters"] if rx.search(n)}
        if not selected:
            print(f"[FEHLER] Kein Parameter passt zu '{args.grep}'.")
            return 1
    try:
        n = vapix.write_adm_config(args.output, cfg, selected_params=selected,
                                   with_profiles=not args.no_profiles,
                                   with_vmd4=not args.no_vmd4)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {exc}")
        return 1
    extra = "" if args.no_profiles else f" + {len(cfg['profiles'])} Stream-Profil(e)"
    if not args.no_vmd4 and cfg.get("vmd4") is not None:
        extra += " + Bewegungserkennung (VMD4)"
    print(f"[OK]     {ip}: {n} Parameter{extra} -> {args.output}")
    return 0

def cmd_backup(args):
    """Speichert die komplette Geraete-Sicherung (DCA $export) einer Kamera als JSON."""
    if len(args.ips) != 1:
        print("[FEHLER] backup erwartet genau eine IP-Adresse.")
        return 1
    ip = args.ips[0]
    k = _conn_kwargs(args)
    k["timeout"] = max(60, args.conn_timeout)
    try:
        n = vapix.save_device_settings(ip, args.output, **k)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {ip}: {exc}")
        return 1
    print(f"[OK]     {ip}: {n} Ressourcen -> {args.output}")
    return 0

def cmd_backup_restore(args):
    """Spielt eine JSON-Geraete-Sicherung (DCA $import) auf die Kamera(s) ein."""
    try:
        data = vapix.load_device_settings_backup(args.file)
    except vapix.VapixError as exc:
        print(f"[FEHLER] {exc}")
        return 1
    print(f"Sicherung: {len(data)} Ressourcen ({', '.join(sorted(data))})")
    k = _conn_kwargs(args)
    k["timeout"] = max(60, args.conn_timeout)
    return _run_over_ips(args.ips, lambda ip: "{} Ressourcen eingespielt".format(
        vapix.import_device_settings(ip, data=data, import_type=args.import_type, **k)))

def main():
    parser = argparse.ArgumentParser(
        description='Axis_Kamera_Discovery - Suche und Konfiguration von Axis-Kameras.')
    # --- Discovery-Optionen (Standardaktion, wenn kein Unterbefehl angegeben ist) ---
    parser.add_argument('--output', '-o', type=str, default=None, help='Output file (export)')
    parser.add_argument('--format', '-f', choices=['txt', 'csv'], default=None,
                        help='Export format (default: from file extension, else txt)')
    parser.add_argument('--timeout', '-t', type=int, default=10,
                        help='Search duration in seconds (default: 10)')
    parser.add_argument('--watch', '-w', type=int, default=None, metavar='SECONDS',
                        help='Repeat the search every SECONDS (like the GUI auto-refresh); Ctrl+C to stop')
    parser.add_argument('--open', action='store_true',
                        help='Open each found camera web interface in the browser')
    parser.add_argument('--show', '-s', action='store_true', help='Show results in console')
    parser.add_argument('--version', '-v', action='store_true', help='Show version information')

    # --- Unterbefehle zur Kamera-Konfiguration ---
    sub = parser.add_subparsers(dest='command', metavar='BEFEHL',
                                help='Kamera-Konfiguration (set-ip, set-dhcp, set-ipv6, '
                                     'ipv6-show, user-add, user-passwd, user-import, '
                                     'onvif-add, onvif-passwd, onvif-import, firmware, '
                                     'config, config-export, backup, backup-restore)')
    # gemeinsame Verbindungs-/Auth-Optionen
    conn = argparse.ArgumentParser(add_help=False)
    conn.add_argument('ips', nargs='+', help='Ziel-IP(s) der Kamera(s)')
    conn.add_argument('-u', '--user', default='root', help='Admin-Benutzer (Standard: root)')
    conn.add_argument('-p', '--password', default=None,
                      help='Admin-Passwort (ohne Angabe wird danach gefragt)')
    conn.add_argument('--scheme', choices=['auto', 'https', 'http'], default='auto')
    conn.add_argument('--port', type=int, default=None)
    conn.add_argument('--conn-timeout', dest='conn_timeout', type=int, default=10,
                      help='Verbindungs-Timeout in Sekunden (Standard: 10)')

    sp = sub.add_parser('set-ip', parents=[conn], help='Feste IP-Adresse setzen')
    sp.add_argument('--new-ip', dest='new_ip', required=True)
    sp.add_argument('--mask', default='255.255.255.0')
    sp.add_argument('--gateway', default='')
    sp.set_defaults(func=cmd_set_ip)

    sp = sub.add_parser('set-dhcp', parents=[conn], help='Auf DHCP umstellen')
    sp.set_defaults(func=cmd_set_dhcp)

    sp = sub.add_parser('set-ipv6', parents=[conn],
                        help='IPv6 setzen (auto/manual/off)')
    sp.add_argument('--mode', choices=['auto', 'manual', 'off'], required=True,
                    help='auto=SLAAC/Router-Advertisement, manual=feste Adresse, off=aus')
    sp.add_argument('--address', default='',
                    help='Feste IPv6-Adresse mit Praefix (nur mode=manual, z. B. 2001:db8::10/64)')
    sp.add_argument('--router', default='',
                    help='IPv6-Gateway (optional, nur mode=manual)')
    sp.set_defaults(func=cmd_set_ipv6)

    sp = sub.add_parser('ipv6-show', parents=[conn],
                        help='Aktuelle IPv6-Konfiguration auslesen')
    sp.set_defaults(func=cmd_ipv6_show)

    sp = sub.add_parser('user-add', parents=[conn], help='Benutzer anlegen')
    sp.add_argument('--name', required=True, help='Name des neuen Benutzers')
    sp.add_argument('--new-password', dest='new_password', required=True)
    sp.add_argument('--role', choices=list(vapix.USER_ROLES), default='viewer')
    sp.add_argument('--factory', action='store_true',
                    help='Auslieferungszustand: ohne Anmeldung/Standard-Zugangsdaten, als Administrator')
    sp.set_defaults(func=cmd_user_add)

    sp = sub.add_parser('user-passwd', parents=[conn], help='Benutzer-Passwort aendern')
    sp.add_argument('--name', required=True)
    sp.add_argument('--new-password', dest='new_password', required=True)
    sp.set_defaults(func=cmd_user_passwd)

    sp = sub.add_parser('user-import', parents=[conn],
                        help='Benutzer aus einer Textdatei anlegen (Name,Passwort[,Rolle])')
    sp.add_argument('--file', required=True, help='Benutzerliste (.txt/.csv)')
    sp.add_argument('--factory', action='store_true',
                    help='Auslieferungszustand: ohne Anmeldung/Standard-Zugangsdaten, als Administrator')
    sp.set_defaults(func=cmd_user_import)

    sp = sub.add_parser('onvif-add', parents=[conn], help='ONVIF-Benutzer anlegen')
    sp.add_argument('--name', required=True)
    sp.add_argument('--new-password', dest='new_password', required=True)
    sp.add_argument('--level', choices=list(vapix.ONVIF_LEVELS), default='Administrator')
    sp.set_defaults(func=cmd_onvif_add)

    sp = sub.add_parser('onvif-passwd', parents=[conn], help='ONVIF-Passwort aendern')
    sp.add_argument('--name', required=True)
    sp.add_argument('--new-password', dest='new_password', required=True)
    sp.add_argument('--level', choices=list(vapix.ONVIF_LEVELS), default='Administrator')
    sp.set_defaults(func=cmd_onvif_passwd)

    sp = sub.add_parser('onvif-import', parents=[conn],
                        help='ONVIF-Benutzer aus einer Textdatei anlegen (Name,Passwort[,Stufe])')
    sp.add_argument('--file', required=True, help='Benutzerliste (.txt/.csv)')
    sp.set_defaults(func=cmd_onvif_import)

    sp = sub.add_parser('firmware', parents=[conn], help='Firmware (.bin) aufspielen')
    sp.add_argument('--file', required=True, help='Firmware-Datei (.bin)')
    sp.add_argument('--factory-default', dest='factory_default', action='store_true')
    sp.set_defaults(func=cmd_firmware)

    sp = sub.add_parser('config', parents=[conn], help='ADM-Konfigurationsdatei (.cfg) anwenden')
    sp.add_argument('--file', required=True, help='Axis-Device-Manager-Konfiguration (.cfg)')
    sp.add_argument('--no-profiles', dest='no_profiles', action='store_true',
                    help='Stream-Profile nicht uebernehmen')
    sp.add_argument('--no-vmd4', dest='no_vmd4', action='store_true',
                    help='Bewegungserkennung (VMD4) nicht uebernehmen')
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser('config-export', parents=[conn],
                        help='Konfiguration einer Kamera als ADM-.cfg speichern')
    sp.add_argument('--output', '-o', required=True, help='Zieldatei (.cfg)')
    sp.add_argument('--grep', default=None,
                    help='Nur Parameter, deren Name auf dieses Regex passt (sonst alle)')
    sp.add_argument('--no-profiles', dest='no_profiles', action='store_true',
                    help='Stream-Profile nicht exportieren')
    sp.add_argument('--no-vmd4', dest='no_vmd4', action='store_true',
                    help='Bewegungserkennung (VMD4) nicht exportieren')
    sp.set_defaults(func=cmd_config_export)

    sp = sub.add_parser('backup', parents=[conn],
                        help='Komplette Geraete-Sicherung (.json) einer Kamera speichern')
    sp.add_argument('--output', '-o', required=True, help='Zieldatei (.json)')
    sp.set_defaults(func=cmd_backup)

    sp = sub.add_parser('backup-restore', parents=[conn],
                        help='Geraete-Sicherung (.json) auf Kamera(s) einspielen')
    sp.add_argument('--file', required=True, help='Sicherungsdatei (.json)')
    sp.add_argument('--import-type', dest='import_type', choices=['merge', 'default'],
                    default='merge',
                    help="'merge' (nur Gesichertes ueberschreiben, Standard) oder "
                         "'default' (betroffene Bereiche zuruecksetzen)")
    sp.set_defaults(func=cmd_backup_restore)

    args = parser.parse_args()

    if args.version:
        print_version()
        return

    if getattr(args, 'command', None):
        raise SystemExit(args.func(args))

    show_in_console = not args.output or args.show

    def run_once(already_opened):
        cameras = discover_axis_cameras(show_in_console, timeout=args.timeout)
        if args.output:
            export_results(cameras, args.output, args.format)
        if args.open:
            open_cameras(cameras, already_opened)
        return cameras

    if args.watch is not None:
        already_opened = set()
        try:
            while True:
                run_once(already_opened)
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print("\nBeendet.")
    else:
        run_once(set())

if __name__ == "__main__":
    main()

