#!/bin/bash
set -e

STAGE_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="${STAGE_DIR}/../app"
SYSTEM_DIR="${STAGE_DIR}/../system"

# Application files
install -d "${ROOTFS_DIR}/opt/growquarium"
install -m 755 "${APP_DIR}/boot_manager.py" "${ROOTFS_DIR}/opt/growquarium/"
install -m 644 "${APP_DIR}/provisioning_portal.py" "${ROOTFS_DIR}/opt/growquarium/"
install -m 644 "${APP_DIR}/dashboard.py" "${ROOTFS_DIR}/opt/growquarium/"

# Systemd service
install -m 644 "${SYSTEM_DIR}/growquarium.service" "${ROOTFS_DIR}/etc/systemd/system/"

# Config directory
install -d "${ROOTFS_DIR}/etc/growquarium"

# Base wpa_supplicant config
install -m 600 "${SYSTEM_DIR}/wpa_supplicant.conf" "${ROOTFS_DIR}/etc/wpa_supplicant/wpa_supplicant.conf"
