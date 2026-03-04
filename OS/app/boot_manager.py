#!/usr/bin/env python3
"""
GrowQuarium Controller - Boot Manager
Handles WiFi provisioning (AP mode) and dashboard launch.

Flow:
  1. Check if wpa_supplicant has saved networks
  2. If yes → attempt connection → launch dashboard
  3. If no (or connection fails) → start AP mode for provisioning
  4. After provisioning → connect → launch dashboard
"""

import subprocess
import time
import os
import sys
import signal
import logging
from pathlib import Path

_handlers = [logging.StreamHandler()]
try:
    _handlers.append(logging.FileHandler("/var/log/growquarium-boot.log"))
except PermissionError:
    pass  # Running without root; log to console only

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_handlers,
)
log = logging.getLogger("boot_manager")

WIFI_INTERFACE = "wlan0"
AP_SSID = "GrowQuarium-Setup"
AP_IP = "192.168.4.1"
WPA_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"
CONNECT_TIMEOUT = 30  # seconds to wait for WiFi association
AP_PROCESS = None
DNSMASQ_PROCESS = None


def has_saved_networks():
    """Check if wpa_supplicant.conf contains any network blocks."""
    try:
        content = Path(WPA_CONF).read_text()
        return "network={" in content
    except FileNotFoundError:
        return False


def try_wifi_connect():
    """Attempt to connect using saved credentials. Returns IP or None."""
    log.info("Attempting WiFi connection with saved credentials...")

    subprocess.run(["sudo", "rfkill", "unblock", "wifi"], capture_output=True)
    subprocess.run(
        ["sudo", "wpa_supplicant", "-B", "-i", WIFI_INTERFACE, "-c", WPA_CONF],
        capture_output=True,
    )
    subprocess.run(["sudo", "dhcpcd", WIFI_INTERFACE], capture_output=True)

    # Wait for an IP address
    for i in range(CONNECT_TIMEOUT):
        ip = get_wlan_ip()
        if ip:
            log.info(f"Connected! IP: {ip}")
            return ip
        time.sleep(1)

    log.warning("WiFi connection timed out.")
    return None


def get_wlan_ip():
    """Return the current IP of wlan0, or None."""
    result = subprocess.run(
        ["hostname", "-I"], capture_output=True, text=True
    )
    for addr in result.stdout.strip().split():
        if not addr.startswith("127.") and not addr.startswith("192.168.4."):
            return addr
    return None


def stop_ap_mode():
    """Tear down AP mode services."""
    global AP_PROCESS, DNSMASQ_PROCESS
    log.info("Stopping AP mode...")

    for proc in [AP_PROCESS, DNSMASQ_PROCESS]:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)

    subprocess.run(["sudo", "ip", "addr", "flush", "dev", WIFI_INTERFACE], capture_output=True)
    subprocess.run(["sudo", "ip", "link", "set", WIFI_INTERFACE, "down"], capture_output=True)
    time.sleep(1)
    subprocess.run(["sudo", "ip", "link", "set", WIFI_INTERFACE, "up"], capture_output=True)


