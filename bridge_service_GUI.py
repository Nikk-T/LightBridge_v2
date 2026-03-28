"""
LightBridge Web Interface — bridge_service_GUI.py (port 5000)
Serves the dashboard and settings pages, proxies commands to bridge_service via WebSocket.

Config files:
  config/maps.yaml     — unit_channel_map, floor_channel_map
  config/settings.yaml — status_colour
"""

from flask import Flask, render_template, jsonify, request
import asyncio, json, websockets, yaml
from pathlib import Path

app = Flask(__name__)

WS_URL        = "ws://localhost:8765"
BASE_DIR      = Path(__file__).resolve().parent
MAPS_PATH     = BASE_DIR / "config" / "maps.yaml"
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"

# ── Config ───────────────────────────────────────────────────
def load_maps() -> dict:
    with open(MAPS_PATH) as f:
        return yaml.safe_load(f) or {}

def load_settings() -> dict:
    with open(SETTINGS_PATH) as f:
        return yaml.safe_load(f) or {}

# ── WebSocket proxy ──────────────────────────────────────────
async def ws_send(payload: dict) -> dict:
    try:
        async with websockets.connect(WS_URL, open_timeout=3) as ws:
            await ws.send(json.dumps(payload))
            reply = await asyncio.wait_for(ws.recv(), timeout=3)
            return json.loads(reply)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def send_command(payload: dict) -> dict:
    return asyncio.run(ws_send(payload))

# ── Dashboard ────────────────────────────────────────────────
@app.route("/")
def index():
    maps       = load_maps()
    settings   = load_settings()
    units      = list(maps.get("unit_channel_map", {}).keys())
    floors     = sorted(maps.get("floor_channel_map", {}).keys())
    statuses   = list(settings.get("status_colour", {}).keys())
    unit_names = maps.get("unit_names", {})
    return render_template("index.html", units=units, floors=floors,
                           statuses=statuses, unit_names=unit_names)

# ── Settings ─────────────────────────────────────────────────
@app.route("/settings")
def settings_page():
    maps     = load_maps()
    settings = load_settings()
    colours  = settings.get("status_colour", {})
    floors   = sorted(maps.get("floor_channel_map", {}).keys())
    return render_template("settings.html", colours=colours, floors=floors)

@app.route("/api/save_preset", methods=["POST"])
def save_preset():
    try:
        data = request.json
        name = data.get("name", "").strip()
        rgb  = data.get("rgb", [0, 0, 0])
        if not name:
            return jsonify({"status": "error", "message": "Preset name required"})
        settings = load_settings()
        settings.setdefault("status_colour", {})[name] = [int(rgb[0]), int(rgb[1]), int(rgb[2])]
        with open(SETTINGS_PATH, "w") as f:
            yaml.dump(settings, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return jsonify({"status": "ok", "message": f"Preset '{name}' saved"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ── Bridge API ───────────────────────────────────────────────
@app.route("/api/ping")
def ping():
    return jsonify(send_command({"command": "ping", "payload": {}}))

@app.route("/api/unit_status", methods=["POST"])
def unit_status():
    data = request.json
    return jsonify(send_command({
        "command": "unit_status",
        "payload": {"unit_id": data["unit_id"], "status": data["status"]}
    }))

@app.route("/api/sync_all", methods=["POST"])
def sync_all():
    data = request.json
    return jsonify(send_command({
        "command": "sync_all",
        "payload": {"units": data.get("units", {})}
    }))

@app.route("/api/floor_highlight", methods=["POST"])
def floor_highlight():
    data = request.json
    return jsonify(send_command({
        "command": "floor_highlight",
        "payload": {"floor": data["floor"], "colour": data.get("colour", [100, 150, 255])}
    }))

@app.route("/api/scene", methods=["POST"])
def set_scene():
    data = request.json
    return jsonify(send_command({
        "command": "set_scene",
        "payload": {"scene": data["scene"]}
    }))

@app.route("/api/blackout", methods=["POST"])
def blackout():
    return jsonify(send_command({"command": "blackout", "payload": {}}))

@app.route("/api/set_colour", methods=["POST"])
def set_colour():
    data = request.json
    return jsonify(send_command({
        "command": "set_colour",
        "payload": {"channel": data["channel"], "r": data["r"], "g": data["g"], "b": data["b"]}
    }))

@app.route("/api/reload_config", methods=["POST"])
def reload_config():
    return jsonify(send_command({"command": "reload_config", "payload": {}}))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
