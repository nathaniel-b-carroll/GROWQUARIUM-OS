#!/usr/bin/env python3
"""
GrowQuarium Dashboard - LAN web interface for sensor monitoring and pump control.
Runs on port 5000 after WiFi connection is established.
"""

from flask import Flask, render_template_string, request, jsonify
import json
import os
import time
import threading
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

        renderSchedules();
        updateSensors();
        setInterval(updateSensors, 5000);
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


# ── Pump Scheduler Thread ──────────────────────────────────────

def pump_scheduler():
    """Background thread that runs pump according to saved schedules."""
    while True:
        try:
            config = load_config()
            now = time.strftime("%H:%M")
            for sched in config["pump_schedules"]:
                if sched["enabled"] and sched["start"] == now:
                    app.logger.info(f"Scheduled pump run: {sched['duration_min']}min")
                    set_pump(True)
                    time.sleep(sched["duration_min"] * 60)
                    set_pump(False)
        except Exception as e:
            app.logger.error(f"Scheduler error: {e}")
        time.sleep(60)  # Check every minute


def start_scheduler():
    """Start the pump scheduler thread. Call explicitly — not at import time."""
    thread = threading.Thread(target=pump_scheduler, daemon=True)
    thread.start()
    app.logger.info("Pump scheduler started.")


DASHBOARD_PORT = int(os.environ.get("GROWQUARIUM_PORT", 5000))

if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
