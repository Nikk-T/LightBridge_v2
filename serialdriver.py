import asyncio, logging, serial, time
from serial.tools import list_ports

from mdp_protocol import *
log = logging.getLogger("bridge.sls960")

class SLS960:

    RECONNECT_DELAY = 3
    MAX_RETRIES = 3

    def __init__(self, baud, port=None, vid=None, pid=None, name_hint=None):
        """
        port: fixed port (optional)
        vid/pid: USB vendor/product ID (best detection)
        name_hint: substring to match in device description
        """

        self.baud = baud
        self.port = port
        self.vid = vid
        self.pid = pid
        self.name_hint = name_hint
        self.ser = None

        self.connect()

    # -------------------------------------------------
    # Detect device
    # -------------------------------------------------
    def detect_port(self):

        ports = list_ports.comports()

        for p in ports:

            # VID/PID match (best)
            if self.vid and self.pid:
                if p.vid == self.vid and p.pid == self.pid:
                    return p.device

            # description match
            if self.name_hint and self.name_hint.lower() in (p.description or "").lower():
                return p.device

            # fallback common serial adapters
            if p.device.startswith("/dev/ttyUSB") or p.device.startswith("/dev/ttyACM"):
                return p.device

        return None

    # -------------------------------------------------
    # Connect serial
    # -------------------------------------------------
    def connect(self):

        while True:

            try:

                if not self.port:
                    self.port = self.detect_port()

                    if not self.port:
                        log.warning("SLS960 device not found — retrying...")
                        time.sleep(self.RECONNECT_DELAY)
                        continue

                log.info(f"Connecting to SLS960 on {self.port}")

                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1
                )

                log.info(f"SLS960 connected on {self.port} @ {self.baud}")
                return

            except serial.SerialException as e:

                log.error(f"Serial connect failed: {e}")
                self.port = None
                time.sleep(self.RECONNECT_DELAY)

    # -------------------------------------------------
    # Send with reconnect
    # -------------------------------------------------
    def send(self, data: bytes):

        for attempt in range(self.MAX_RETRIES):

            try:

                if not self.ser or not self.ser.is_open:
                    raise serial.SerialException("Serial not connected")

                self.ser.write(data)
                self.ser.flush()
                return

            except (serial.SerialException, OSError) as e:

                log.error(f"Serial write failed: {e}")

                try:
                    if self.ser:
                        self.ser.close()
                except:
                    pass

                self.port = None
                log.warning("Serial disconnected — reconnecting...")
                self.connect()

        log.error("Serial send failed after retries")

    # -------------------------------------------------
    # Commands
    # -------------------------------------------------
    def rgb(self, ch, r, g, b):
        self.send(cmd_rgb_level(ch, r, g, b))

    def rgb_fadein(self, ch, r, g, b, interval=10, step=60):
        s = lambda v: int(v / step) if v > 0 else 5
        self.send(cmd_rgb_fade(ch, r, interval, s(r), g, interval, s(g), b, interval, s(b)))

    def off(self, ch):
        self.send(cmd_off(ch))

    def blackout(self):
        self.send(cmd_broadcast_off())

    def suspend(self):
        self.send(cmd_subcmd(0, SUBCMD_SUSPEND))

    def resume(self):
        self.send(cmd_subcmd(0, SUBCMD_RESUME))

    def keepalive(self):
        self.send(cmd_nop(0))