#!/usr/bin/env python3
"""
GrowQuarium Dashboard - LAN web interface for sensor monitoring and pump control.
Runs on port 5000 after WiFi connection is established.
"""

from flask import Flask, render_template_string, request, jsonify
import json
import logging
import os
import sqlite3
import subprocess
import time
import threading
from datetime import datetime, date, timedelta
from pathlib import Path

app = Flask(__name__)

# ── Persistent Config ───────────────────────────────────────────

def _resolve_config_path() -> str:
    """Determine a writable config path. Prefer env var, then system path,
    then fall back to config.json next to this script for local dev."""
    env_path = os.environ.get("GROWQUARIUM_CONFIG")
    if env_path:
        return env_path
    system_path = Path("/etc/growquarium/config.json")
    try:
        system_path.parent.mkdir(parents=True, exist_ok=True)
        return str(system_path)
    except PermissionError:
        return str(Path(__file__).parent / "config.json")


CONFIG_PATH = _resolve_config_path()
DEFAULT_CONFIG = {
    "pump_schedules": [
        {"start": "06:00", "duration_min": 5, "enabled": True},
        {"start": "12:00", "duration_min": 5, "enabled": True},
        {"start": "18:00", "duration_min": 5, "enabled": True},
    ],
    "pump_burst_seconds": 300,
    "pump_interval_minutes": 360,
    "theme": "ocean",
}

ALLOWED_THEMES = {"ocean", "forest", "amber", "slate"}


