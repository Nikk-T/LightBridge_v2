import asyncio, json, logging, serial, time
import websockets
import yaml
import random

from pathlib import Path
from logging.handlers import RotatingFileHandler
from serialdriver import SLS960

idle_show_task = None

# -----------------------------
# Create logs directory
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR/"logs"
LOG_DIR.mkdir(exist_ok=True)
#LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "bridge.log"
ERROR_FILE = LOG_DIR / "bridge_error.log"

# -----------------------------
# Create logger
# -----------------------------
log = logging.getLogger("bridge")
log.setLevel(logging.INFO)

# -----------------------------
# Log format
# -----------------------------
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# -----------------------------
# Rotating main log file
# -----------------------------
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,   # 5 MB
    backupCount=3               # keep 3 old logs
)
file_handler.setFormatter(formatter)

# -----------------------------
# Error log file
# -----------------------------
error_handler = RotatingFileHandler(
    ERROR_FILE,
    maxBytes=2 * 1024 * 1024,
    backupCount=3
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# -----------------------------
# Console output
# -----------------------------
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# -----------------------------
# Add handlers
# -----------------------------
log.addHandler(file_handler)
log.addHandler(error_handler)
log.addHandler(console_handler)


CONFIG_PATH = BASE_DIR / "config" / "maps.yaml"
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"

SERIAL_PORT = "/dev/ttyUSB0" # Confirm name of port running ls /dev* command. Supposed to be /dev/ttyUSB0
SERIAL_BAUD = 115200         # Confirm DIP switch setting on unit
WS_URL = "ws://0.0.0.0:8765"

UNIT_CHANNEL_MAP = {}
FLOOR_CHANNEL_MAP = {}
STATUS_COLOUR = {}
INTERVAL = 1000

RECONNECT_DELAY = 5
#---------------------------------------------------------
# Load config from YAML
#---------------------------------------------------------
# Load Maps
def load_maps(config_path=CONFIG_PATH):
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

        #Unit map
        unit_channel_map = config.get("unit_channel_map", {})

        #Floor map
        floor_channel_map = {}
        for floor, range_data in config.get("floor_channel_map", {}).items():
            if not isinstance(range_data, list) or len(range_data) !=2:
                raise ValueError(
                    f"Invalid floor_channel_map entry for floor {floor}. "
                    f"Expected [start, end], got: {range_data}"
                )
            start, end = map(int, range_data)
            floor_channel_map[int(floor)] = list(range(start, end+1))

    return unit_channel_map, floor_channel_map
#========= LOAD other settings =================
def load_settings(settings_path=SETTINGS_PATH):
    if not settings_path.exists():
        raise FileNotFoundError(f"Config file not found: {settings_path}")

    with open(settings_path, "r") as f:
        config = yaml.safe_load(f)

        #Get colors
        status_colour = config.get("status_colour", {})
        interval = config.get("interval", 1000)
        return status_colour, interval

sls = SLS960(SERIAL_BAUD)
START_TIME = time.time()

#======= Async scenes ==========
#Realistic light show
async def realistic_idle_show():

    log.info("Realistic idle show started")
    units = list(UNIT_CHANNEL_MAP.keys())
    # state tracking
    active_units = {}
    try:
        while True:

            # desired active apartment count
            target_active = random.randint(
                int(len(units)*0.1),
                int(len(units)*0.4)
            )

            # turn on more apartments if needed
            while len(active_units) < target_active:
                uid = random.choice(units)

                if uid in active_units:
                    continue
                channels = UNIT_CHANNEL_MAP.get(uid, [])

                # warm white variation
                #base = random.randint(200,255)
                r = 255 #base
                g = 200 #base # - random.randint(5,40)
                b = 160 #base # - random.randint(20,70)

                for ch in channels:
                    sls.rgb_fadein(ch,r,g,b, INTERVAL*2)
                duration = random.randint(2,20)
                active_units[uid] = asyncio.get_event_loop().time() + duration
                log.debug(f"Apartment {uid} ON for {duration}s")

            # check apartments to turn off
            now = asyncio.get_event_loop().time()
            for uid in list(active_units.keys()):
                if now >= active_units[uid]:
                    for ch in UNIT_CHANNEL_MAP.get(uid,[]):
                        sls.rgb_fadein(ch,0,0,0, 0)
                    log.debug(f"Apartment {uid} OFF")
                    del active_units[uid]
            await asyncio.sleep(random.uniform(1,3))
    except asyncio.CancelledError:

        log.info("Realistic idle show stopped")

        # turn off all active units
        for uid in active_units:
            for ch in UNIT_CHANNEL_MAP.get(uid,[]):
                sls.rgb_fadein(ch,0,0,0, INTERVAL)
        raise

# ============== Scene light up ====================
async def _run_light_up():
    log.info("Scene light_up started")
    try:
        for floor in sorted(FLOOR_CHANNEL_MAP.keys()):
            sls.suspend()
            for ch in FLOOR_CHANNEL_MAP[floor]:
                sls.rgb_fadein(ch, 255, 220, 160, INTERVAL)
            sls.resume()
            await asyncio.sleep(0.2)
        log.info("Scene light_up complete")
    except asyncio.CancelledError:
        sls.blackout()
        log.info("Scene light_up interrupted")
        raise

#================ Scene fede out =====================
async def _run_fade_out():
    log.info("Scene fade_out started")
    try:
        for floor in sorted(FLOOR_CHANNEL_MAP.keys(), reverse=True):
            sls.suspend()
            for ch in FLOOR_CHANNEL_MAP[floor]:
                sls.rgb_fadein(ch, 0, 0, 0, INTERVAL)
            sls.resume()
            await asyncio.sleep(0.2)
        sls.blackout()
        log.info("Scene fade_out complete")
    except asyncio.CancelledError:
        sls.blackout()
        log.info("Scene fade_out interrupted")
        raise

#================ Rainbow run ========================
async def _run_rainbow():
    log.info("Scene rainbow started")
    # Full rainbow: 0=red, 120=green, 240=blue (HSV hue degrees)
    def hue_to_rgb(hue):
        h = hue % 360
        x = 1 - abs((h / 60) % 2 - 1)
        if   h < 60:  r, g, b = 1,   x,   0
        elif h < 120: r, g, b = x,   1,   0
        elif h < 180: r, g, b = 0,   1,   x
        elif h < 240: r, g, b = 0,   x,   1
        elif h < 300: r, g, b = x,   0,   1
        else:         r, g, b = 1,   0,   x
        return int(r * 255), int(g * 255), int(b * 255)

    try:
        hue_offset = 0
        floors = sorted(FLOOR_CHANNEL_MAP.keys())
        while True:
            sls.suspend()
            for i, floor in enumerate(floors):
                hue = (hue_offset + i * (360 // max(len(floors), 1))) % 360
                r, g, b = hue_to_rgb(hue)
                for ch in FLOOR_CHANNEL_MAP[floor]:
                    sls.rgb_fadein(ch, r, g, b, INTERVAL)
            sls.resume()
            hue_offset = (hue_offset + 15) % 360
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        sls.blackout()
        log.info("Scene rainbow interrupted")
        raise

#Send MDP_NOP every 10 min to prevent 30-min SLS960 idle timeout.
async def keepalive_loop():
    while True:
        await asyncio.sleep(600)
        sls.keepalive()
        log.debug("Keepalive NOP sent")

#WebSocket handling
async def handle(websocket):
    global idle_show_task
    log.info(f"Client connected: {websocket.remote_address}")
    async for msg in websocket:
        try:
            data = json.loads(msg)
            command = data.get("command", "")
            payload = data.get("payload", {})
            log.info(f"CMD: {command} | {payload}")

            #Stop idle show on any command except PING
            if idle_show_task and command != "ping" and not idle_show_task.done():
                log.info("Stopping realistic idle show deu to new command")
                idle_show_task.cancel()
                idle_show_task = None

            if command == "unit_status" or command == "unit_topology":
                uid = payload["unit_id"]
                status = payload.get("status", "off")
                r, g, b = STATUS_COLOUR.get(status, (0,0,0))
                for ch in UNIT_CHANNEL_MAP.get(uid, []):
                    sls.rgb_fadein(ch, r, g, b, INTERVAL)

            elif command == "sync_all" or command == "highlight_group":
                # SUSPEND first — all channels update simultaneously
                sls.suspend()
                for uid, status in payload.get("units", {}).items():
                    r, g, b = STATUS_COLOUR.get(status, (0,0,0))
                    for ch in UNIT_CHANNEL_MAP.get(uid, []):
                        sls.rgb_fadein(ch, r, g, b, INTERVAL)
                sls.resume() # All channels light at once — no flicker

            elif command == "floor_highlight":
                col = payload.get("colour", [100, 150, 255])
                floor = int(payload.get("floor", 0))
                channels = FLOOR_CHANNEL_MAP.get(floor, [])
                log.info(f"floor_highlight: floor={floor}, channels={len(channels)}, colour={col}")
                sls.suspend()
                for ch in channels:
                    if payload.get("instant", True):
                        sls.rgb(ch, *col)
                    else:
                        sls.rgb_fadein(ch, *col, INTERVAL)
                sls.resume()

            elif command == "set_scene":
                scene = payload.get("scene", "idle")
                if scene == "blackout":
                    sls.blackout()

                elif scene == "idle":
                    # Warm white across all channels
                    sls.suspend()
                    for ch in range(960):
                        sls.rgb_fadein(ch, 255, 220, 160, 0)
                    sls.resume()

                elif scene == "presentation":
                    if not idle_show_task or idle_show_task.done():
                        idle_show_task = asyncio.create_task(realistic_idle_show())

                elif scene == "light_up":
                    idle_show_task = asyncio.create_task(_run_light_up())

                elif scene == "fade_out":
                    idle_show_task = asyncio.create_task(_run_fade_out())

                elif scene == "rainbow":

                    idle_show_task = asyncio.create_task(_run_rainbow())
                elif scene == "log_on":
                    pass

            elif command == "blackout":
                sls.blackout()

            elif command == "set_colour":
                sls.rgb(payload["channel"],
                        payload["r"], payload["g"], payload["b"])

            elif command == "ping":
                uptime = int(time.time() - START_TIME)
                await websocket.send(json.dumps(
                    {"status":"ok","command":"ping","uptime":uptime}))
                continue

            await websocket.send(json.dumps({"status": "ok", "command": command}))

        except Exception as e:
            log.error(f"Error: {e}")
            await websocket.send(json.dumps(
                {"status":"error","message":str(e)}))

async def main():
    global UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP, STATUS_COLOUR, INTERVAL

    log.info("Bridge starting — ws://0.0.0.0:8765")

    UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP = load_maps()
    STATUS_COLOUR, INTERVAL = load_settings()

    log.info(f"Configuration loaded from file: {CONFIG_PATH}")
    log.info(f"{len(UNIT_CHANNEL_MAP)} units successfully loaded")
    log.info(f"{len(FLOOR_CHANNEL_MAP)} floors successfully loaded")
    log.info(f"{len(STATUS_COLOUR)} state color combinations successfully loaded")

    async with websockets.serve(handle, "0.0.0.0", 8765):
        await asyncio.gather(
            asyncio.Future(), # run forever
            keepalive_loop(), # prevent SLS960 idle timeout
        )
asyncio.run(main())

"""
# ── Load config ──────────────────────────────────────────────
def load_maps():
    for path in (MAPS_PATH, SETTINGS_PATH):
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

    with open(MAPS_PATH) as f:
        maps = yaml.safe_load(f)
    with open(SETTINGS_PATH) as f:
        settings = yaml.safe_load(f)

    unit_channel_map = maps.get("unit_channel_map", {})

    floor_channel_map = {}
    for floor, range_data in maps.get("floor_channel_map", {}).items():
        if not isinstance(range_data, list) or len(range_data) != 2:
            raise ValueError(f"Invalid floor_channel_map entry for floor {floor}: {range_data}")
        start, end = map(int, range_data)
        floor_channel_map[int(floor)] = list(range(start, end + 1))

    status_colour = settings.get("status_colour", {})
    return unit_channel_map, floor_channel_map, status_colour"""