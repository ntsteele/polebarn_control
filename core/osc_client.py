#!/usr/bin/env python3
"""
XR18 / X-Air OSC Control  –  Polebarn Project
Handles muting/unmuting both channel strips and output busses.
"""

import socket, time

XR18_IP   = "192.168.4.136"
XR18_PORT = 10024

def _send(addr, value: float = 0.0):
    """Low-level OSC packet."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg  = addr.encode() + b"\x00,f\x00\x00" + (value).hex().encode()
    sock.sendto(msg, (XR18_IP, XR18_PORT))
    sock.close()

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def mute_all():
    """Mute all test channels (17/18) and both output busses."""
    for addr in [
        "/ch/17/mix/on", "/ch/18/mix/on",
        "/main/st/mute", "/aux/6/mute"
    ]:
        _send(addr, 0.0)   # 0 = OFF for ch/on, 1 = MUTE for bus
        time.sleep(0.05)

def unmute_for(bus):
    """Unmute only what we’re testing."""
    mute_all()
    if bus == "MainL":
        _send("/ch/17/mix/on", 1.0)
        _send("/main/st/mute", 0.0)
    elif bus == "MainR":
        _send("/ch/18/mix/on", 1.0)
        _send("/main/st/mute", 0.0)
    elif bus == "Subwoofer":
        # Sub from Aux 6 only
        _send("/ch/17/mix/on", 1.0)
        _send("/ch/18/mix/on", 1.0)
        _send("/aux/6/mute", 0.0)
    time.sleep(0.1)
