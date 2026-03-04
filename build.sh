#!/bin/bash
# ──────────────────────────────────────────────────────────
# GROWQUARIUM-OS - Build Flashable Image
# Requires: Docker
# Usage: ./build.sh
# Output: deploy/growquarium-os.img.zip
# ──────────────────────────────────────────────────────────

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PIGEN_DIR="${REPO_DIR}/.pi-gen"
STAGE_NAME="stage-growquarium"

echo "=== GROWQUARIUM-OS Image Builder ==="

# ── Check Docker ──────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "Error: Docker is required. Install it from https://docs.docker.com/get-docker/"
    exit 1
fi

# ── Clone pi-gen if needed ────────────────────────────────
if [ ! -d "${PIGEN_DIR}" ]; then
    echo "[1/4] Cloning pi-gen..."
    git clone --depth 1 https://github.com/RPi-Distro/pi-gen.git "${PIGEN_DIR}"
else
    echo "[1/4] pi-gen already cloned."
fi

# ── Write config ──────────────────────────────────────────
echo "[2/4] Writing config..."
cat > "${PIGEN_DIR}/config" << 'EOF'
IMG_NAME=growquarium-os
RELEASE=bookworm
TARGET_HOSTNAME=growquarium
FIRST_USER_NAME=pi
ENABLE_SSH=1
LOCALE_DEFAULT=en_US.UTF-8
TIMEZONE_DEFAULT=America/New_York
KEYBOARD_KEYMAP=us
KEYBOARD_LAYOUT="English (US)"
DEPLOY_COMPRESSION=zip
EOF

# ── Skip stages 3-5 (we build on Lite, which is stage2) ──
touch "${PIGEN_DIR}/stage3/SKIP" "${PIGEN_DIR}/stage3/SKIP_IMAGES"
touch "${PIGEN_DIR}/stage4/SKIP" "${PIGEN_DIR}/stage4/SKIP_IMAGES"
touch "${PIGEN_DIR}/stage5/SKIP" "${PIGEN_DIR}/stage5/SKIP_IMAGES"

# Skip image export for stages that aren't our final output
touch "${PIGEN_DIR}/stage0/SKIP_IMAGES"
touch "${PIGEN_DIR}/stage1/SKIP_IMAGES"
touch "${PIGEN_DIR}/stage2/SKIP_IMAGES"

# ── Copy our custom stage (symlinks don't survive in Docker) ──
echo "[3/4] Copying custom stage..."
rm -rf "${PIGEN_DIR}/${STAGE_NAME}"
cp -r "${REPO_DIR}/OS/pi-gen-stage" "${PIGEN_DIR}/${STAGE_NAME}"

# ── Build ─────────────────────────────────────────────────
echo "[4/4] Building image (this takes a while)..."
cd "${PIGEN_DIR}"
CLEAN=1 ./build-docker.sh

# ── Copy output ───────────────────────────────────────────
mkdir -p "${REPO_DIR}/deploy"
cp "${PIGEN_DIR}/deploy/"*.zip "${REPO_DIR}/deploy/" 2>/dev/null || true

echo ""
echo "=== Done! ==="
echo "Image: deploy/growquarium-os.img.zip"
echo "Flash with: Raspberry Pi Imager or 'unzip -p deploy/growquarium-os.img.zip | sudo dd bs=4M of=/dev/sdX'"
