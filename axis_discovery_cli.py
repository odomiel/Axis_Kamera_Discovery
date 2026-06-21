# Axis IP Utility - findet Axis-Netzwerkkameras per Zeroconf/mDNS.
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

from zeroconf import ServiceBrowser, Zeroconf
import time
import csv
import webbrowser
from prettytable import PrettyTable
import argparse

# Versionsschema: JJ.MM.TT, bei mehreren Releases am selben Tag b1, b2, ...
# (wird von bump_version.py gepflegt)
__version__ = "26.06.21b11"

FIELD_NAMES = [
    "Name",
    "IP Adresse: Zeroconfig",
    "IP Adresse: Konfiguriert",
    "Port",
    "Hostname",
    "MAC-Adresse/Seriennummer",
]

def convert_bytearray_to_ipv4(bytearray_address):
    return ".".join(str(byte) for byte in bytearray_address)

class AxisDiscovery:
    def __init__(self):
        self.zeroconf = Zeroconf()
        self.services = []

    def on_service_state_change(self, zeroconf, service_type, name, state_change):
        if state_change is Zeroconf.StateChange.Added:
            self.add_service(zeroconf, service_type, name)

    def add_service(self, zeroconf, service_type, name):
        info = zeroconf.get_service_info(service_type, name)
        if info:
            addresses = [convert_bytearray_to_ipv4(address) for address in info.addresses]

            # Filtern Sie den zusätzlichen Teil aus dem Namen
            name = name.replace("._axis-video._tcp.local.", "")

            # Konvertieren Sie Byte-Objekte in Strings für die MAC-Adresse/Seriennummer
            mac_address = info.properties.get(b'macaddress', b'').decode('utf-8')

            # Adressen trennen: Zeroconf/Link-Local (169.254.x.x) vs. konfiguriert
            zeroconf_ips = [a for a in addresses if a.startswith("169.254.")]
            configured_ips = [a for a in addresses if not a.startswith("169.254.")]

            service_info = {
                "Name": name,
                "IP Adresse: Zeroconfig": ', '.join(zeroconf_ips),
                "IP Adresse: Konfiguriert": ', '.join(configured_ips),
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

def export_to_text_file(axis_cameras, output_file):
    if axis_cameras:
        table = PrettyTable()
        table.field_names = FIELD_NAMES

        for camera in axis_cameras:
            table.add_row([camera.get(field, "") for field in FIELD_NAMES])

        with open(output_file, 'w') as file:
            file.write(str(table))
        print(f"Axis Cameras Found. Exported to {output_file}")
    else:
        print("No Axis Cameras Found.")

def export_to_csv(axis_cameras, output_file):
    if axis_cameras:
        with open(output_file, 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=FIELD_NAMES)
            writer.writeheader()
            for camera in axis_cameras:
                writer.writerow({field: camera.get(field, "") for field in FIELD_NAMES})
        print(f"Axis Cameras Found. Exported to {output_file}")
    else:
        print("No Axis Cameras Found.")

def export_results(axis_cameras, output_file, fmt=None):
    """Exportiert je nach Format/Dateiendung als CSV oder Texttabelle."""
    if fmt is None:
        fmt = "csv" if output_file.lower().endswith(".csv") else "txt"
    if fmt == "csv":
        export_to_csv(axis_cameras, output_file)
    else:
        export_to_text_file(axis_cameras, output_file)

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
    print(f"Axis Discovery CLI Version {__version__}")

def main():
    parser = argparse.ArgumentParser(description='Discover Axis Cameras and export to a text file.')
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

    args = parser.parse_args()

    if args.version:
        print_version()
        return

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

