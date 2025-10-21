#!/usr/bin/env python3
"""
XR18 Probe CLI – uses core.osc_client.XR18 (single-socket client)
"""
import argparse, time
from core.osc_client import XR18

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--local-port", type=int, default=0)
    ap.add_argument("--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("watch")

    g1 = sub.add_parser("get-name"); g1.add_argument("ch", type=int)
    s1 = sub.add_parser("set-name"); s1.add_argument("ch", type=int); s1.add_argument("name")

    mut = sub.add_parser("mute"); mut.add_argument("target", choices=["main","aux6","sub"]); mut.add_argument("state", choices=["on","off"])
    chm = sub.add_parser("ch-mute"); chm.add_argument("ch", type=int); chm.add_argument("state", choices=["on","off"])
    fad = sub.add_parser("fader"); fad.add_argument("ch", type=int); fad.add_argument("linear", type=float)

    eqo = sub.add_parser("eq-on"); eqo.add_argument("ch", type=int); eqo.add_argument("state", choices=["on","off"])
    geq = sub.add_parser("get-eq-on"); geq.add_argument("ch", type=int)

    raw = sub.add_parser("send"); raw.add_argument("address"); raw.add_argument("args", nargs="*")

    args = ap.parse_args()
    xr = XR18(args.ip, args.local_port, verbose=args.verbose)
    xr.start()
    try:
        if args.cmd == "watch":
            print("Watching… Ctrl-C to stop.")
            while True:
                msg = xr.get_message(timeout=0.3)
                if msg:
                    ts, addr, vals = msg
                    print(addr, *vals)

        elif args.cmd == "get-name":
            xr.get_channel_name(args.ch)

        elif args.cmd == "set-name":
            xr.set_channel_name(args.ch, args.name)

        elif args.cmd == "mute":
            xr.set_mute(args.target, mute=(args.state == "on"))

        elif args.cmd == "ch-mute":
            xr.set_channel_mute(args.ch, mute=(args.state == "on"))

        elif args.cmd == "fader":
            xr.set_channel_fader(args.ch, args.linear)

        elif args.cmd == "eq-on":
            xr.set_eq_on(args.ch, args.state == "on")

        elif args.cmd == "get-eq-on":
            xr.get_eq_on(args.ch)

        elif args.cmd == "send":
            # quick type coercion: int, then float, else string
            coerced = []
            for a in args.args:
                try:
                    coerced.append(int(a)); continue
                except ValueError:
                    pass
                try:
                    coerced.append(float(a)); continue
                except ValueError:
                    coerced.append(a)
            xr.send(args.address, *coerced)

        # give responses ~2s to arrive
        deadline = time.time() + 2.0
        while time.time() < deadline:
            msg = xr.get_message(timeout=0.1)
            if msg:
                ts, addr, vals = msg
                print(addr, *vals)

    finally:
        xr.stop()

if __name__ == "__main__":
    main()
