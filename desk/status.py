"""Read-only status page for the work board: what the desk shows, with no buttons and no secrets.

Written to Store/Logs/board-status.html (git-ignored) after every refresh and every finished job. The page is
self-contained (inline CSS, JS and data) so the board session can publish it as is. It holds only what is safe
to show anywhere: setup progress, the release text, build and upload history, release-check results and the
stores table. No IDs, keys, paths, logins or account details go into it."""
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from . import builds, evaluate, laptop, release, stores

OUT = "Logs/board-status.html"
ROOT = Path(__file__).resolve().parent.parent
BUILD_STORE = stores.KIND_STORE


def _build(h):
    return {"kind": builds.KINDS.get(h.get("kind"), {}).get("label", h.get("kind", "")), "version": h.get("version", ""),
            "build": h.get("build", ""), "finished": h.get("finished", ""), "minutes": h.get("minutes"),
            "sizeMB": h.get("sizeMB"), "uploaded": h.get("uploaded", "") or h.get("galaxy", ""),
            "changes": (h.get("changes") or [])[:8], "result": h.get("result", "")}


def collect(project, progress):
    r = release.status(project)
    # Per kind, so a build made before the desk kept a history still shows (history() falls back per kind).
    history = sorted((h for kind in builds.KINDS for h in builds.history(project, kind)), key=lambda h: h.get("finished", ""), reverse=True)
    rows = []
    for s in progress:
        mine = [h for h in history if BUILD_STORE.get(h.get("kind")) == s["id"]]
        if s["id"] == "samsung":
            mine = [dict(h, uploaded=h.get("galaxy", "")) for h in history if h.get("kind") == "play-aab"]
        st = r["stores"].get(s["id"], {})
        rows.append({"id": s["id"], "name": s["name"], "done": s["done"], "total": s["total"], "next": s["next"],
                       "overrides": st.get("overrides", []), "tooLong": st.get("tooLong", {}),
                       "builds": [_build(h) for h in mine[:5]]})
    checks = [{k: c.get(k) for k in ("request", "commit", "state", "started", "finished", "summary")}
              | {"steps": [{k: x.get(k) for k in ("name", "state", "minutes", "summary")} for x in c.get("steps", [])]}
              for c in laptop.results(project, 5)]
    for c in checks:
        c["commit"] = str(c.get("commit") or "")[:9]
    fields = {k: v["label"] for k, v in r["fields"].items()}
    return {"title": project.unity_settings().get("productName") or project.root.name,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "release": {"fields": fields, "values": r["shared"]}, "stores": rows, "checks": checks,
            "compare": compare(project), "evaluate": [s for s in evaluate.stores() if stores.is_on(project, s["id"])]}


def compare(project):
    """The stores table with only the stores turned on for this project."""
    c = json.loads((ROOT / "rules" / "compare.json").read_text(encoding="utf-8"))
    c["stores"] = [s for s in c["stores"] if stores.is_on(project, s["id"])]
    c["groups"] = stores.groups(project)
    return c


def write(project, progress):
    data = collect(project, progress)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.replace("__TITLE__", html.escape(data["title"])).replace("__DATA__", payload)
    path = project.store / OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Release Desk</title>