def load_config():
    try:
        return json.loads(Path(CONFIG_PATH).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except PermissionError:
        app.logger.warning(f"Cannot read {CONFIG_PATH}, using defaults")
        return DEFAULT_CONFIG.copy()


def save_config(config):
    try:
        Path(CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(CONFIG_PATH).write_text(json.dumps(config, indent=2))
    except PermissionError:
        app.logger.warning(f"Cannot write to {CONFIG_PATH} (permission denied)")


# ── Sensor Reading (stubs — replace with real GPIO reads) ──────

def read_sensors():
    """
    Read all connected sensors. Replace stubs with actual GPIO/I2C reads.
    Returns dict of current sensor values.
    """
    sensors = {}

    # DS18B20 Temperature (1-Wire on GPIO4)
    try:
        # Real implementation reads from /sys/bus/w1/devices/28-*/w1_slave
        w1_devices = Path("/sys/bus/w1/devices/")
        for dev in w1_devices.glob("28-*"):
            raw = (dev / "w1_slave").read_text()
            if "YES" in raw:
                temp_str = raw.split("t=")[1].strip()
                sensors["water_temp_c"] = round(int(temp_str) / 1000, 1)
                sensors["water_temp_f"] = round(sensors["water_temp_c"] * 9 / 5 + 32, 1)
    except Exception:
        sensors["water_temp_c"] = None
        sensors["water_temp_f"] = None

    # Placeholder for additional sensors (extend as you wire them up)
    sensors.setdefault("water_temp_c", None)
    sensors.setdefault("water_temp_f", None)
    sensors["ph"] = None           # Future: via ADC on GPIO23/24
    sensors["humidity"] = None     # Future: DHT22 / SHT31
    sensors["air_temp_c"] = None   # Future: second DS18B20
    sensors["flow_lpm"] = None     # Future: YF-S402

    sensors["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    return sensors


# ── Pump Control ────────────────────────────────────────────────

PUMP_PIN = 17
_gpio_initialized = False


def init_gpio():
    global _gpio_initialized
    if _gpio_initialized:
        return
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PUMP_PIN, GPIO.OUT)
        GPIO.output(PUMP_PIN, GPIO.LOW)
        _gpio_initialized = True
    except Exception as e:
        app.logger.warning(f"GPIO init failed (ok if not on Pi): {e}")


def set_pump(state: bool):
    """Turn pump on or off."""
    try:
        import RPi.GPIO as GPIO
        init_gpio()
        GPIO.output(PUMP_PIN, GPIO.HIGH if state else GPIO.LOW)
        return True
    except Exception:
        return False


def get_pump_state():
    """Read current pump GPIO state."""
    try:
        import RPi.GPIO as GPIO
        init_gpio()
        return GPIO.input(PUMP_PIN) == GPIO.HIGH
    except Exception:
        return False


# ── Dashboard HTML ──────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GrowQuarium Dashboard</title>
    <style>
        :root {
            --bg-body: #0a1628;
            --bg-card: #121e36;
            --bg-input: #0d1a2e;
            --accent: #4fc3f7;
            --border: #1e3a5f;
            --btn-bg: #1565c0;
            --btn-hover: #1976d2;
            --text-primary: #e0e0e0;
            --text-muted: #546e7a;
            --text-muted-2: #78909c;
            --text-heading: #b0bec5;
            --pump-on-bg: #1b5e20;
            --pump-on-text: #a5d6a7;
            --pump-on-indicator: #66bb6a;
            --pump-off-bg: #b71c1c;
            --pump-off-text: #ef9a9a;
            --slider-unchecked: #37474f;
            --schedule-border: #1a2740;
            --toast-bg: #1b5e20;
            --toast-text: #a5d6a7;
            --delete-btn: #b71c1c;
            --status-stopped-bg: #1a1a2e;
        }
        [data-theme="forest"] {
            --bg-body: #0a1a10;
            --bg-card: #12241a;
            --bg-input: #0d1e14;
            --accent: #66bb6a;
            --border: #1e4f2e;
            --btn-bg: #2e7d32;
            --btn-hover: #388e3c;
            --text-muted: #5a7a60;
            --text-muted-2: #7a9a80;
            --text-heading: #a5d6a7;
            --slider-unchecked: #37504a;
            --schedule-border: #1a3720;
            --status-stopped-bg: #1a2a1e;
        }
        [data-theme="amber"] {
            --bg-body: #1a1408;
            --bg-card: #241e10;
            --bg-input: #1e180c;
            --accent: #ffb74d;
            --border: #4f3a1e;
            --btn-bg: #e65100;
            --btn-hover: #f57c00;
            --text-muted: #7a6a4e;
            --text-muted-2: #9a8a6e;
            --text-heading: #ffe0b2;
            --slider-unchecked: #504030;
            --schedule-border: #3a2a14;
            --status-stopped-bg: #2a1e10;
        }
        [data-theme="slate"] {
            --bg-body: #121518;
            --bg-card: #1a1e24;
            --bg-input: #161a20;
            --accent: #b0bec5;
            --border: #2e3440;
            --btn-bg: #455a64;
            --btn-hover: #546e7a;
            --text-muted: #546e7a;
            --text-muted-2: #78909c;
            --text-heading: #cfd8dc;
            --slider-unchecked: #37474f;
            --schedule-border: #262c34;
            --status-stopped-bg: #1e2228;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        .header h1 { font-size: 1.1rem; color: var(--accent); }
        .header .ip { font-size: 0.7rem; color: var(--text-muted); }
        .theme-selector { display: flex; gap: 8px; align-items: center; }
        .theme-swatch {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            border: 2px solid transparent;
            cursor: pointer;
            padding: 0;
            transition: border-color 0.2s;
        }
        .theme-swatch.active {
            border-color: var(--text-primary);
            box-shadow: 0 0 0 1px rgba(255,255,255,0.2);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }
        .sensor-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .sensor-card .label {
            font-size: 0.65rem;
            color: var(--text-muted-2);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        .sensor-card .value {
            font-size: 1.55rem;
            font-weight: 600;
            color: var(--accent);
        }
        .sensor-card .value.offline { color: var(--slider-unchecked); font-size: 0.85rem; }
        .sensor-card .value.pump-on { color: var(--pump-on-indicator); }
        .sensor-card .value.pump-off { color: var(--accent); }
        .sensor-card .unit {
            font-size: 0.7rem;
            color: var(--text-muted);
        }
        .section {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }
        .section h2 {
            font-size: 0.85rem;
            color: var(--text-heading);
            margin-bottom: 16px;
        }
        .pump-toggle {
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }
        .toggle-btn {
            padding: 10px 24px;
            border: none;
            border-radius: 8px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .toggle-btn.on { background: var(--pump-on-bg); color: var(--pump-on-text); }
        .toggle-btn.off { background: var(--pump-off-bg); color: var(--pump-off-text); }
        .toggle-btn:hover { filter: brightness(1.2); }
        .pump-status {
            font-size: 0.75rem;
            padding: 6px 12px;
            border-radius: 6px;
        }
        .pump-status.running { background: var(--pump-on-bg); color: var(--pump-on-text); }
        .pump-status.stopped { background: var(--status-stopped-bg); color: var(--text-muted); }
        .schedule-row {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 0;
            border-bottom: 1px solid var(--schedule-border);
        }
        .schedule-row:last-child { border-bottom: none; }
        .schedule-row input[type="time"] {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            padding: 8px;
            font-size: 0.8rem;
        }
        .schedule-row input[type="number"] {
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text-primary);
            padding: 8px;
            width: 70px;
            font-size: 0.8rem;
        }
        .schedule-row label {
            font-size: 0.7rem;
            color: var(--text-muted-2);
        }
        .switch {
            position: relative;
            width: 44px;
            height: 24px;
        }
        .switch input { opacity: 0; width: 0; height: 0; }
        .slider {
            position: absolute;
            inset: 0;
            background: var(--slider-unchecked);
            border-radius: 24px;
            cursor: pointer;
            transition: 0.3s;
        }
        .slider:before {
            content: "";
            position: absolute;
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background: white;
            border-radius: 50%;
            transition: 0.3s;
        }
        .switch input:checked + .slider { background: var(--btn-bg); }
        .switch input:checked + .slider:before { transform: translateX(20px); }
        .save-btn {
            margin-top: 16px;
            padding: 10px 24px;
            background: var(--btn-bg);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.8rem;
        }
        .save-btn:hover { background: var(--btn-hover); }
        .add-btn {
            margin-top: 8px;
            padding: 8px 16px;
            background: none;
            border: 1px solid var(--border);
            color: var(--accent);
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.7rem;
        }
        .toast {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 0.75rem;
            display: none;
            z-index: 100;
        }
        .toast.success { background: var(--toast-bg); color: var(--toast-text); display: block; }
        .updated { color: var(--text-muted); font-size: 0.65rem; text-align: right; margin-top: 8px; }
        .chart-container {
            position: relative;
            width: 100%;
            height: 180px;
            margin-top: 8px;
        }
        .chart-container svg { width: 100%; height: 100%; }
        .chart-labels {
            display: flex;
            justify-content: space-between;
            font-size: 0.6rem;
            color: var(--text-muted);
            margin-top: 4px;
        }
        .chart-y-labels {
            position: absolute;
            top: 0;
            right: 4px;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            font-size: 0.55rem;
            color: var(--text-muted-2);
            pointer-events: none;
        }
        .chart-empty {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 180px;
            color: var(--text-muted);
            font-size: 0.75rem;
        }
        .wifi-reset-btn {
            padding: 10px 24px;
            background: none;
            border: 1px solid var(--delete-btn);
            color: var(--pump-off-text);
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.2s;
        }
        .wifi-reset-btn:hover { background: var(--pump-off-bg); }
    </style>
</head>
<body data-theme="{{ theme }}">
    <div class="header">
        <div>
            <h1>🌿 GrowQuarium</h1>
        </div>
        <div class="theme-selector">
            <button class="theme-swatch{% if theme == 'ocean' %} active{% endif %}" data-theme="ocean" style="background:#4fc3f7" title="Ocean"></button>
            <button class="theme-swatch{% if theme == 'forest' %} active{% endif %}" data-theme="forest" style="background:#66bb6a" title="Forest"></button>
            <button class="theme-swatch{% if theme == 'amber' %} active{% endif %}" data-theme="amber" style="background:#ffb74d" title="Amber"></button>
            <button class="theme-swatch{% if theme == 'slate' %} active{% endif %}" data-theme="slate" style="background:#b0bec5" title="Slate"></button>
        </div>
        <div class="ip">{{ ip }}</div>
    </div>

    <!-- Sensor Cards -->
    <div class="grid" id="sensors">
        <div class="sensor-card">
            <div class="label">Water Temp</div>
            <div class="value" id="water-temp">--</div>
            <div class="unit">&deg;F</div>
        </div>
        <div class="sensor-card">
            <div class="label">pH</div>
            <div class="value" id="ph">--</div>
            <div class="unit">&nbsp;</div>
        </div>
        <div class="sensor-card">
            <div class="label">Humidity</div>
            <div class="value" id="humidity">--</div>
            <div class="unit">%</div>
        </div>
        <div class="sensor-card">
            <div class="label">Air Temp</div>
            <div class="value" id="air-temp">--</div>
            <div class="unit">&deg;F</div>
        </div>
        <div class="sensor-card">
            <div class="label">Flow Rate</div>
            <div class="value" id="flow">--</div>
            <div class="unit">L/min</div>
        </div>
        <div class="sensor-card">
            <div class="label">Pump</div>
            <div class="value pump-off" id="pump-indicator">OFF</div>
            <div class="unit">&nbsp;</div>
        </div>
    </div>
    <div class="updated" id="last-updated"></div>

    <!-- Temperature History -->
    <div class="section">
        <h2>Water Temperature (24h)</h2>
        <div id="chart-area">
            <div class="chart-empty">Collecting data...</div>
        </div>
    </div>

    <!-- Pump Control -->
    <div class="section">
        <h2>Pump Control</h2>
        <div class="pump-toggle">
            <button class="toggle-btn on" onclick="pumpControl(true)">Turn ON</button>
            <button class="toggle-btn off" onclick="pumpControl(false)">Turn OFF</button>
            <span class="pump-status stopped" id="pump-status">Stopped</span>
        </div>
    </div>

    <!-- Schedule -->
    <div class="section">
        <h2>Pump Schedule</h2>
        <div id="schedules"></div>
        <button class="add-btn" onclick="addSchedule()">+ Add Schedule</button>
        <br>
        <button class="save-btn" onclick="saveSchedules()">Save Schedules</button>
    </div>

    <!-- Settings -->
    <div class="section">
        <h2>Settings</h2>
        <button class="wifi-reset-btn" onclick="resetWiFi()">Reset WiFi</button>
        <span style="font-size:0.7rem; color:var(--text-muted); margin-left:12px">
            Clears saved network and returns to setup mode
        </span>
    </div>

    <div class="toast" id="toast"></div>

    <script>
        let schedules = {{ schedules | tojson }};

        function renderSchedules() {
            const el = document.getElementById('schedules');
            el.innerHTML = schedules.map((s, i) => `
                <div class="schedule-row">
                    <label class="switch">
                        <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="schedules[${i}].enabled = this.checked">
                        <span class="slider"></span>
                    </label>
                    <input type="time" value="${s.start}" onchange="schedules[${i}].start = this.value">
                    <label>for</label>
                    <input type="number" value="${s.duration_min}" min="1" max="60"
                           onchange="schedules[${i}].duration_min = parseInt(this.value)">
                    <label>min</label>
                    <button style="background:none;border:none;color:var(--delete-btn);cursor:pointer;font-size:1.0rem"
                            onclick="schedules.splice(${i},1); renderSchedules()">&times;</button>
                </div>
            `).join('');
        }

        function addSchedule() {
            schedules.push({ start: "12:00", duration_min: 5, enabled: true });
            renderSchedules();
        }

        function saveSchedules() {
            fetch('/api/schedules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ schedules })
            })
            .then(r => r.json())
            .then(data => showToast(data.success ? 'Schedules saved!' : 'Save failed.'));
        }

        function pumpControl(on) {
            fetch('/api/pump', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: on })
            })
            .then(r => r.json())
            .then(updatePumpStatus);
        }

        function updatePumpStatus(data) {
            const el = document.getElementById('pump-status');
            const ind = document.getElementById('pump-indicator');
            if (data.pump_on) {
                el.className = 'pump-status running';
                el.textContent = 'Running';
                ind.textContent = 'ON';
                ind.className = 'value pump-on';
            } else {
                el.className = 'pump-status stopped';
                el.textContent = 'Stopped';
                ind.textContent = 'OFF';
                ind.className = 'value pump-off';
            }
        }

        function updateSensors() {
            fetch('/api/sensors')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('water-temp').textContent = data.water_temp_f ?? '--';
                    document.getElementById('water-temp').className = data.water_temp_f ? 'value' : 'value offline';
                    document.getElementById('ph').textContent = data.ph ?? '--';
                    document.getElementById('humidity').textContent = data.humidity ?? '--';
                    document.getElementById('air-temp').textContent = data.air_temp_c != null
                        ? Math.round(data.air_temp_c * 9/5 + 32) : '--';
                    document.getElementById('flow').textContent = data.flow_lpm ?? '--';
                    document.getElementById('last-updated').textContent = 'Updated: ' + data.timestamp;
                    updatePumpStatus(data);
                });
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast success';
            setTimeout(() => t.className = 'toast', 2500);
        }

        // Theme selector
        document.querySelectorAll('.theme-swatch').forEach(btn => {
            btn.addEventListener('click', function() {
                const theme = this.dataset.theme;
                document.body.setAttribute('data-theme', theme);
                document.querySelectorAll('.theme-swatch').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                fetch('/api/theme', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ theme })
                })
                .then(r => r.json())
                .then(data => { if (data.success) showToast('Theme saved!'); });
            });
        });

        // ── SVG Chart ──────────────────────────────────────────
        function updateChart() {
            fetch('/api/sensors/history?hours=24')
                .then(r => r.json())
                .then(data => {
                    const readings = (data.readings || []).filter(r => r.water_temp_f != null);
                    const area = document.getElementById('chart-area');
                    if (readings.length < 2) {
                        area.innerHTML = '<div class="chart-empty">Collecting data...</div>';
                        return;
                    }
                    const temps = readings.map(r => r.water_temp_f);
                    const times = readings.map(r => r.timestamp);
                    const minT = Math.floor(Math.min(...temps) - 1);
                    const maxT = Math.ceil(Math.max(...temps) + 1);
                    const range = maxT - minT || 1;
                    const pad = { top: 10, right: 40, bottom: 4, left: 4 };
                    const w = 600, h = 180;
                    const cw = w - pad.left - pad.right;
                    const ch = h - pad.top - pad.bottom;

                    let points = temps.map((t, i) => {
                        const x = pad.left + (i / (temps.length - 1)) * cw;
                        const y = pad.top + ch - ((t - minT) / range) * ch;
                        return `${x},${y}`;
                    });

                    // Build fill polygon (area under line)
                    const firstX = pad.left;
                    const lastX = pad.left + cw;
                    const bottomY = pad.top + ch;
                    const fillPoints = `${firstX},${bottomY} ${points.join(' ')} ${lastX},${bottomY}`;

                    const startTime = times[0].split(' ')[1] || times[0];
                    const endTime = times[times.length-1].split(' ')[1] || times[times.length-1];

                    area.innerHTML = `
                        <div class="chart-container">
                            <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
                                <polygon points="${fillPoints}"
                                    fill="var(--accent)" fill-opacity="0.1" />
                                <polyline points="${points.join(' ')}"
                                    fill="none" stroke="var(--accent)"
                                    stroke-width="2" stroke-linejoin="round" />
                            </svg>
                            <div class="chart-y-labels">
                                <span>${maxT}&deg;</span>
                                <span>${minT}&deg;</span>
                            </div>
                        </div>
                        <div class="chart-labels">
                            <span>${startTime}</span>
                            <span>${endTime}</span>
                        </div>`;
                })
                .catch(() => {});
        }

        // ── WiFi Reset ────────────────────────────────────────
        function resetWiFi() {
            if (!confirm('Reset WiFi credentials?\\n\\nThe device will restart in setup mode. You will need to reconnect to the GrowQuarium-Setup network.')) return;
            fetch('/api/wifi-reset', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showToast('WiFi reset. Entering setup mode...');
                    } else {
                        showToast(data.error || 'Reset failed.');
                    }
                })
                .catch(() => showToast('Request failed.'));
        }

        renderSchedules();
        updateSensors();
        updateChart();
        setInterval(updateSensors, 5000);
        setInterval(updateChart, 30000);
    </script>
