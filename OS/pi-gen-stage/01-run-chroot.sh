#!/bin/bash
set -e

# Disable hostapd/dnsmasq from auto-starting (boot_manager controls them)
systemctl disable hostapd 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true

# Enable growquarium service
systemctl enable growquarium.service

# Enable mDNS
systemctl enable avahi-daemon

# Set hostname
echo "growquarium" > /etc/hostname
sed -i 's/127\.0\.1\.1.*/127.0.1.1\tgrowquarium/' /etc/hosts

# Enable 1-Wire overlay for DS18B20 on GPIO4
CONFIG_FILE="/boot/firmware/config.txt"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/boot/config.txt"
if ! grep -q "dtoverlay=w1-gpio" "$CONFIG_FILE" 2>/dev/null; then
    echo "dtoverlay=w1-gpio" >> "$CONFIG_FILE"
fi

# Clean up to reduce image size
apt-get clean
rm -rf /var/lib/apt/lists/*
