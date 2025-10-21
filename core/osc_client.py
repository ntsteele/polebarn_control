#!/usr/bin/env python3
"""
XR18 / X-Air OSC Client – single-socket TX/RX (+ bundle-aware decoder)
- ONE UDP socket/port for both sending and receiving (required for /xremote)
- Periodic /xremote heartbeat so the mixer streams updates back to THIS port
- Decodes normal OSC messages and OSC #bundle replies
- High-level helpers: get/set channel name, on/mute, fader, EQ on/off + per-band gain
"""

import socket
import threading
import time
import queue
import struct
from typing import List, Tuple
from pythonosc.osc_message_builder import OscMessageBuilder

XR18_PORT     = 10024
HEARTBEAT_SEC = 5.0
RECV_BUFSIZE  = 8192

# ───────────────────────────── utils ─────────────────────────────

def _fmt_ch(n: int) -> str:
    return f"{int(n):02d}"

def _build(address, *args) -> bytes:
    mb = OscMessageBuilder(address=address)
    for a in args:
        mb.add_arg(a)
    return mb.build().dgram

def _read_padded_string(data: bytes, i: int):
    """Read a null-terminated, 4-byte-padded OSC string; return (string, next_idx)."""
    j = data.find(b"\x00", i)
    if j < 0:
        return "", len(data)
    s = data[i:j].decode("utf-8", errors="replace")
    i = (j + 4) & ~0x03
    return s, i

def _decode_message(data: bytes, i: int):
    """
    Decode ONE OSC message from data[i:].
    Returns: ((address:str, args:list), next_idx)
    """
    address, i = _read_padded_string(data, i)

    # typetags (string starting with comma)
    if i >= len(data) or data[i:i+1] != b",":
        return (address, []), i
    types, i = _read_padded_string(data, i + 1)  # skip comma

    args = []
    for t in types:
        if t == "i":
            v = struct.unpack(">i", data[i:i+4])[0]; i += 4; args.append(v)
        elif t == "f":
            v = struct.unpack(">f", data[i:i+4])[0]; i += 4; args.append(v)
        elif t == "s":
            v, i = _read_padded_string(data, i); args.append(v)
        elif t == "b":
            n = struct.unpack(">i", data[i:i+4])[0]; i += 4
            blob = data[i:i+n]; i = (i + n + 3) & ~0x03
            args.append(blob)
        else:
            # Common extras
            if t == "d":      # 64-bit float
                v = struct.unpack(">d", data[i:i+8])[0]; i += 8; args.append(v)
            elif t == "T":    # True
                args.append(True)
            elif t == "F":    # False
                args.append(False)
            else:
                break
    return (address, args), i

def _decode_osc_all(data: bytes):
    """
    Decode an OSC datagram (message or #bundle) into a list of (address, args).
    XR18 often replies with #bundle containing one or more messages.
    """
    out = []
    if data.startswith(b"#bundle\x00"):
        # "#bundle\0" (8) + timetag (8)
        i = 16
        while i + 4 <= len(data):
            sz = struct.unpack(">i", data[i:i+4])[0]; i += 4
            elem = data[i:i+sz]; i += sz
            try:
                (addr, args), _ = _decode_message(elem, 0)
                out.append((addr, args))
            except Exception:
                out.append(("<unparsed>", []))
        return out
    else:
        try:
            (addr, args), _ = _decode_message(data, 0)
            return [(addr, args)]
        except Exception:
            return [("<unparsed>", [])]

# ───────────────────────────── client ────────────────────────────

class XR18:
    def __init__(self, ip: str, local_port: int = 0, verbose: bool = False):
        self.ip = ip
        self.remote = (ip, XR18_PORT)
        self.verbose = verbose

        # One UDP socket for BOTH send & receive
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow quick rebinding if we restart the watcher
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Optional: allow multiple processes to bind same port (Linux only)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass

        # Bind to chosen port (0 = random free port)
        self.sock.bind(("", local_port))
        self.sock.setblocking(False)
        self.local_port = self.sock.getsockname()[1]

        self.running = False
        self.msg_q: "queue.Queue[tuple[float,str,list]]" = queue.Queue()

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        if self.running:
            return
        self.running = True

        # Kick /xremote immediately, from THIS same socket/port
        self._send_raw(_build("/xremote"))

        # Threads
        self.rx_t = threading.Thread(target=self._rx_loop, daemon=True)
        self.hb_t = threading.Thread(target=self._hb_loop, daemon=True)
        self.rx_t.start()
        self.hb_t.start()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass

    def _rx_loop(self):
        while self.running:
            try:
                data, _ = self.sock.recvfrom(RECV_BUFSIZE)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            ts = time.time()
            for address, args in _decode_osc_all(data):
                self.msg_q.put((ts, address, args))
                if self.verbose:
                    pretty = " ".join(
                        f"{a:.3f}" if isinstance(a, float) else
                        (a if isinstance(a, str) else str(a))
                        for a in args
                    )
                    print(f"{address} {pretty}".rstrip())

    def _hb_loop(self):
        while self.running:
            time.sleep(HEARTBEAT_SEC)
            self._send_raw(_build("/xremote"))

    # ── tx helpers ────────────────────────────────────────────────────────────
    def _send_raw(self, datagram: bytes):
        self.sock.sendto(datagram, self.remote)

    def send(self, address: str, *args):
        self._send_raw(_build(address, *args))

    # public raw sender (used by CLI)
    def send_raw(self, address: str, *args):
        self._send_raw(_build(address, *args))

    def get_message(self, timeout: float = 0.25):
        try:
            return self.msg_q.get(timeout=timeout)
        except queue.Empty:
            return None

    # ── high-level API ────────────────────────────────────────────────────────
    def ch_path(self, ch: int) -> str:
        return f"/ch/{_fmt_ch(ch)}"

    # Names
    def get_channel_name(self, ch: int):
        self.send(f"{self.ch_path(ch)}/config/name")

    def set_channel_name(self, ch: int, name: str):
        self.send(f"{self.ch_path(ch)}/config/name", name)

    # On/Mute/Fader
    def set_channel_on(self, ch: int, on: bool):
        self.send(f"{self.ch_path(ch)}/mix/on", 1 if on else 0)

    def set_channel_mute(self, ch: int, mute: bool):
        self.set_channel_on(ch, not mute)

    def set_channel_fader(self, ch: int, fader_linear: float):
        self.send(f"{self.ch_path(ch)}/mix/fader", float(fader_linear))

    def set_mute(self, target: str, mute: bool):
        t = target.lower()
        if t in ("main", "lr", "st"):
            # 1 = muted, 0 = unmuted
            self.send("/main/st/mute", 1 if mute else 0)
        elif t in ("aux6", "bus6", "sub"):
            self.send("/aux/06/mute", 1 if mute else 0)
        else:
            raise ValueError("Unknown target for set_mute().")

    # EQ
    def set_eq_on(self, ch: int, is_on: bool):
        self.send(f"{self.ch_path(ch)}/eq/on", 1 if is_on else 0)

    def get_eq_on(self, ch: int):
        self.send(f"{self.ch_path(ch)}/eq/on")

    def set_eq_gain(self, ch: int, band: int, gain_db: float):
        assert 1 <= band <= 4, "band must be 1..4"
        self.send(f"{self.ch_path(ch)}/eq/{int(band)}/gain", float(gain_db))

    def get_eq_gain(self, ch: int, band: int):
        assert 1 <= band <= 4, "band must be 1..4"
        self.send(f"{self.ch_path(ch)}/eq/{int(band)}/gain")
