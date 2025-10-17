const socket = io();
socket.on("state:update", (st) => {
  // Set switches
  const a = document.getElementById("toggleAutovol");
  const b = document.getElementById("toggleBeat");
  const l = document.getElementById("toggleLighting");
  if (a) a.checked = !!st.features.autovolume_enabled;
  if (b) b.checked = !!st.features.beat_enabled;
  if (l) l.checked = !!st.features.lighting_enabled;
});

socket.on("meters:update", (m) => {
  for (const k of ["main_l","main_r","aux1","aux2","aux3","aux4"]) {
    const el = document.getElementById("m-"+k);
    if (!el) continue;
    const pct = Math.max(0, Math.min(100, Math.round((m[k]||0)*100)));
    el.style.setProperty("--w", pct+"%");
    el.style.setProperty("width", pct+"%");
    el.style.width = pct + "%";
    el.style.setProperty("--bar-width", pct + "%");
    el.style.setProperty("background", "transparent");
    el.style.setProperty("position", "relative");
    el.style.setProperty("overflow", "hidden");
    el.style.setProperty("borderRadius", "8px");
    el.style.setProperty("boxShadow", "inset 0 0 6px rgba(255,193,7,.25)");
    el.style.setProperty("--after-width", pct + "%");
    el.style.setProperty("transition", "width .12s linear");
    // use ::after width via style hack
    el.style.setProperty("--w", pct+"%");
    el.style.setProperty("width", pct+"%");
    el.style.setProperty("contain", "paint");
  }
});

window.addEventListener("DOMContentLoaded", () => {
  // Feature toggles
  const bind = (id, key) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", async () => {
      try {
        await fetch("/api/feature", {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ key, value: el.checked })
        });
      } catch (_) {}
    });
  };
  bind("toggleAutovol", "autovolume_enabled");
  bind("toggleBeat", "beat_enabled");
  bind("toggleLighting", "lighting_enabled");

  // Config save
  const frm = document.getElementById("cfgForm");
  if (frm) {
    frm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(frm);
      const res = await fetch("/api/config/save", { method:"POST", body: fd });
      const js = await res.json().catch(()=>({ok:false, err:"parse"}));
      const out = document.getElementById("cfgResult");
      if (js.ok) { out.textContent = "Saved."; out.className="small text-success"; }
      else { out.textContent = "Error: " + (js.err||"unknown"); out.className="small text-danger"; }
    });
  }
});
// Scene upload
const sf = document.getElementById("sceneForm");
if (sf) {
  sf.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(sf);
    const res = await fetch("/api/scene/upload", {method:"POST", body:fd});
    const js = await res.json().catch(()=>({ok:false,err:"parse"}));
    const out = document.getElementById("sceneResult");
    if (js.ok) out.textContent = `Loaded ${Object.keys(js.scene.channels).length} channels`;
    else out.textContent = "Error: "+(js.err||"unknown");
  });
}
