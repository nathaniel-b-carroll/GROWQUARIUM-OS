# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GROWQUARIUM-OS is a Raspberry Pi-based grow system controller. It manages WiFi provisioning via a captive portal, a web dashboard for sensor monitoring/pump control, and scheduled pump automation.

## Build & Deploy

**Flashable image (primary):** Requires Docker.
```bash
./build.sh                  # Output: deploy/growquarium-os.img.zip
```
CI builds automatically on push to `main` via `.github/workflows/build-image.yml` using `usimd/pi-gen-action`.

**Manual install** (on a Pi running Raspberry Pi OS Lite):
```bash
cd OS && sudo ./install.sh && sudo reboot
```

**On-device service management:**
```bash
sudo systemctl restart growquarium.service
sudo journalctl -u growquarium.service -f
```

**Local development** (runs on non-Pi systems — GPIO calls are wrapped in try/except):
```bash
cd OS/app && python3 dashboard.py          # Dashboard on :5000
cd OS/app && python3 provisioning_portal.py # Portal on :80 (needs sudo or port change)
```
Override config path for local dev: `GROWQUARIUM_CONFIG=./config.json python3 dashboard.py`

## Architecture

Three Python files in `OS/app/` form a pipeline orchestrated by `boot_manager.py`:

1. **boot_manager.py** — Entry point (systemd runs it as root from `/opt/growquarium`). Checks `wpa_supplicant.conf` for saved networks. If found → connect → launch dashboard. If not → start AP ("GrowQuarium-Setup") with hostapd/dnsmasq → launch provisioning portal. Exposes `connect_and_switch(ssid, password)` which the portal calls after credential submission.

2. **provisioning_portal.py** — Flask on port 80. Captive portal with catch-all routing (every path serves the setup page). Includes Android (`/generate_204`, `/gen_204`) and Apple (`/hotspot-detect.html`) captive portal detection redirects. On successful connect, calls `boot_manager.connect_and_switch()`, then `os._exit(0)` so systemd restarts into dashboard mode.

3. **dashboard.py** — Flask on port 5000. Single-page dashboard with sensor cards, pump toggle, and cron-style pump scheduling. Background scheduler thread (started explicitly via `start_scheduler()`, not at import time) checks schedules every 60s. Config persists to `/etc/growquarium/config.json` (overridable via `GROWQUARIUM_CONFIG` env var).

Both Flask apps use `render_template_string` with inline HTML/CSS/JS — no separate template files.

### Dashboard API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sensors` | GET | Sensor readings + pump state |
| `/api/pump` | POST | `{"state": true/false}` — manual pump control |
| `/api/schedules` | GET | Current pump schedules |
| `/api/schedules` | POST | `{"schedules": [...]}` — save schedules |
| `/api/theme` | POST | `{"theme": "ocean/forest/amber/slate"}` — save theme |

### Deployment Paths

| Repo path | On-device path |
|-----------|----------------|
| `OS/app/*.py` | `/opt/growquarium/` |
| `OS/system/growquarium.service` | `/etc/systemd/system/` |
| `OS/system/wpa_supplicant.conf` | `/etc/wpa_supplicant/wpa_supplicant.conf` |
| Runtime config | `/etc/growquarium/config.json` |
| Boot log | `/var/log/growquarium-boot.log` |

## Pi-Gen Image Build

`OS/pi-gen-stage/` is a custom pi-gen stage layered on Raspberry Pi OS Lite (stage2):
- `00-packages` — apt dependencies (python3-flask, hostapd, dnsmasq, avahi-daemon, wireless-tools)
- `00-run.sh` — copies app and system files into image rootfs
- `01-run-chroot.sh` — enables services, sets hostname, configures 1-Wire overlay
- `EXPORT_IMAGE` — marker that triggers .img export

`build.sh` clones pi-gen into `.pi-gen/`, skips stages 3-5 (desktop/full), links our custom stage, and runs `build-docker.sh`.

## Hardware

- GPIO access (RPi.GPIO) wrapped in try/except — code runs on non-Pi for development
- DS18B20 water temp: GPIO4 (1-Wire, reads from `/sys/bus/w1/devices/28-*/w1_slave`)
- Pump control: GPIO17 (MOSFET gate, HIGH=on)
- pH, humidity, air temp, flow rate: stubbed for future implementation

## Code Conventions

- Python 3, snake_case functions, UPPER_SNAKE_CASE constants
- Type hints on function signatures
- Logging module (not print) for all output
- JSON responses for API errors
- Dark UI theme with CSS custom properties: `--bg-body`, `--accent`, etc. Four themes: ocean (default, cyan `#4fc3f7`), forest (green), amber (orange), slate (gray)
