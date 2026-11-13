"""Steam: listing checks, art checks, Windows build and SteamPipe upload."""
import json
import os
import re
import subprocess
from pathlib import Path

from . import art, builds, images, jobs, release, unity
from .project import CONFIG_DIR

RULES = json.loads((Path(__file__).resolve().parent.parent / "rules" / "steam.json").read_text(encoding="utf-8"))
STEAMCMD = CONFIG_DIR / "steamcmd" / "steamcmd.exe"


def build_dir(project):
    return builds.output(project, "steam-windows")


def listing(project):
    return project.read("steam/listing.json", {}) or {}


def save_listing(project, fields):
    data = listing(project)
    for key, rule in RULES["text"].items():
        if key in fields and not rule.get("from"):
            data[key] = str(fields[key]).strip()
    project.write("steam/listing.json", data)
    return data


def _art(project):
    return art.check(project, "steam")


def _screenshots(project):
    rule = RULES["screenshots"]
    folder = project.store / rule["folder"]
    shots = []
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        dims = images.size(path)
        if not dims:
            continue
        w, h, _ = dims
        ok = w >= rule["minWidth"] and h >= rule["minHeight"] and abs(w / h - rule["aspect"]) < 0.01
        shots.append({"file": path.name, "size": f"{w}×{h}", "ok": ok})
    good = sum(s["ok"] for s in shots)
    return {"items": shots, "good": good, "min": rule["min"], "folder": rule["folder"], "note": rule["note"]}


def _build(project):
    info = builds.latest(project, "steam-windows")
    info["folder"] = info["path"]
    info["history"] = builds.history(project, "steam-windows")
    info["uploaded"] = any(h.get("uploaded") for h in info["history"][:1])
    return info


def steamcmd_state(config):
    user = config.get("steamUser", "")
    state = {"path": str(STEAMCMD), "installed": STEAMCMD.is_file(), "user": user, "loggedIn": False}
    vdf = STEAMCMD.parent / "config" / "config.vdf"
    if user and vdf.is_file():
        state["loggedIn"] = f'"{user.lower()}"' in vdf.read_text(encoding="utf-8", errors="replace").lower()
    return state


