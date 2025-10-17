#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import json
from pathlib import Path

QLC_WORKSPACE = Path("/home/pi/QLCplus/workspaces/Polebarn_Master_GOOD.qxw")

def parse_qlc_workspace(path: Path = QLC_WORKSPACE):
    """
    Parse a QLC+ workspace (.qxw) for Fixtures, Functions, Universes,
    and OSC/DMX plugin settings.
    """
    path = Path(path)
    if not path.exists():
        return {"error": f"QLC+ workspace not found: {path}"}

    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as e:
        return {"error": f"Failed to parse {path}: {e}"}

    # ─── Helper: strip XML namespaces ─────────────────────────────
    def strip_ns(tag):
        return tag.split('}', 1)[-1] if '}' in tag else tag

    for elem in root.iter():
        elem.tag = strip_ns(elem.tag)

    fixtures, universes, osc_plugins = [], [], []
    functions = []

    # ─── Fixtures ──────────────────────────────
    for fx in root.findall(".//Fixture"):
        fixtures.append({
            "id": fx.findtext("ID", "Unknown"),
            "name": fx.findtext("Name", "Unnamed Fixture"),
            "model": fx.findtext("Model", "Unknown Model"),
            "universe": fx.findtext("Universe", "0"),
            "address": fx.findtext("Address", "0"),
            "channels": fx.findtext("Channels", "0")
        })

    # ─── Functions ─────────────────────────────
    for fn in root.findall(".//Function"):
        fid = fn.attrib.get("ID", "")
        ftype = fn.attrib.get("Type", "Unknown")
        fname = fn.attrib.get("Name", f"Function {fid}")
        functions.append({
            "id": fid,
            "type": ftype,
            "name": fname
        })

    # ─── Universes + I/O ───────────────────────
    for uni in root.findall(".//Universe"):
        udata = {
            "name": uni.attrib.get("Name", ""),
            "id": uni.attrib.get("ID", ""),
            "inputs": [],
            "outputs": [],
            "universe_type": "DMX" if "ArtNet" in ET.tostring(uni).decode() else "Other"
        }

        # Input section
        for inp in uni.findall("Input"):
            udata["inputs"].append({
                "plugin": inp.attrib.get("Plugin", ""),
                "uid": inp.attrib.get("UID", ""),
                "line": inp.attrib.get("Line", "")
            })
            if inp.attrib.get("Plugin", "") == "OSC":
                osc_plugins.append(inp.attrib.get("UID", ""))

        # Output section
        for outp in uni.findall("Output"):
            plugin = outp.attrib.get("Plugin", "")
            uid = outp.attrib.get("UID", "")
            line = outp.attrib.get("Line", "")
            params_node = outp.find("PluginParameters")
            params = {k: v for k, v in params_node.attrib.items()} if params_node is not None else {}

            target_ip = params.get("outputIP", "")
            protocol = "ArtNet" if plugin == "ArtNet" else plugin or "Unknown"

            udata["outputs"].append({
                "plugin": plugin,
                "protocol": protocol,
                "uid": uid,
                "line": line,
                "target_ip": target_ip,
                "params": params
            })

            if plugin.lower() in ("artnet", "dmx", "sacn"):
                udata["universe_type"] = "DMX"
            elif plugin.lower() == "osc":
                udata["universe_type"] = "OSC"

        universes.append(udata)

    # ─── Summary ───────────────────────────────
    summary = {
        "fixtures": len(fixtures),
        "functions": len(functions),
        "universes": len(universes),
        "osc_plugins": len(osc_plugins)
    }

    return {
        "fixtures": fixtures,
        "functions": functions,
        "universes": universes,
        "osc": {"plugins": osc_plugins},
        "summary": summary
    }

if __name__ == "__main__":
    data = parse_qlc_workspace()
    print(json.dumps(data, indent=2))
