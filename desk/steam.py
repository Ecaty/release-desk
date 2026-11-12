"""Steam: listing checks, art checks, Windows build and SteamPipe upload."""
import json
import os
import re
import subprocess
from pathlib import Path

from . import images, unity
from .project import CONFIG_DIR

RULES = json.loads((Path(__file__).resolve().parent.parent / "rules" / "steam.json").read_text(encoding="utf-8"))
STEAMCMD = CONFIG_DIR / "steamcmd" / "steamcmd.exe"


def build_dir(project):
    return project.root / "Build" / "Steam" / "Windows"


def listing(project):
    shared = project.read("store.json", {}) or {}
    data = project.read("steam/listing.json", {}) or {}
    data.setdefault("name", shared.get("name", ""))
    return data


def save_listing(project, fields):
    data = listing(project)
    for key in RULES["text"]:
        if key in fields:
            data[key] = str(fields[key]).strip()
    project.write("steam/listing.json", data)
    return data


def _art(project):
    folder = project.store / "steam" / "art"
    out = []
    for spec in RULES["art"]:
        found = None
        for ext in spec.get("formats", ["png", "jpg"]):
            candidate = folder / f"{spec['file']}.{ext}"
            if candidate.is_file():
                found = candidate
                break
        item = {"label": spec["label"], "expected": f"{spec['width']}×{spec['height']}", "required": spec["required"],
                "file": f"steam/art/{spec['file']}.{spec.get('formats', ['png'])[0]}", "note": spec.get("note", "")}
        if not found:
            item["state"] = "missing" if spec["required"] else "optional"
        else:
            dims = images.size(found)
            item["file"] = str(found.relative_to(project.store)).replace("\\", "/")
            if not dims:
                item["state"], item["problem"] = "bad", "not a readable image"
            else:
                w, h, fmt = dims
                item["actual"] = f"{w}×{h}"
                if spec.get("fit") == "either":
                    ok = (w == spec["width"] and h <= spec["height"]) or (h == spec["height"] and w <= spec["width"])
                else:
                    ok = (w, h) == (spec["width"], spec["height"])
                item["state"] = "ok" if ok else "bad"
                if not ok:
                    item["problem"] = f"is {w}×{h}, needs {item['expected']}"
        out.append(item)
    return out


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
    folder = build_dir(project)
    result = folder.parent / "build-result.json"
    info = {"folder": str(folder), "exists": folder.is_dir() and any(folder.glob("*.exe"))}
    try:
        info.update(json.loads(result.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if info["exists"]:
        info["sizeMB"] = round(sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1048576)
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
    for key, rule in RULES["text"].items():
        value = text.get(key, "")
        problem = ""
        if rule.get("required") and not value:
            problem = "empty"
        elif rule.get("max") and len(value) > rule["max"]:
            problem = f"{len(value)} / {rule['max']} characters"
        fields.append({"key": key, "label": rule["label"], "value": value, "max": rule.get("max"),
                       "multiline": rule.get("multiline", False), "note": rule.get("note", ""), "problem": problem})
    art = _art(project)
    shots = _screenshots(project)
    build = _build(project)
    cmd = steamcmd_state(config)
    app_id, depot = str(steam.get("appId", "")), str(steam.get("depots", {}).get("windows", ""))
    steps = [
        {"title": "Steamworks account and app", "state": "ok" if app_id else "todo", "kind": "hand",
         "detail": "Pay the app fee in Steamworks, then put the App ID and Windows depot ID in Store/store.json.",
         "link": "https://partner.steamgames.com/"},
        {"title": "Build account", "state": "ok" if cmd["user"] else "todo", "kind": "hand",
         "detail": "Create a separate Steam account with only 'Edit App Metadata' and 'Publish App Changes To Steam', and enter its name in Keys & accounts."},
        {"title": "SteamCMD installed and logged in once", "state": "ok" if cmd["installed"] and cmd["loggedIn"] else "todo", "kind": "hand",
         "detail": f"Install SteamCMD, then log in once in a terminal so Steam Guard is remembered: \"{cmd['path']}\" +login {cmd['user'] or '<build account>'}"},
        {"title": "Store page text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy",
         "detail": "Paste the Listing fields into the Steamworks store page editor."},
        {"title": "Store art", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art) else "todo", "kind": "copy",
         "detail": "Upload each image from Store/steam/art in Steamworks."},
        {"title": "Screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy",
         "detail": f"{shots['good']} of {shots['min']} usable (1920×1080 or larger, 16:9) in Store/{shots['folder']}."},
        {"title": "Windows build", "state": "ok" if build["exists"] else "todo", "kind": "desk",
         "detail": "Built by Unity into Build/Steam/Windows."},
        {"title": "Upload to beta branch", "state": "ok" if build.get("uploaded") else "todo", "kind": "desk",
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


def build_windows(project):
    out = build_dir(project)
    ok, result = unity.call(project.root, f"return ReleaseDesk.Editor.DeskEntry.BuildWindows({unity.literal(out)});", timeout=600)
    return ok, result


def _vdf(project, preview):
    shared = project.read("store.json", {}) or {}
    steam = shared.get("steam", {})
    app_id, depot = str(steam.get("appId", "")), str(steam.get("depots", {}).get("windows", ""))
    if not app_id or not depot:
        raise ValueError("Set steam.appId and steam.depots.windows in Store/store.json first.")
    scripts = project.root / "Build" / "Steam" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    desc = f"{shared.get('version', '')} ({shared.get('build', '')}) game {project.git_commit(project.root)} store {project.git_commit(project.store)}"

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
    run = subprocess.run([str(STEAMCMD), "+login", cmd["user"], "+run_app_build", str(script), "+quit"],
                         capture_output=True, text=True, timeout=3600, stdin=subprocess.DEVNULL)
    output = run.stdout + run.stderr
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "steamcmd.txt").write_text(output, encoding="utf-8")
    ok = "Successfully finished AppID" in output or ("Preview" in output and "ERROR" not in output.upper() and run.returncode == 0)
    if ok and not preview:
        result = build_dir(project).parent / "build-result.json"
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data["uploaded"] = True
        result.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tail = [l for l in output.splitlines() if re.search(r"error|fail|success|login|preview", l, re.I)][-6:]
    return ok, "\n".join(tail) or "See Store/Logs/steamcmd.txt"
