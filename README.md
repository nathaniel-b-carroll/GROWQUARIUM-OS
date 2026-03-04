# GrowQuarium Controller - Software Stack

## Quick Start (Flashable Image)

1. Download the latest `growquarium-os.img.zip` from [Releases](../../releases)
2. Flash to an SD card with [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
3. Insert SD card, power on the Pi
4. Connect to the **"GrowQuarium-Setup"** WiFi network from your phone/laptop
5. Follow the captive portal to connect to your home WiFi
6. Dashboard available at **http://growquarium.local:5000**

## Directory Structure

```
OS/
├── app/                    # Python application
│   ├── boot_manager.py     # Boot lifecycle orchestrator
│   ├── provisioning_portal.py  # Captive portal (port 80)
│   └── dashboard.py        # LAN dashboard (port 5000)
├── system/                 # System configuration
│   ├── growquarium.service # systemd unit
│   └── wpa_supplicant.conf # Base WiFi config template
├── pi-gen-stage/           # Custom pi-gen stage for image builds
└── install.sh              # Manual install (alternative to flashing image)
```

## Boot Flow

```
Power On
  │
  ├─ Saved WiFi exists?
  │    ├─ YES → Connect → Launch dashboard at http://growquarium.local:5000
  │    └─ NO (or fail) ↓
  │
  ├─ Start AP: "GrowQuarium-Setup"
  │    └─ User connects phone/laptop to AP
  │         └─ Captive portal auto-opens
  │              └─ User selects network + enters password
  │                   └─ Credentials saved (persists across reboots)
  │                        └─ AP shuts down → connects → shows dashboard IP
  │
  └─ Dashboard serves on LAN until power off
```

## Credentials Persistence

WiFi credentials are appended to `/etc/wpa_supplicant/wpa_supplicant.conf` which persists across reboots. The AP provisioning portal only activates when no saved network can be reached.

## Dashboard API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sensors` | GET | Current sensor readings + pump state |
| `/api/pump` | POST | `{"state": true/false}` — manual pump control |
| `/api/schedules` | GET | Current pump schedules |
| `/api/schedules` | POST | `{"schedules": [...]}` — save new schedules |

## Building the Image

### CI (GitHub Actions)

Push to `main` triggers an automatic image build. Download the artifact from the Actions tab.

### Local Build (requires Docker)

```bash
./build.sh
# Output: deploy/growquarium-os.img.zip
```

### Manual Install (alternative)

```bash
# On a Pi running Raspberry Pi OS Lite:
cd OS && chmod +x install.sh && sudo ./install.sh && sudo reboot
```

## Sensor Wiring

- **DS18B20** → GPIO4 (1-Wire, water temp)
- **GPIO17** → MOSFET gate (pump control)
- **GPIO23/24** → pH sensor (via ADC, future)
- **GPIO18** → DHT22/SHT31 (humidity, future)
- **GPIO25** → Light control (future)
