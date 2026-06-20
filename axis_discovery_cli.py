from zeroconf import ServiceBrowser, Zeroconf
import time
import csv
from prettytable import PrettyTable
import argparse

# Versionsschema: JJ.MM.TT, bei mehreren Releases am selben Tag b1, b2, ...
# (wird von bump_version.py gepflegt)
__version__ = "26.06.20"

FIELD_NAMES = [
    "Name",
    "IP Adresse: Zeroconfig/Konfiguriert",
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

            # Konvertieren Sie Listen von IP-Adressen in Strings
            ip_addresses = ', '.join(addresses)

            service_info = {
                "Name": name,
                "IP Adresse: Zeroconfig/Konfiguriert": ip_addresses,
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

def print_version():
    print(f"Axis Discovery CLI Version {__version__}")

def main():
    parser = argparse.ArgumentParser(description='Discover Axis Cameras and export to a text file.')
    parser.add_argument('--output', '-o', type=str, default=None, help='Output file (export)')
    parser.add_argument('--format', '-f', choices=['txt', 'csv'], default=None,
                        help='Export format (default: from file extension, else txt)')
    parser.add_argument('--show', '-s', action='store_true', help='Show results in console')
    parser.add_argument('--version', '-v', action='store_true', help='Show version information')

    args = parser.parse_args()

    if args.version:
        print_version()
        return

    show_in_console = not args.output or args.show
    axis_cameras = discover_axis_cameras(show_in_console)

    if args.output:
        export_results(axis_cameras, args.output, args.format)

if __name__ == "__main__":
    main()

