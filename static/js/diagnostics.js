// diagnostics.js — Polebarn Web Diagnostics Dashboard

async function loadStatus() {
  try {
    const res = await fetch("/api/system/status");
    const d = await res.json();

    // CPU / Memory / Temp / Uptime
    document.getElementById("cpu").innerText = (d.cpu ?? 0).toFixed(1) + " %";
    document.getElementById("mem").innerText = (d.mem ?? 0).toFixed(1) + " %";
    document.getElementById("temp").innerText = (d.temp ?? 0).toFixed(1);
    document.getElementById("uptime").innerText = d.uptime ?? "--";

    // Service statuses
    ["polebarn", "qlcplus", "auto_volume", "beat_detect", "lighting_auto"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.className = "status-dot " + (d[id] || "inactive");
    });

    // Beat telemetry
    if (d.beat_info) {
      const bpm = d.beat_info.bpm ?? 0;
      const intensity = d.beat_info.intensity ?? 0; // already 0–100 scale
      document.getElementById("bpm").innerText = Math.round(bpm);
      document.getElementById("intensity").innerText = Math.round(intensity) + " %";
      const bar = document.getElementById("beat-bar");
      if (bar) {
        bar.style.width = Math.min(intensity, 100) + "%";
        bar.classList.add("flash");
        setTimeout(() => bar.classList.remove("flash"), 120);
      }
    }
  } catch (err) {
    console.error("Status update failed:", err);
  }
}

// Perform backend actions
async function doAction(action) {
  try {
    await fetch("/api/system/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action })
    });
    console.log("Action triggered:", action);
  } catch (err) {
    console.error("Action failed:", err);
  }
  setTimeout(loadStatus, 2000);
}

// Loop every second
setInterval(loadStatus, 1000);
loadStatus();