</body>
</html>
"""


# ── API Routes ──────────────────────────────────────────────────

@app.route("/")
def index():
    config = load_config()
    ip = app.config.get("DEVICE_IP", "unknown")
    theme = config.get("theme", "ocean")
    return render_template_string(
        DASHBOARD_HTML,
        ip=ip,
        schedules=config["pump_schedules"],
        theme=theme,
    )


@app.route("/api/sensors")
def api_sensors():
    data = read_sensors()
    data["pump_on"] = get_pump_state()
    return jsonify(data)


@app.route("/api/pump", methods=["POST"])
def api_pump():
    body = request.get_json()
    if body is None:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    state = body.get("state", False)
    success = set_pump(state)
    return jsonify({"success": success, "pump_on": get_pump_state()})


@app.route("/api/theme", methods=["POST"])
def api_theme():
    body = request.get_json()
    if body is None:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    theme = body.get("theme", "")
    if theme not in ALLOWED_THEMES:
        return jsonify({"success": False, "error": "Invalid theme"}), 400
    config = load_config()
    config["theme"] = theme
    save_config(config)
    return jsonify({"success": True})


@app.route("/api/schedules", methods=["GET"])
def api_get_schedules():
    config = load_config()
    return jsonify({"schedules": config["pump_schedules"]})


@app.route("/api/schedules", methods=["POST"])
def api_save_schedules():
    body = request.get_json()
    if body is None:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    schedules = body.get("schedules", [])

    # Validate schedule entries
    for s in schedules:
        if not isinstance(s, dict):
            return jsonify({"success": False, "error": "Invalid schedule entry"}), 400
        if "start" not in s or "duration_min" not in s or "enabled" not in s:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        if not isinstance(s["duration_min"], (int, float)) or s["duration_min"] < 1 or s["duration_min"] > 60:
            return jsonify({"success": False, "error": "Duration must be 1-60 minutes"}), 400

    config = load_config()
    config["pump_schedules"] = schedules
    save_config(config)
    return jsonify({"success": True})


@app.route("/api/sensors/history")
def api_sensor_history():
    """Return sensor history for charting. Query param: hours (default 24)."""
    hours = request.args.get("hours", 24, type=int)
    hours = max(1, min(hours, 720))  # Clamp to 1h–30d
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """SELECT timestamp, water_temp_f, ph, humidity,
                      air_temp_c, flow_lpm, pump_state
               FROM sensor_readings
               WHERE timestamp > datetime('now', 'localtime', ? || ' hours')
               ORDER BY timestamp ASC""",
            (f"-{hours}",),
        )
        readings = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Downsample to ~200 points max for chart performance
        if len(readings) > 200:
            step = len(readings) // 200
            readings = readings[::step]

        return jsonify({"readings": readings})
    except Exception as e:
        return jsonify({"readings": [], "error": str(e)})


WPA_CONF = "/etc/wpa_supplicant/wpa_supplicant.conf"


@app.route("/api/wifi-reset", methods=["POST"])
def api_wifi_reset():
    """Clear saved WiFi credentials and restart into AP mode."""
    try:
        # Keep only the wpa_supplicant header (first 3 lines)
        header_lines = [
            "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n",
            "update_config=1\n",
            "country=US\n",
        ]
        try:
            with open(WPA_CONF, "r") as f:
                lines = f.readlines()
            # Preserve actual header if it exists
            header_lines = []
            for line in lines:
                if line.strip().startswith("network="):
                    break
                header_lines.append(line)
        except (FileNotFoundError, PermissionError):
            pass

        Path(WPA_CONF).write_text("".join(header_lines))
        app.logger.info("WiFi credentials cleared")

        # Restart the service so boot_manager re-enters AP mode
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "growquarium.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return jsonify({"success": True, "message": "WiFi reset. Entering setup mode..."})
    except PermissionError:
        return jsonify({"success": False, "error": "Permission denied (not running as root)"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Sensor History (SQLite) ────────────────────────────────────

DB_PATH = str(Path(CONFIG_PATH).parent / "sensors.db")


def init_db():
    """Create sensor history database if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                water_temp_f REAL,
                ph REAL,
                humidity REAL,
                air_temp_c REAL,
                flow_lpm REAL,
                pump_state INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON sensor_readings(timestamp DESC)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"Could not initialize sensor DB: {e}")


