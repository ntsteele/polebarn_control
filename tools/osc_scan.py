#!/usr/bin/env python3
from pythonosc.udp_client import SimpleUDPClient
import time

XR18_IP = "192.168.4.136"
XR18_PORT = 10024
c = SimpleUDPClient(XR18_IP, XR18_PORT)

print("🔍 Scanning possible mute paths…")
paths = [
    "/ch/01/mix/mute",
    "/ch/01/mix/on",
    "/main/st/mute",
    "/lr/mute",
    "/aux/06/mute",
    "/bus/06/mute",
]
for p in paths:
    print(f" → sending {p}")
    c.send_message(p, 1)
    time.sleep(0.5)
    c.send_message(p, 0)
    time.sleep(0.5)

print("✅ Scan complete. Watch the XR18 meters and mute lights.")