def start_ap_mode():
    """Start hostapd + dnsmasq to create the provisioning AP."""
    global AP_PROCESS, DNSMASQ_PROCESS
    log.info(f"Starting AP mode: SSID={AP_SSID}")

    # Kill anything holding wlan0
    subprocess.run(["sudo", "killall", "wpa_supplicant"], capture_output=True)
    subprocess.run(["sudo", "killall", "hostapd"], capture_output=True)
    subprocess.run(["sudo", "killall", "dnsmasq"], capture_output=True)
    time.sleep(1)

    # Configure interface
    subprocess.run(["sudo", "ip", "link", "set", WIFI_INTERFACE, "down"], capture_output=True)
    subprocess.run(["sudo", "ip", "addr", "flush", "dev", WIFI_INTERFACE], capture_output=True)
    subprocess.run(
        ["sudo", "ip", "addr", "add", f"{AP_IP}/24", "dev", WIFI_INTERFACE],
        capture_output=True,
    )
    subprocess.run(["sudo", "ip", "link", "set", WIFI_INTERFACE, "up"], capture_output=True)
    time.sleep(1)

    # Write temporary hostapd config
    hostapd_conf = f"""interface={WIFI_INTERFACE}
driver=nl80211
ssid={AP_SSID}
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
"""
    Path("/tmp/hostapd.conf").write_text(hostapd_conf)

    # Write temporary dnsmasq config (DHCP + DNS redirect for captive portal)
    dnsmasq_conf = f"""interface={WIFI_INTERFACE}
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
address=/#/{AP_IP}
"""
    Path("/tmp/dnsmasq.conf").write_text(dnsmasq_conf)

    # Start services
    AP_PROCESS = subprocess.Popen(["sudo", "hostapd", "/tmp/hostapd.conf"])
    time.sleep(2)
    DNSMASQ_PROCESS = subprocess.Popen(
        ["sudo", "dnsmasq", "-C", "/tmp/dnsmasq.conf", "--no-daemon"]
    )

    log.info(f"AP mode active. Connect to '{AP_SSID}' and visit http://{AP_IP}")


def launch_provisioning_portal():
    """Run the Flask captive portal for WiFi setup."""
    log.info("Launching provisioning portal...")
    # Import here to avoid loading Flask unless needed
    from provisioning_portal import app as portal_app

    portal_app.config["AP_IP"] = AP_IP
    portal_app.run(host="0.0.0.0", port=80, debug=False)


def launch_dashboard(ip):
    """Run the main sensor/pump dashboard."""
    log.info(f"Launching dashboard at http://{ip}:5000")
    log.info(f"Also available at http://growquarium.local:5000")

    # Enable mDNS hostname
    subprocess.run(
        ["sudo", "hostnamectl", "set-hostname", "growquarium"],
        capture_output=True,
    )

    from dashboard import app as dashboard_app, start_scheduler

    start_scheduler()
    dashboard_app.config["DEVICE_IP"] = ip
    dashboard_app.run(host="0.0.0.0", port=5000, debug=False)


def handle_shutdown(signum, frame):
    """Clean up AP processes on SIGTERM/SIGINT from systemd."""
    log.info(f"Received signal {signum}, cleaning up...")
    stop_ap_mode()
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)


def main():
    log.info("=" * 50)
    log.info("GrowQuarium Controller - Boot Manager Starting")
    log.info("=" * 50)

    if has_saved_networks():
        ip = try_wifi_connect()
        if ip:
            launch_dashboard(ip)
            return

        log.warning("Saved networks exist but connection failed. Entering AP mode.")

    # No saved networks or connection failed → AP provisioning
    start_ap_mode()
    launch_provisioning_portal()
    # Portal calls connect_and_switch() when user submits credentials,
    # which will stop AP, connect, and redirect to dashboard.


def connect_and_switch(ssid, password):
    """Called by provisioning portal after user submits WiFi credentials."""
    log.info(f"Provisioning: connecting to '{ssid}'...")

    # Ensure the conf file has the required header
    if not Path(WPA_CONF).exists():
        header = "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\ncountry=US\n"
        with open(WPA_CONF, "w") as f:
            f.write(header)

    # Use wpa_passphrase for hashed PSK (more secure), fall back to escaped plaintext
    result = subprocess.run(
        ["wpa_passphrase", ssid, password],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        with open(WPA_CONF, "a") as f:
            f.write("\n" + result.stdout)
    else:
        safe_ssid = ssid.replace('\\', '\\\\').replace('"', '\\"')
        safe_psk = password.replace('\\', '\\\\').replace('"', '\\"')
        network_block = f'\nnetwork={{\n    ssid="{safe_ssid}"\n    psk="{safe_psk}"\n    key_mgmt=WPA-PSK\n}}\n'
        with open(WPA_CONF, "a") as f:
            f.write(network_block)

    log.info("Credentials saved to wpa_supplicant.conf")

    # Tear down AP
    stop_ap_mode()
    time.sleep(2)

    # Connect
    ip = try_wifi_connect()
    return ip


if __name__ == "__main__":
    main()