<style>
:root{--bg:#f6f6f3;--panel:#fff;--ink:#1d2420;--muted:#66706a;--line:#dde1dc;--accent:#2f6f5a;--ok:#2f7a4f;--ok-bg:#e3f2e8;--warn:#9a6a0c;--warn-bg:#f8eed6;--bad:#b5452f;--bad-bg:#f7e2dc;--soft:#eef0ec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141816;--panel:#1f2522;--ink:#e7ebe8;--muted:#9aa49e;--line:#2e3632;--accent:#6cc2a2;--ok:#7fd3a0;--ok-bg:#1f3a2a;--warn:#f0c46a;--warn-bg:#3a3020;--bad:#f09a85;--bad-bg:#3c2420;--soft:#262d29}}
:root[data-theme="dark"]{--bg:#141816;--panel:#1f2522;--ink:#e7ebe8;--muted:#9aa49e;--line:#2e3632;--accent:#6cc2a2;--ok:#7fd3a0;--ok-bg:#1f3a2a;--warn:#f0c46a;--warn-bg:#3a3020;--bad:#f09a85;--bad-bg:#3c2420;--soft:#262d29}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{padding:16px}
h1{font-size:20px;margin:0}h2{font-size:15px;margin:0 0 8px}.note{color:var(--muted);font-size:12px}
.box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:12px 0}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.tabs button{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit}
.tabs button[aria-selected=true]{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,var(--panel))}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.meter{height:6px;background:var(--soft);border-radius:99px;overflow:hidden;margin:6px 0}.meter i{display:block;height:100%;background:var(--accent)}
.chip{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:var(--soft);color:var(--muted);white-space:nowrap}
.chip.ok{background:var(--ok-bg);color:var(--ok)}.chip.warn{background:var(--warn-bg);color:var(--warn)}.chip.bad{background:var(--bad-bg);color:var(--bad)}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--muted);font-weight:600}
.scroll{overflow-x:auto}.cell{border:0;background:none;padding:0;cursor:pointer;font:inherit}.cell[aria-expanded=true] .chip{outline:2px solid var(--accent)}
.detail td{background:var(--soft)}pre{white-space:pre-wrap;margin:0;font:inherit}ul{margin:4px 0;padding-left:18px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.unknown{background:var(--muted)}
a{color:var(--accent)}
</style></head><body><div class="wrap" id="app"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const chip = (lvl, t) => `<span class="chip ${lvl}">${esc(t)}</span>`;
const LV = {ok: "ok", warn: "warn", bad: "bad", unknown: ""};
let tab = "stores";
try { tab = localStorage.getItem("desk.tab") || tab; } catch (_) {}
function card(s) {
    const b = s.builds[0];
    return `<div class="card"><b>${esc(s.name)}</b><div class="meter"><i style="width:${Math.round(100 * s.done / Math.max(1, s.total))}%"></i></div>
      <div class="note">${s.done} of ${s.total} setup steps · next: ${esc(s.next)}</div>
      ${b ? `<div style="margin-top:6px">${esc(b.kind)} ${esc(b.version)} (${esc(b.build)}) · ${esc(b.finished)} ${b.uploaded ? chip("ok", "uploaded " + b.uploaded) : chip("", "not uploaded")}</div>` : `<div class="note" style="margin-top:6px">No builds yet</div>`}
      ${s.overrides.length ? `<div class="note">Own: ${esc(s.overrides.join(", "))}</div>` : ""}
      ${Object.keys(s.tooLong).length ? `<div>${Object.entries(s.tooLong).map(([k, v]) => chip("bad", (D.release.fields[k] || k) + " " + v)).join(" ")}</div>` : ""}</div>`;
}
const evalCard = e => `<div class="card"><b><span class="dot ${esc(e.fit)}"></span>${esc(e.name)}</b><div class="note">To evaluate · ${esc({ok: "fits the AI and runtime scripts", warn: "fits with conditions", bad: "AI or runtime scripts likely not allowed", unknown: "rules unknown or under NDA"}[e.fit] || "")}</div></div>`;
function stores() {
  const group = id => (D.compare.stores.find(x => x.id === id) || {}).group;
  return D.compare.groups.map(([g, label]) => {
    const planned = D.stores.filter(s => group(s.id) === g), later = D.evaluate.filter(e => e.group === g);
    if (!planned.length && !later.length) return "";
    return `<h2 style="margin-top:16px">${esc(label)}</h2><div class="grid">${planned.map(card).join("")}${later.map(evalCard).join("")}</div>`;
  }).join("");
}
function rel() {
  return `<div class="box"><table>${Object.entries(D.release.fields).map(([k, l]) => `<tr><th style="width:160px">${esc(l)}</th><td><pre>${esc(D.release.values[k])}</pre></td></tr>`).join("")}</table></div>`;
}
function blds() {
  const rows = D.stores.flatMap(s => s.builds.map(b => [s.name, b])).sort((a, b) => String(b[1].finished).localeCompare(String(a[1].finished)));
  return `<div class="box scroll"><table><tr><th>Store</th><th>Build</th><th>Version</th><th>Made</th><th>Size</th><th>Uploaded</th><th>Changes</th></tr>${rows.map(([n, b]) => `<tr><td>${esc(n)}</td><td>${esc(b.kind)}</td><td>${esc(b.version)} (${esc(b.build)})</td><td>${esc(b.finished)}</td><td>${b.sizeMB != null ? esc(b.sizeMB) + " MB" : ""}</td><td>${b.uploaded ? chip("ok", b.uploaded) : chip("", "no")}</td><td>${b.changes.length ? `<ul>${b.changes.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}</td></tr>`).join("") || `<tr><td colspan="7" class="note">No builds yet.</td></tr>`}</table></div>`;
}
function checks() {
  if (!D.checks.length) return `<div class="box note">No release checks yet.</div>`;
  return D.checks.map(c => `<div class="box"><h2>${chip(c.state === "passed" ? "ok" : c.state === "failed" ? "bad" : "", c.state)} ${esc(c.request)} <span class="note">${esc(c.commit)} · ${esc(c.finished || c.started)}</span></h2><p>${esc(c.summary)}</p>
    <table>${c.steps.map(s => `<tr><td>${esc(s.name)}</td><td>${chip(s.state === "passed" ? "ok" : s.state === "failed" ? "bad" : "", s.state)}</td><td>${s.minutes != null ? esc(s.minutes) + " min" : ""}</td><td>${esc(s.summary)}</td></tr>`).join("")}</table></div>`).join("");
}
function compare() {
  const c = D.compare;
  return `<div class="box scroll"><p class="note">Click a cell for details. Checked ${esc(c.checked)}.</p><table><tr><th>Store</th>${c.columns.map(x => `<th>${esc(x.label)}</th>`).join("")}</tr>
    ${c.groups.map(([g, label]) => `<tr><th colspan="${c.columns.length + 1}" style="padding-top:14px;color:var(--ink)">${esc(label)}</th></tr>` + c.stores.filter(s => s.group === g).map(s => `<tr><td style="white-space:nowrap">${esc(s.name)}</td>${c.columns.map(x => { const v = s.cells[x.key] || {short: "?", level: "unknown"}; return `<td><button class="cell" data-cell="${esc(s.id)}:${esc(x.key)}" aria-expanded="false">${chip(LV[v.level] ?? "", v.short)}</button></td>`; }).join("")}</tr><tr class="detail" data-for="${esc(s.id)}" hidden><td colspan="${c.columns.length + 1}"></td></tr>`).join("")).join("")}</table></div>
    <div class="box"><h2>For players from 8, through a parent's account</h2><ul>${c.product.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
}
const TABS = {stores: ["Stores", stores], release: ["Release", rel], builds: ["Builds", blds], checks: ["Release checks", checks], compare: ["Store rules", compare]};
function draw() {
  if (!TABS[tab]) tab = "stores";
  document.getElementById("app").innerHTML = `<h1>${esc(D.title)} · Release Desk</h1><div class="note">Read-only status, written by the desk at ${esc(D.generated)}. Builds and uploads run in the desk on the PC.</div>
    <div class="tabs" role="tablist">${Object.entries(TABS).map(([k, [l]]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("")}</div>${TABS[tab][1]()}`;
}
document.addEventListener("click", e => {
  const t = e.target.closest("[data-tab]");
  if (t) { tab = t.dataset.tab; try { localStorage.setItem("desk.tab", tab); } catch (_) {} return draw(); }
  const b = e.target.closest("[data-cell]");
  if (!b) return;
  const [sid, key] = b.dataset.cell.split(":"), s = D.compare.stores.find(x => x.id === sid), v = s.cells[key] || {}, col = D.compare.columns.find(x => x.key === key);
  const row = document.querySelector(`[data-for="${sid}"]`), open = b.getAttribute("aria-expanded") === "true";
  document.querySelectorAll(`[data-cell^="${sid}:"]`).forEach(x => x.setAttribute("aria-expanded", "false"));
  if (open) { row.hidden = true; return; }
  b.setAttribute("aria-expanded", "true");
  row.firstElementChild.innerHTML = `<b>${esc(s.name)} · ${esc(col.label)}</b><p>${esc(v.detail || "")}</p>${/^https:\/\//.test(v.source || "") ? `<a href="${esc(v.source)}" target="_blank" rel="noopener">${esc(v.source)}</a>` : ""}`;
  row.hidden = false;
});
draw();
</script></body></html>
"""
