#!/usr/bin/env python3
"""
Provisioning Portal - Captive portal for WiFi setup.
Serves on port 80 during AP mode. Scans for networks,
lets user pick one and enter password, then hands off to boot_manager.
"""

from flask import Flask, render_template_string, request, redirect, jsonify
import os
import subprocess
import threading
import time

app = Flask(__name__)

WIFI_INTERFACE = "wlan0"
AP_SSID = "GrowQuarium-Setup"

# ── HTML Templates ──────────────────────────────────────────────

SETUP_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GrowQuarium - WiFi Setup</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a1628;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .card {
            background: #121e36;
            border: 1px solid #1e3a5f;
            border-radius: 16px;
            padding: 32px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        h1 {
            font-size: 1.4rem;
            color: #4fc3f7;
            margin-bottom: 4px;
        }
        .subtitle {
            color: #78909c;
            font-size: 0.85rem;
            margin-bottom: 24px;
        }
        label {
            display: block;
            font-size: 0.8rem;
            color: #90a4ae;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        select, input[type="password"] {
            width: 100%;
            padding: 12px;
            background: #0d1a2e;
            border: 1px solid #1e3a5f;
            border-radius: 8px;
            color: #e0e0e0;
            font-size: 1rem;
            margin-bottom: 20px;
            outline: none;
        }
        select:focus, input:focus {
            border-color: #4fc3f7;
        }
        button {
            width: 100%;
            padding: 14px;
            background: #1565c0;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover { background: #1976d2; }
        button:disabled {
            background: #37474f;
            cursor: wait;
        }
        .refresh-btn {
            background: none;
            border: 1px solid #1e3a5f;
            color: #4fc3f7;
            padding: 8px 12px;
            font-size: 0.8rem;
            width: auto;
            display: inline-block;
            margin-bottom: 16px;
        }
        .refresh-btn:hover { border-color: #4fc3f7; }
        .status {
            text-align: center;
            padding: 12px;
            border-radius: 8px;
            margin-top: 16px;
            font-size: 0.9rem;
            display: none;
        }
        .status.connecting {
            display: block;
            background: #1a237e;
            color: #82b1ff;
        }
        .status.error {
            display: block;
            background: #3e0000;
            color: #ef9a9a;
        }
        .icon { font-size: 2rem; margin-bottom: 12px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🌿</div>
        <h1>GrowQuarium WiFi Setup</h1>
        <p class="subtitle">Connect your controller to your home network</p>

        <form id="wifi-form" method="POST" action="/connect">
            <label for="ssid">Network</label>
            <select id="ssid" name="ssid" required>
                {% for net in networks %}
                <option value="{{ net.ssid }}">{{ net.ssid }} ({{ net.signal }}%)</option>
                {% endfor %}
                {% if not networks %}
                <option value="" disabled selected>No networks found</option>
                {% endif %}
            </select>

            <button type="button" class="refresh-btn" onclick="location.reload()">↻ Rescan</button>

            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Enter WiFi password" required>

            <button type="submit" id="submit-btn">Connect</button>
        </form>

        <div class="status connecting" id="status-connecting">
            Connecting... this may take up to 30 seconds.
        </div>
        <div class="status error" id="status-error"></div>
    </div>

    <script>
        document.getElementById('wifi-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const btn = document.getElementById('submit-btn');
            const statusConn = document.getElementById('status-connecting');
            const statusErr = document.getElementById('status-error');

            btn.disabled = true;
            btn.textContent = 'Connecting...';
            statusConn.style.display = 'block';
            statusErr.style.display = 'none';

            fetch('/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ssid: document.getElementById('ssid').value,
                    password: document.getElementById('password').value,
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.body.innerHTML = `
                        <div class="card" style="text-align:center">
                            <div class="icon">✅</div>
                            <h1>Connected!</h1>
                            <p class="subtitle" style="margin-bottom:16px">Your GrowQuarium dashboard is ready</p>
                            <p style="font-size:1.2rem; color:#4fc3f7; margin-bottom:8px">
                                <a href="http://${data.ip}:5000" style="color:#4fc3f7">http://${data.ip}:5000</a>
                            </p>
                            <p style="color:#78909c; font-size:0.85rem; margin-bottom:24px">
                                or <a href="http://growquarium.local:5000" style="color:#90a4ae">http://growquarium.local:5000</a>
                            </p>
                            <p style="color:#546e7a; font-size:0.8rem">
                                Reconnect to your home WiFi, then visit the address above.
                                <br>This setup portal will close automatically.
                            </p>
                        </div>`;
                } else {
                    statusConn.style.display = 'none';
                    statusErr.style.display = 'block';
                    statusErr.textContent = data.error || 'Connection failed. Check password and try again.';
                    btn.disabled = false;
                    btn.textContent = 'Connect';
                }
            })
            .catch(() => {
                statusConn.style.display = 'none';
                statusErr.style.display = 'block';
                statusErr.textContent = 'Request failed. The device may be reconnecting.';
                btn.disabled = false;
                btn.textContent = 'Connect';
            });
        });
    </script>
</body>
</html>
"""


def scan_wifi():
    """Scan for available WiFi networks."""
    try:
        result = subprocess.run(
            ["sudo", "iwlist", WIFI_INTERFACE, "scan"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        networks = []
        current = {}
        for line in result.stdout.split("\n"):
            line = line.strip()
            if "ESSID:" in line:
                ssid = line.split('ESSID:"')[1].rstrip('"')
                if ssid:
                    current["ssid"] = ssid
            elif "Signal level=" in line:
                # Convert dBm to percentage (rough approximation)
                try:
                    dbm = int(line.split("Signal level=")[1].split(" ")[0])
                    pct = max(0, min(100, 2 * (dbm + 100)))
                    current["signal"] = pct
                except (ValueError, IndexError):
                    current["signal"] = 0

            if "ssid" in current and "signal" in current:
                if current["ssid"] != AP_SSID:  # Don't show our own AP
                    networks.append(current)
                current = {}

        # Deduplicate and sort by signal
        seen = set()
        unique = []
        for n in sorted(networks, key=lambda x: x["signal"], reverse=True):
            if n["ssid"] not in seen:
                seen.add(n["ssid"])
                unique.append(n)
        return unique
    except Exception as e:
        app.logger.error(f"WiFi scan failed: {e}")
        return []


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def captive_portal(path):
    """Catch all routes → serve setup page (captive portal behavior)."""
    networks = scan_wifi()
    return render_template_string(SETUP_PAGE, networks=networks)


@app.route("/connect", methods=["POST"])
def connect():
    """Handle WiFi credential submission."""
    data = request.get_json()
    if data is None:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "").strip()

    if not ssid or not password:
        return jsonify({"success": False, "error": "SSID and password are required."})

    # Import boot_manager to trigger connection
    from boot_manager import connect_and_switch

    ip = connect_and_switch(ssid, password)

    if ip:
        # Exit after response so systemd restarts us into dashboard mode
        def shutdown_after_response():
            time.sleep(3)
            os._exit(0)

        threading.Thread(target=shutdown_after_response, daemon=True).start()
        return jsonify({"success": True, "ip": ip})
    else:
        return jsonify({
            "success": False,
            "error": "Could not connect. Check your password and try again.",
        })


# Android/Apple captive portal detection endpoints
@app.route("/generate_204")
@app.route("/gen_204")
def android_detect():
    return redirect("/")


@app.route("/hotspot-detect.html")
def apple_detect():
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