def status(project, config):
    shared = project.read("store.json", {}) or {}
    steam = shared.get("steam", {})
    text = listing(project)
    fields = []
    fields.extend(release.text_fields(project, "steam", RULES, text))
    art = _art(project)
    shots = _screenshots(project)
    build = _build(project)
    cmd = steamcmd_state(config)
    app_id, depot = str(steam.get("appId", "")), str(steam.get("depots", {}).get("windows", ""))
    steps = [
        {"title": "Steamworks account and app", "go": "keys//ids-steam-appId", "state": "ok" if app_id else "todo", "kind": "hand",
         "detail": "Pay the app fee in Steamworks, then put the App ID and Windows depot ID in Store/store.json.",
         "link": "https://partner.steamgames.com/"},
        {"title": "Build account", "go": "keys//steam-user", "state": "ok" if cmd["user"] else "todo", "kind": "hand",
         "detail": "Create a separate Steam account with only 'Edit App Metadata' and 'Publish App Changes To Steam', and enter its name in Keys & accounts."},
        {"title": "SteamCMD installed and logged in once", "go": "keys//steamcmd", "state": "ok" if cmd["installed"] and cmd["loggedIn"] else "todo", "kind": "hand",
         "detail": f"Install SteamCMD, then log in once in a terminal so Steam Guard is remembered: \"{cmd['path']}\" +login {cmd['user'] or '<build account>'}"},
        {"title": "Store page text", "go": "steam/listing/steam-text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy",
         "detail": "Paste the Listing fields into the Steamworks store page editor."},
        {"title": "Store art", "go": "steam/listing/steam-art", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art) else "todo", "kind": "copy",
         "detail": "Upload each image from Store/steam/art in Steamworks."},
        {"title": "Screenshots", "go": "steam/listing/steam-shots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy",
         "detail": f"{shots['good']} of {shots['min']} usable (1920×1080 or larger, 16:9) in Store/{shots['folder']}."},
        {"title": "Windows build", "go": "steam/builds/steam-builds", "state": "ok" if build["exists"] else "todo", "kind": "desk",
         "detail": "Built by Unity into Build/Steam/Windows (Builds tab)."},
        {"title": "Upload to beta branch", "go": "steam/builds/steam-upload", "state": "ok" if build.get("uploaded") else "todo", "kind": "desk",
         "detail": f"SteamPipe upload, set live on '{steam.get('branch', 'beta')}'. The default branch is always set live by hand in Steamworks."},
        {"title": "Review by Valve", "state": "todo", "kind": "hand", "detail": "Valve reviews the store page and the build before release."},
    ]
    return {"fields": fields, "art": art, "screenshots": shots, "build": build, "steamcmd": cmd, "steps": steps,
            "appId": app_id, "depot": depot, "branch": steam.get("branch", "beta"), "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project, config):
    s = status(project, config)
    lines = []
    blocking = [x for x in s["steps"] if x["state"] != "ok" and x["title"] != "Review by Valve"]
    for f in s["fields"]:
        if f["problem"]:
            lines.append(f"Listing: {f['label']} {f['problem']}")
    missing = [a["label"] for a in s["art"] if a["state"] == "missing"]
    wrong = [f"{a['label']} {a['problem']}" for a in s["art"] if a["state"] == "bad"]
    if missing:
        lines.append("Art missing: " + ", ".join(missing))
    lines.extend("Art wrong size: " + w for w in wrong)
    lines.append(f"Screenshots: {s['screenshots']['good']} of {s['screenshots']['min']} usable")
    lines.append("Build: " + (f"{s['build'].get('sizeMB', '?')} MB in {s['build']['folder']}" if s["build"]["exists"] else "none"))
    lines.append(f"Steam IDs: app {s['appId'] or 'missing'}, depot {s['depot'] or 'missing'}")
    lines.append(f"SteamCMD: {'installed' if s['steamcmd']['installed'] else 'not installed'}, "
                 f"{'logged in' if s['steamcmd']['loggedIn'] else 'not logged in'}")
    lines.append(f"Result: {len(blocking)} steps open")
    return lines


def _vdf(project, preview):
    shared = project.read("store.json", {}) or {}
    steam = shared.get("steam", {})
    app_id, depot = str(steam.get("appId", "")), str(steam.get("depots", {}).get("windows", ""))
    if not app_id or not depot:
        raise ValueError("Set steam.appId and steam.depots.windows in Store/store.json first.")
    scripts = project.root / "Build" / "Steam" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    rel = release.effective(project, "steam")
    desc = f"{rel['version']} ({rel['build']}) game {project.git_commit(project.root)} store {project.git_commit(project.store)}"

    def q(text):
        return '"' + str(text).replace("\\", "\\\\").replace('"', "'") + '"'

    lines = ['"AppBuild"', "{", f'  "AppID" {q(app_id)}', f'  "Desc" {q(desc)}', f'  "Preview" {q("1" if preview else "0")}',
             f'  "SetLive" {q(steam.get("branch", "beta"))}', f'  "ContentRoot" {q(build_dir(project))}',
             f'  "BuildOutput" {q(scripts / "output")}', '  "Depots"', "  {", f"    {q(depot)}", "    {",
             '      "FileMapping"', "      {", '        "LocalPath" "*"', '        "DepotPath" "."', '        "Recursive" "1"', "      }",
             '      "FileExclusion" "*.pdb"', '      "FileExclusion" "*DoNotShip*"', '      "FileExclusion" "*DontShipItWithYourGame*"',
             "    }", "  }", "}"]
    path = scripts / "app_build.vdf"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def upload(project, config, preview=True):
    cmd = steamcmd_state(config)
    if not cmd["installed"]:
        return False, "SteamCMD is not installed."
    if not cmd["user"]:
        return False, "Enter the Steam build account name in Keys & accounts."
    if not _build(project)["exists"]:
        return False, "Build Windows first."
    try:
        script = _vdf(project, preview)
    except ValueError as error:
        return False, str(error)
    # The password is never handled here: SteamCMD reuses the login cached by the one-time terminal login.
    run = jobs.run([str(STEAMCMD), "+login", cmd["user"], "+run_app_build", str(script), "+quit"],
                         timeout=3600)
    output = run.stdout + run.stderr
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "steamcmd.txt").write_text(output, encoding="utf-8")
    ok = "Successfully finished AppID" in output or ("Preview" in output and "ERROR" not in output.upper() and run.returncode == 0)
    if ok and not preview:
        builds.mark_uploaded(project, "steam-windows", project.read("store.json", {}).get("steam", {}).get("branch", "beta"))
        result = builds.record_path(build_dir(project))
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data["uploaded"] = True
        result.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tail = [l for l in output.splitlines() if re.search(r"error|fail|success|login|preview", l, re.I)][-6:]
    return ok, "\n".join(tail) or "See Store/Logs/steamcmd.txt"
