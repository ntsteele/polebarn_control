#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mic Gain-Trim Calibrator (XR18) — Relative Mode, robust meter subscription

Flow:
  1) Ask for REFERENCE channel (e.g., 5). You mute it, place tone on grille, press ENTER.
     We capture that level as the reference target.
  2) Ask which channels to CALIBRATE (e.g., 1,2,6). For each:
     - Prompt: MUTE, apply tone, press ENTER.
     - Measure → auto-trim /ch/NN/preamp/gain until it matches the reference (±1 dB).
     - Print "good to go", then move to next.

Meter robustness:
  - Handles /meters/1 and /meters/0.
  - Uses subscription + direct request + batchsubscribe/renew fallback.
  - Prints a one-time confirmation when meters start arriving.

Safety:
  - Reads pre-processing input meters (pre-EQ/comp/fader/mute).
  - Only writes /ch/NN/preamp/gain (0..60 dB, 0.5 dB steps).

Default XR18 IP: 192.168.4.136 (override with env XAIRMIX_IP)
Logs: ~/polebarn_control/calibration/gain_logs/gain_trim_YYYYmmdd_HHMMSS.log
"""

import os, socket, struct, time, threading, math
from datetime import datetime
from pathlib import Path

# ─────────────── CONFIG ───────────────
XR18_IP        = os.environ.get("XAIRMIX_IP", "192.168.4.136")
XR18_PORT      = 10024
LOCAL_PORT     = 10025       # local UDP port to receive replies/meters
TOLERANCE_DB   = 1.0         # ±1 dB window
MAX_ITERS      = 10          # max gain correction loops per channel
SAMPLE_SEC     = 1.2         # averaging window for meter reads
KEEPALIVE_SEC  = 8.0         # /xremote cadence
GAIN_MIN_DB    = 0.0
GAIN_MAX_DB    = 60.0
GAIN_STEP_DB   = 0.5         # quantize to 0.5 dB steps

# Log dir inside project
PROJECT_ROOT   = Path(__file__).resolve().parents[1]  # ~/polebarn_control
LOG_DIR        = PROJECT_ROOT / "calibration" / "gain_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────── Minimal OSC helpers ───────────────
def _pad4(b: bytes) -> bytes:
    return b + (b"\x00" * ((4 - (len(b) % 4)) % 4))

def osc_pack(address: str, *args):
    # Build an OSC packet with address and typed args (float,int,str,blob(bytes))
    types = [","]
    data  = b""
    for a in args:
        if isinstance(a, float):
            types.append("f"); data += struct.pack(">f", a)
        elif isinstance(a, int):
            types.append("i"); data += struct.pack(">i", a)
        elif isinstance(a, (bytes, bytearray)):
            types.append("b"); data += struct.pack(">i", len(a)) + _pad4(a)
        else:  # string
            types.append("s"); data += _pad4(str(a).encode("utf-8") + b"\x00")
    addr = _pad4(address.encode("utf-8") + b"\x00")
    typetag = _pad4("".join(types).encode("utf-8") + b"\x00")
    return addr + typetag + data

def osc_unpack(msg: bytes):
    # Return (address:str, [types], [values])
    def read_padded_str(off):
        end = msg.find(b"\x00", off)
        s = msg[off:end].decode("utf-8")
        off = (end + 4) & ~3
        return s, off
    off = 0
    address, off = read_padded_str(off)
    typetag, off = read_padded_str(off)
    types = typetag[1:] if typetag.startswith(",") else ""
    vals = []
    for t in types:
        if t == "f":
            vals.append(struct.unpack(">f", msg[off:off+4])[0]); off += 4
        elif t == "i":
            vals.append(struct.unpack(">i", msg[off:off+4])[0]); off += 4
        elif t == "s":
            s, off = read_padded_str(off); vals.append(s)
        elif t == "b":
            size = struct.unpack(">i", msg[off:off+4])[0]; off += 4
            blob = msg[off:off+size]; off = (off + size + 3) & ~3
            vals.append(blob)
    return address, list(types), vals

# ─────────────── XR18 session (send+receive on SAME port) ───────────────
class XR18:
    def __init__(self, xr_ip, xr_port, local_port):
        self.xr_ip, self.xr_port = xr_ip, xr_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", local_port))
        self.sock.setblocking(False)

        # state
        self.meters = [None] * 40
        self.names  = {}       # ch:int -> str
        self.gains  = {}       # ch:int -> float
        self._lock  = threading.Lock()
        self._running = True

        self.last_meter_ts = 0.0
        self.meters_seen_once = False  # print a one-time confirmation
        self._meter_count_last = 0

        # RX + keepalive threads
        self.recv_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.recv_thread.start()
        self.keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self.keepalive_thread.start()

        # prime: start push updates and try meters a few ways
        self.touch()
        time.sleep(0.05)
        self.subscribe_meters()
        time.sleep(0.05)
        self.request_meters_once()
        time.sleep(0.05)
        self.batch_subscribe()

    # ── outbound ──────────────────────────────────────────────────────
    def send(self, address, *args):
        pkt = osc_pack(address, *args)
        self.sock.sendto(pkt, (self.xr_ip, self.xr_port))

    def touch(self):
        self.send("/xremote")

    def subscribe_meters(self):
        # Subscribe to input meters (/meters/1). Lease ~10s; refresh as needed.
        # Format: /meters ,sii "/meters/1" time_factor updates
        self.send("/meters", "/meters/1", 2, 200)
        # Some firmwares expose inputs as /meters/0 — subscribe that too:
        self.send("/meters", "/meters/0", 2, 200)

    def request_meters_once(self):
        # Ask for a one-shot meter frame (if supported)
        self.send("/meters/1")
        self.send("/meters/0")

    def batch_subscribe(self):
        # Fallback batch subscription with a token; renew occasionally
        self.send("/batchsubscribe", "mtrs", "/meters/1", 0, 0, 0)
        self.send("/batchsubscribe", "mtrs0", "/meters/0", 0, 0, 0)

    def batch_renew(self):
        self.send("/renew", "mtrs")
        self.send("/renew", "mtrs0")

    def request_name(self, ch):
        self.send(f"/ch/{ch:02d}/config/name")

    def request_gain(self, ch):
        self.send(f"/ch/{ch:02d}/preamp/gain")

    def set_gain(self, ch, gain_db):
        self.send(f"/ch/{ch:02d}/preamp/gain", float(gain_db))

    # ── background loops ──────────────────────────────────────────────
    def _keepalive_loop(self):
        while self._running:
            try:
                self.touch()
                # periodically renew everything
                self.subscribe_meters()
                self.batch_renew()
            except Exception:
                pass
            time.sleep(KEEPALIVE_SEC)

    def close(self):
        self._running = False
        try: self.sock.close()
        except: pass

    def _rx_loop(self):
        while self._running:
            try:
                data, _ = self.sock.recvfrom(16384)
            except BlockingIOError:
                time.sleep(0.005); continue
            except OSError:
                break
            try:
                addr, types, vals = osc_unpack(data)
                self._dispatch(addr, types, vals)
            except Exception:
                # ignore malformed
                pass

    # ── inbound handlers ─────────────────────────────────────────────
    def _dispatch(self, address, types, vals):
        if address in ("/meters/1", "/meters/0"):
            floats = []
            if len(types) == 1 and types[0] == "b" and vals:
                blob = vals[0]
                if len(blob) >= 8:
                    n = struct.unpack("<I", blob[4:8])[0]  # LE uint32 count
                    data = blob[8:8 + 4*n]
                    if n > 0 and len(data) >= 4 and (len(data) % 4) == 0:
                        floats = list(struct.unpack("<%df" % (len(data)//4), data))
            else:
                # some firmwares send plain float list
                floats = [float(v) for v in vals if isinstance(v, float)]

            if floats:
                with self._lock:
                    for i in range(min(len(self.meters), len(floats))):
                        self.meters[i] = floats[i]
                self.last_meter_ts = time.time()
                if not self.meters_seen_once:
                    self.meters_seen_once = True
                    self._meter_count_last = len(floats)
                    print(f"🔎 Meters active: received {len(floats)} floats on {address}.")
            return

        if address.startswith("/ch/") and address.endswith("/config/name") and vals:
            try:
                ch = int(address.split("/")[2]); name = vals[0]
                with self._lock: self.names[ch] = name
            except: pass
            return

        if address.startswith("/ch/") and address.endswith("/preamp/gain") and vals:
            try:
                ch = int(address.split("/")[2]); gain = float(vals[0])
                with self._lock: self.gains[ch] = gain
            except: pass
            return

    # ── getters ──────────────────────────────────────────────────────
    def get_meter_linear(self, ch):
        with self._lock:
            return self.meters[ch-1] if 1 <= ch <= len(self.meters) else None

    def get_name(self, ch, fallback=None):
        with self._lock:
            return self.names.get(ch, fallback)

    def get_gain(self, ch):
        with self._lock:
            return self.gains.get(ch)

# ─────────────── Utilities ───────────────
def dbfs_from_linear(v):
    if v is None or v <= 0.0:
        return -90.0
    return 20.0 * math.log10(v)

def median(values):
    xs = sorted(values)
    n = len(xs)
    return xs[n//2] if n % 2 else 0.5 * (xs[n//2 - 1] + xs[n//2])

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def quantize(db):
    return round(db / GAIN_STEP_DB) * GAIN_STEP_DB

def ensure_meters_flow(xr: XR18, timeout_s=1.0):
    """
    Make a best-effort to get meter frames arriving.
    Called before each measurement and when we detect stale frames.
    """
    now = time.time()
    if now - xr.last_meter_ts < 0.3:
        return  # already flowing

    # Try subscription, direct request, and batch methods
    xr.subscribe_meters()
    time.sleep(0.05)
    xr.request_meters_once()
    time.sleep(0.05)
    xr.batch_subscribe()
    xr.batch_renew()

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if time.time() - xr.last_meter_ts < 0.3:
            return
        time.sleep(0.05)

def sample_db(xr: XR18, ch: int, seconds=SAMPLE_SEC):
    ensure_meters_flow(xr, timeout_s=0.8)
    t0 = time.time()
    window = []
    while time.time() - t0 < seconds:
        v = xr.get_meter_linear(ch)
        db = dbfs_from_linear(v)
        if db > -80.0:   # ignore "no signal" values
            window.append(db)
        else:
            # If we see a lot of -90, try nudging subscription again
            ensure_meters_flow(xr, timeout_s=0.2)
        time.sleep(0.05)
    return median(window) if window else -90.0

# ─────────────── Core calibration routines ───────────────
def capture_reference(xr: XR18, ref_ch: int):
    xr.request_name(ref_ch)
    xr.request_gain(ref_ch)
    time.sleep(0.2)
    ref_name = xr.get_name(ref_ch, f"CH{ref_ch}")
    input(f"\n🎯 Reference → {ref_name} (CH{ref_ch}): MUTE the channel, place tone (or consistent vocal) on the grille.\n    Press ENTER to capture reference level… ")
    ref_db = sample_db(xr, ref_ch, seconds=SAMPLE_SEC)
    while ref_db <= -60.0:
        print("     ⚠️ Very low reference detected — reseat tone generator / get closer / raise level.")
        input("     Press ENTER to re-measure reference… ")
        ref_db = sample_db(xr, ref_ch, seconds=SAMPLE_SEC)
    print(f"   • Reference locked at {ref_db:.1f} dBFS\n")
    return ref_db, ref_name

def calibrate_channel(xr: XR18, ch: int, target_dbfs: float, logf):
    xr.request_name(ch)
    xr.request_gain(ch)
    time.sleep(0.2)

    name = xr.get_name(ch, f"CH{ch}")
    cur_gain = xr.get_gain(ch)
    if cur_gain is None:
        cur_gain = 30.0  # benign default until mixer replies

    input(f"\n▶️  {name} (CH{ch}): MUTE the channel, place tone on the grille.\n    Press ENTER to measure and auto-trim to {target_dbfs:.1f} dBFS… ")

    for attempt in range(1, MAX_ITERS + 1):
        measured = sample_db(xr, ch, seconds=SAMPLE_SEC)
        diff = target_dbfs - measured
        print(f"   • Read {measured:.1f} dBFS vs target {target_dbfs:+.1f} → diff {diff:+.1f} dB")
        logf.write(f"CH{ch:02d} {name}: read {measured:.1f} dBFS, diff {diff:+.1f}\n"); logf.flush()

        if measured <= -60.0:
            print("     ⚠️ Very low input — reseat tone / verify it's really hitting the mic.")
            input("     Press ENTER to re-measure… ")
            continue

        if abs(diff) <= TOLERANCE_DB:
            print(f"✅ {name} (CH{ch}) within ±{TOLERANCE_DB:.1f} dB at {measured:.1f} dBFS — good to go.")
            logf.write("OK: converged.\n\n"); logf.flush()
            return

        cur_gain = xr.get_gain(ch) or cur_gain
        new_gain = quantize(clamp(cur_gain + diff, GAIN_MIN_DB, GAIN_MAX_DB))
        if abs(new_gain - cur_gain) < 0.1:
            print(f"     ⚠️ Gain change too small or at limit; holding at {cur_gain:.1f} dB.")
            logf.write("WARN: small/limited step.\n\n"); logf.flush()
            return

        xr.set_gain(ch, new_gain)
        print(f"     ↳ Set preamp gain: {cur_gain:.1f} dB → {new_gain:.1f} dB (step {new_gain - cur_gain:+.1f})")
        logf.write(f"SET: gain {cur_gain:.1f} → {new_gain:.1f}\n"); logf.flush()
        cur_gain = new_gain
        time.sleep(0.9)  # settle
        # keep trying to keep meters alive during iteration
        ensure_meters_flow(xr, timeout_s=0.2)

    print(f"⚠️  {name} (CH{ch}) did not converge within {MAX_ITERS} iterations — review above.")
    logf.write("WARN: max iterations reached.\n\n"); logf.flush()

# ─────────────── Main ───────────────
def main():
    print(f"XR18 @ {XR18_IP}:{XR18_PORT}   (listening UDP {LOCAL_PORT})")
    xr = XR18(XR18_IP, XR18_PORT, LOCAL_PORT)

    try:
        ref_raw = input("Which channel is your REFERENCE mic? (e.g., 5): ").strip()
        if not ref_raw.isdigit():
            print("Invalid reference channel. Exiting."); return
        ref_ch = int(ref_raw)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"gain_trim_{ts}.log"
        with open(log_path, "a", encoding="utf-8") as logf:
            logf.write(f"Mic Gain Trim — RELATIVE — {ts}\nXR18 {XR18_IP}:{XR18_PORT}\n\n")

            ref_db, ref_name = capture_reference(xr, ref_ch)
            logf.write(f"REFERENCE: {ref_name} CH{ref_ch} = {ref_db:.1f} dBFS\n\n")

            raw = input("Which channels to CALIBRATE? (e.g., 1,2,6): ").strip()
            chans = [int(x) for x in raw.replace(";", ",").split(",") if x.strip().isdigit()]

            # de-dup + drop the reference if included
            seen = set([ref_ch]); to_cal = []
            for c in chans:
                if c not in seen:
                    to_cal.append(c); seen.add(c)
            if not to_cal:
                print("No channels to calibrate. Exiting.")
                print(f"Reference was locked at {ref_db:.1f} dBFS. Log: {log_path}")
                return

            for ch in to_cal:
                calibrate_channel(xr, ch, ref_db, logf)

        print(f"\n🎯 Done. Reference: {ref_db:.1f} dBFS on CH{ref_ch}.")
        print(f"🗒️  Log saved to {log_path}")
    finally:
        xr.close()

if __name__ == "__main__":
    main()