def log_sensor_reading():
    """Record current sensor readings to SQLite."""
    try:
        sensors = read_sensors()
        pump_on = get_pump_state()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO sensor_readings
               (water_temp_f, ph, humidity, air_temp_c, flow_lpm, pump_state)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                sensors.get("water_temp_f"),
                sensors.get("ph"),
                sensors.get("humidity"),
                sensors.get("air_temp_c"),
                sensors.get("flow_lpm"),
                1 if pump_on else 0,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to log sensor reading: {e}")


def cleanup_old_readings():
    """Delete sensor readings older than 30 days."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "DELETE FROM sensor_readings WHERE timestamp < datetime('now', '-30 days')"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"Failed to clean old readings: {e}")


# ── Pump Scheduler Thread (non-blocking) ─────────────────────

_pump_run_until: datetime | None = None
_last_triggered: dict[str, date] = {}
_scheduler_lock = threading.Lock()


def pump_scheduler():
    """Non-blocking scheduler. Polls every 10s, tracks pump state via timestamps."""
    global _pump_run_until
    last_log_minute = -1
    last_cleanup_hour = -1

    while True:
        try:
            now = datetime.now()

            with _scheduler_lock:
                # Check if current scheduled run should stop
                if _pump_run_until is not None and now >= _pump_run_until:
                    app.logger.info("Scheduled pump run complete")
                    set_pump(False)
                    _pump_run_until = None

                # Check if a new run should start
                if _pump_run_until is None:
                    config = load_config()
                    current_hm = now.strftime("%H:%M")
                    for sched in config["pump_schedules"]:
                        if not sched["enabled"]:
                            continue
                        if sched["start"] != current_hm:
                            continue
                        sched_key = sched["start"]
                        if _last_triggered.get(sched_key) == now.date():
                            continue
                        # Start pump run
                        duration = sched["duration_min"] * 60
                        _pump_run_until = now + timedelta(seconds=duration)
                        _last_triggered[sched_key] = now.date()
                        set_pump(True)
                        app.logger.info(
                            f"Scheduled pump run: {sched['duration_min']}min "
                            f"(until {_pump_run_until.strftime('%H:%M:%S')})"
                        )
                        break

            # Log sensor readings once per minute
            if now.minute != last_log_minute:
                last_log_minute = now.minute
                log_sensor_reading()

            # Cleanup old readings once per hour
            if now.hour != last_cleanup_hour:
                last_cleanup_hour = now.hour
                cleanup_old_readings()

        except Exception as e:
            app.logger.error(f"Scheduler error: {e}")

        time.sleep(10)


def start_scheduler():
    """Start the pump scheduler thread. Call explicitly — not at import time."""
    init_db()
    thread = threading.Thread(target=pump_scheduler, daemon=True)
    thread.start()
    app.logger.info("Pump scheduler started.")


DASHBOARD_PORT = int(os.environ.get("GROWQUARIUM_PORT", 5000))

if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
