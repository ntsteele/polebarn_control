#!/usr/bin/env python3
"""
OSC → QLC+ WebAccess Bridge (Pi WebAccess compatible)
-----------------------------------------------------
Listens for:
  /QLC+/Function/Start i <id>
  /QLC+/Function/Stop  i <id>
and forwards to QLC+'s built-in web control URLs:
  http://<host>:9999/?function=<id>&action=start|stop
"""

from pythonosc import dispatcher, osc_server
import requests, logging, sys

QLC_HOST = "127.0.0.1"
QLC_PORT = 9999
QLC_URL  = f"http://{QLC_HOST}:{QLC_PORT}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [osc_bridge] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def send_to_qlc(func_id, action):
    """Send simple GET to QLC+ WebAccess"""
    url = f"{QLC_URL}/?function={func_id}&action={action}"
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            logging.info(f"✅ {action.title()} Function {func_id}")
        else:
            logging.warning(f"⚠️  {action.title()} Function {func_id} → HTTP {r.status_code}")
    except Exception as e:
        logging.error(f"❌ Error {action} function {func_id}: {e}")

def start_function(addr, func_id):
    send_to_qlc(func_id, "start")

def stop_function(addr, func_id):
    send_to_qlc(func_id, "stop")

def run_server(host="0.0.0.0", port=7700):
    disp = dispatcher.Dispatcher()
    disp.map("/QLC+/Function/Start", start_function)
    disp.map("/QLC+/Function/Stop",  stop_function)

    server = osc_server.ThreadingOSCUDPServer((host, port), disp)
    logging.info(f"✅ OSC → QLC+ Bridge listening on {host}:{port}")
    logging.info(f"→ Forwarding to {QLC_URL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Bridge stopped by user")

if __name__ == "__main__":
    run_server()
