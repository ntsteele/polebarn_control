#!/usr/bin/env python3
import time, json, os
from pathlib import Path
from datetime import datetime
from parse_qxw import parse_qlc_workspace

# Paths
QLC_PATH = Path("/home/pi/QLCplus/workspaces/Polebarn_Master_GOOD.qxw")
OUT_PATH = Path("/tmp/qlc_workspace.json")

# Optional: notify the Polebarn web server via SocketIO
NOTIFY_WEB = True
WEB_SOCKET_URL = "http://localhost:5055"

def notify_websocket(summary):
    """Emit update event to Polebarn web server if enabled."""
    try:
        import socketio
        sio = socketio.SimpleClient()
        sio.connect(WEB_SOCKET_URL)
        sio.emit("qlc:update", summary)
        sio.disconnect()
    except Exception as e:
        print(f"[watchdog] (optional) socket emit failed: {e}")

def main():
    print(f"[watchdog] Watching: {QLC_PATH}")
    last_mtime = 0

    while True:
        try:
            if QLC_PATH.exists():
                mtime = QLC_PATH.stat().st_mtime
                if mtime != last_mtime:
                    print(f"[watchdog] Detected change → re-parsing {QLC_PATH.name}")
                    data = parse_qlc_workspace(QLC_PATH)
                    data["timestamp"] = datetime.now().isoformat(timespec="seconds")
                    summary = data.get("summary", {})
                    OUT_PATH.write_text(json.dumps(data, indent=2))
                    print(f"[watchdog] Updated {OUT_PATH} ({summary})")
                    if NOTIFY_WEB:
                        notify_websocket(summary)
                    last_mtime = mtime
            else:
                print(f"[watchdog] File not found: {QLC_PATH}")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[watchdog] Stopped by user.")
            break
        except Exception as e:
            print(f"[watchdog] Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
