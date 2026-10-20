"""Run the Flask app over HTTPS with a local self-signed certificate."""

import ipaddress
import os
import shutil
import socket
import subprocess
from pathlib import Path

from app import app


BASE_DIR = Path(__file__).resolve().parents[1]
CERT_DIR = BASE_DIR / ".local-https"
CERT_FILE = CERT_DIR / "localhost.pem"
KEY_FILE = CERT_DIR / "localhost-key.pem"


def local_addresses():
    addresses = {ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")}
    try:
        # UDP connect discovers the preferred local interface without sending data.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            addresses.add(ipaddress.ip_address(sock.getsockname()[0]))
    except OSError:
        pass

    try:
        for result in socket.getaddrinfo(socket.gethostname(), None):
            addresses.add(ipaddress.ip_address(result[4][0].split("%", 1)[0]))
    except OSError:
        pass

    for value in os.environ.get("LOCAL_HTTPS_IPS", "").split(","):
        value = value.strip()
        if value:
            addresses.add(ipaddress.ip_address(value))
    return sorted(addresses, key=lambda address: (address.version, str(address)))


def local_names():
    names = {"localhost", socket.gethostname()}
    for value in os.environ.get("LOCAL_HTTPS_NAMES", "").split(","):
        value = value.strip()
        if value:
            names.add(value)
    return sorted(names)


def ensure_certificate(openssl, addresses, names):
    CERT_DIR.mkdir(mode=0o700, exist_ok=True)
    san_entries = [*(f"IP:{address}" for address in addresses), *(f"DNS:{name}" for name in names)]
    san = ",".join(san_entries)
    if CERT_FILE.is_file() and KEY_FILE.is_file():
        validity = subprocess.run(
            [openssl, "x509", "-in", str(CERT_FILE), "-noout", "-checkend", "86400"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        existing_san = subprocess.run(
            [openssl, "x509", "-in", str(CERT_FILE), "-noout", "-ext", "subjectAltName"],
            capture_output=True,
            text=True,
        )
        if validity.returncode == 0 and existing_san.returncode == 0 and all(
            entry in existing_san.stdout for entry in san_entries
        ):
            return

    subprocess.run(
        [
            openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "365",
            "-nodes", "-keyout", str(KEY_FILE), "-out", str(CERT_FILE),
            "-subj", "/CN=localhost", "-addext", f"subjectAltName={san}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    KEY_FILE.chmod(0o600)


def main():
    openssl = shutil.which("openssl")
    if not openssl:
        raise SystemExit("Не е намерен OpenSSL. Инсталирай го, за да създадеш локален сертификат.")

    addresses = local_addresses()
    names = local_names()
    ensure_certificate(openssl, addresses, names)

    port = int(os.environ.get("PORT", "5000"))
    print("Локалният HTTPS сървър е достъпен на:")
    for name in names:
        print(f"  https://{name}:{port}")
    for address in addresses:
        display_address = f"[{address}]" if address.version == 6 else str(address)
        print(f"  https://{display_address}:{port}")
    print("Сертификатът е самоподписан; браузърът ще покаже предупреждение за доверие.")
    print("За IP адреси от допълнителни мрежови интерфейси задай LOCAL_HTTPS_IPS=IP1,IP2 и стартирай отново.")

    app.run(host="0.0.0.0", port=port, debug=False, ssl_context=(str(CERT_FILE), str(KEY_FILE)))


if __name__ == "__main__":
    main()
