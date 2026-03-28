# mdp_protocol.py — Confirmed MDP serial packet builder
# Based on LightSwarm LS001 Rev 0.18 / SLS960 V1.06

SLIP_END = 0xC0 # 192 decimal
SLIP_ESC = 0xDB # 219 decimal
SLIP_ESC_END = 0xDC # Replaces END byte within data
SLIP_ESC_ESC = 0xDD # Replaces ESC byte within data

# MDP Command codes
MDP_NOP = 0x00
MDP_ON = 0x20
MDP_OFF = 0x21
MDP_LEVEL = 0x22
MDP_FADE = 0x23
MDP_RGB_LEVEL = 0x2C # Primary command for RGB colour control
MDP_RGB_FADE = 0x31 # Smooth colour transitions
MDP_SUBCMD = 0x7C # Suspend/Resume for bulk updates

SUBCMD_NOP = 0x00
SUBCMD_SUSPEND = 0x01 # Hold LED output — batch update in progress
SUBCMD_RESUME = 0x02 # Release — all channels update simultaneously

BROADCAST_ADDR = 0xFFFF # All channels execute command

def slip_encode(data: bytes) -> bytes:
 """Wrap MDP Layer 3 frame in SLIP framing per RFC 1055."""
 out = bytearray([SLIP_END]) # Leading END flushes receiver buffer
 for byte in data:
  if byte == SLIP_END:
   out += bytes([SLIP_ESC, SLIP_ESC_END])
  elif byte == SLIP_ESC:
   out += bytes([SLIP_ESC, SLIP_ESC_ESC])
  else:
   out.append(byte)
 out.append(SLIP_END) # Trailing END marks packet boundary
 return bytes(out)

def checksum(data: bytes) -> int:
 """XOR of all preceding bytes starting from first address byte."""
 result = 0
 for b in data: result ^= b
 return result

def make_packet(address: int, cmd: int, info: bytes = b"") -> bytes:
 """Build a complete SLIP-framed MDP packet."""
 addr_hi = (address >> 8) & 0xFF
 addr_lo = address & 0xFF
 payload = bytes([addr_hi, addr_lo, cmd]) + info
 return slip_encode(payload + bytes([checksum(payload)]))

# ── High-level command builders ──────────────────────────────
def cmd_rgb_level(address: int, r: int, g: int, b: int) -> bytes:
 """MDP_RGB_LEVEL — set RGB colour for one LED (address 0-based)."""
 return make_packet(address, MDP_RGB_LEVEL, bytes([r, g, b]))

def cmd_off(address: int) -> bytes:
 """MDP_OFF — turn channel off."""
 return make_packet(address, MDP_OFF)

def cmd_on(address: int) -> bytes:
 """MDP_ON — set channel to full brightness."""
 return make_packet(address, MDP_ON)

def cmd_level(address: int, level: int) -> bytes:
 """MDP_LEVEL — set mono brightness 0–255."""
 return make_packet(address, MDP_LEVEL, bytes([level]))

def cmd_rgb_fade(address: int,
 r_lvl, r_int, r_step,
 g_lvl, g_int, g_step,
 b_lvl, b_int, b_step) -> bytes:
 """MDP_RGB_FADE — smooth simultaneous fade on R/G/B.
 interval = 1/100 second units. step = increment per interval.
 Example: fade to red over ~1 sec: r_lvl=255,r_int=5,r_step=10
 """
 info = bytes([r_lvl, r_int, r_step, g_lvl, g_int, g_step, b_lvl, b_int, b_step])
 return make_packet(address, MDP_RGB_FADE, info)

def cmd_subcmd(address: int, subcmd: int) -> bytes:
 """MDP_SUBCMD — Suspend or Resume LED output."""
 return make_packet(address, MDP_SUBCMD, bytes([subcmd]))

def cmd_broadcast_off() -> bytes:
 """Blackout — MDP_OFF to broadcast address 0xFFFF."""
 return make_packet(BROADCAST_ADDR, MDP_OFF)

def cmd_nop(address: int = 0) -> bytes:
 """MDP_NOP — keepalive, no visible effect."""
 return make_packet(address, MDP_NOP)

# ── Checksum verification example (from LS001 spec) ──────────
# Send MDP_OFF to address 0x0005:
# payload = [0x00, 0x05, 0x21] checksum = 0x00 XOR 0x05 XOR 0x21 = 0x24
# SLIP frame: C0 00 05 21 24 C0