#!/bin/bash
# ──────────────────────────────────────────────────────────
# GrowQuarium Controller - Install Script
# Manual install on a fresh Raspberry Pi OS Lite:
#   cd OS && chmod +x install.sh && sudo ./install.sh
# For a pre-built flashable image, see build.sh in the repo root.
# ──────────────────────────────────────────────────────────

set -e

echo "🌿 GrowQuarium Controller - Installing..."

# ── System Dependencies ──────────────────────────────────
echo "[1/6] Installing packages..."
apt-get update
apt-get install -y \
    python3-pip \
    python3-flask \
    hostapd \
    dnsmasq \
    avahi-daemon \
    wireless-tools

# Disable hostapd/dnsmasq from auto-starting (we manage them manually)
systemctl disable hostapd 2>/dev/null || true
systemctl stop hostapd 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# ── Enable 1-Wire for DS18B20 ───────────────────────────
echo "[2/6] Configuring 1-Wire interface..."
if ! grep -q "dtoverlay=w1-gpio" /boot/firmware/config.txt 2>/dev/null && \
   ! grep -q "dtoverlay=w1-gpio" /boot/config.txt 2>/dev/null; then
    CONFIG_FILE="/boot/firmware/config.txt"
    [ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"
    echo "dtoverlay=w1-gpio" >> "$CONFIG_FILE"
    echo "  → Added 1-Wire overlay (GPIO4)"
fi

# ── Copy Application Files ──────────────────────────────
echo "[3/6] Installing application..."
mkdir -p /opt/growquarium
mkdir -p /etc/growquarium

cp app/boot_manager.py /opt/growquarium/
cp app/provisioning_portal.py /opt/growquarium/
cp app/dashboard.py /opt/growquarium/

chmod +x /opt/growquarium/boot_manager.py

# ── Install Systemd Service ─────────────────────────────
echo "[4/6] Setting up systemd service..."
cp system/growquarium.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable growquarium.service

# ── Configure Avahi (mDNS) for growquarium.local ─────────
echo "[5/6] Configuring mDNS hostname..."
hostnamectl set-hostname growquarium
systemctl enable avahi-daemon
systemctl restart avahi-daemon

# ── Ensure wpa_supplicant base config exists ─────────────
echo "[6/6] Preparing WiFi config..."
WPA_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"
if [ ! -f "$WPA_CONF" ]; then
    cat > "$WPA_CONF" << 'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US
EOF
    echo "  → Created base wpa_supplicant.conf"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "  ✅ Installation complete!"
echo ""
echo "  On next boot:"
echo "    • If no WiFi saved → broadcasts 'GrowQuarium-Setup' AP"
echo "    • Connect to it and follow the setup portal"
echo "    • After setup → dashboard at http://growquarium.local:5000"
echo ""
echo "  Reboot now?  sudo reboot"
echo "════════════════════════════════════════════════════════"
