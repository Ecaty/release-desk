"""GOG: listing and art checks, Windows build upload through GOG's Pipeline Builder.

GOG is curated: the game is submitted for consideration first, and the store page assets go to GOG through their
Assets Manager. Uploads use GOGGalaxyPipelineBuilder with the project.json made once in GOG's Build Creator.
The upload runs in a visible console so the Pipeline Builder can ask for the GOG login itself the first time
(it caches it); the desk never sees the password."""
import json
import subprocess
import time

from . import art, builds, jobs, release, storekit
from .project import CONFIG_DIR

RULES = art.rules("gog")
TOOL_DIR = CONFIG_DIR / "GOGGalaxyPipelineBuilder"
IGNORE = ["*.pdb", "*_BurstDebugInformation_DoNotShip*", "*_BackUpThisFolder_ButDontShipItWithYourGame*", "*DoNotShip*"]
BUILD_FOLDER = "Build/GOG/Windows"


def settings(project):
    data = (project.read("store.json", {}) or {}).get("gog", {}) or {}
    return {"productId": data.get("productId", ""), "branch": data.get("branch", ""), "project": data.get("project", "gog/project.json")}


def tool():
    found = sorted(TOOL_DIR.glob("**/GOGGalaxyPipelineBuilder.exe"))
    return found[0] if found else None


def project_json(project):
    """The Build Creator project file in Store/; checks that it points at the desk's GOG build folder."""
    rel = settings(project)["project"]
    path = project.store / rel
    state = {"path": f"Store/{rel}", "exists": path.is_file(), "points": False, "problem": ""}
    if not state["exists"]:
        state["problem"] = "missing"
        return state
    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
    except (OSError, ValueError):
        state["problem"] = "not valid JSON"
        return state
    state["points"] = BUILD_FOLDER.replace("/", "") in text.replace("\\\\", "").replace("\\", "").replace("/", "")
    if not state["points"]:
        state["problem"] = f"its depot folder should be the desk's {BUILD_FOLDER} folder"
    return state


def key_state(project):
    exe, pj = tool(), project_json(project)
    return {"tool": str(exe or ""), "toolFolder": str(TOOL_DIR), "installed": bool(exe), "project": pj,
            "ready": bool(exe) and pj["exists"] and not pj["problem"]}


def _build(project):
    info = builds.latest(project, "gog-windows")
    info["folder"] = info["path"]
    info["history"] = builds.history(project, "gog-windows")
    return info


def status(project):
    fields = storekit.fields(project, "gog", RULES)
    art_items, shots, build, key = art.check(project, "gog"), storekit.screenshots(project, RULES), _build(project), key_state(project)
    portal = "https://devportal.gog.com/"
    steps = [
        {"title": "Submit the game to GOG", "state": "ok" if settings(project)["productId"] else "todo", "kind": "hand",
         "link": "https://partners.gog.com/", "go": "keys//ids-gog-productId",
         "detail": "GOG curates its catalogue: submit the game for consideration. After signing, put the product ID in Keys & accounts."},
        {"title": "Pipeline Builder", "state": "ok" if key["installed"] else "todo", "kind": "hand", "link": portal, "go": "keys//gog-tool",
         "detail": f"Download GOG's Pipeline Builder from the Developer Portal and unzip it into {key['toolFolder']}."},
        {"title": "Build Creator project", "state": "ok" if not key["project"]["problem"] else "todo", "kind": "hand", "go": "keys//gog-project",
         "detail": f"Create the project once in GOG's Build Creator with the depot folder {BUILD_FOLDER} (inside the Unity project) and save it as {key['project']['path']}."},
        {"title": "Store page text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy", "go": "gog/listing/gog-text",
         "detail": "Description, system requirements and legal lines go to GOG with the assets."},
        {"title": "Key art and logo", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy", "go": "gog/listing/gog-art",
         "detail": "Send key art and logo (Store/gog/art) through GOG's Assets Manager; GOG renders the store images from its templates."},
        {"title": "Screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy", "go": "gog/listing/gog-shots",
         "detail": f"{shots['good']} usable (1920×1080 or larger) in Store/{shots['folder']}."},
        {"title": "Windows build (DRM-free)", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "gog/builds/gog-builds",
         "detail": "Built by Unity into Build/GOG/Windows. GOG builds must run without any other store's client or DRM."},
        {"title": "Upload with Pipeline Builder", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "gog/builds/gog-upload", "detail": "Uploads the build; publish it to a branch in the Developer Portal (Pipeline Builder cannot publish to master)."},
        {"title": "Ratings, prices and release", "state": "todo", "kind": "hand", "link": portal,
         "detail": "Age ratings, price list, release date and launch discount are agreed with GOG."},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "build": build, "key": key, "steps": steps,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project):
    s = status(project)
    return [f"GOG: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open"]


def upload(project):
    key, info = key_state(project), _build(project)
    if not key["ready"]:
        return False, "Finish the Pipeline Builder setup first (Keys & accounts)."
    if not info["exists"]:
        return False, "Build Windows (GOG) first."
    rel, gog = release.effective(project, "gog"), settings(project)
    scripts = project.root / "Build" / "GOG" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    ignore = scripts / "ignore.txt"
    ignore.write_text("\n".join(IGNORE) + "\n", encoding="utf-8")
    result = scripts / "result.txt"
    if result.exists():
        result.unlink()
    version = f"{rel['version']} ({rel['build']})"
    args = f'call "{key["tool"]}" build-game "{project.store / gog["project"]}" --version "{version}" --ignore_list "{ignore}"'
    if gog["branch"]:
        args += f' --branch "{gog["branch"]}"'
    script = scripts / "upload.cmd"
    script.write_text("\r\n".join(["@echo off", "title GOG upload", "echo Uploading to GOG. Enter the GOG login here if asked; Release Desk never sees it.",
                                   args, f'>"{result}" echo %ERRORLEVEL%', "echo.", "echo Done. This window closes in 10 seconds.",
                                   "timeout /t 10 >nul"]) + "\r\n", encoding="utf-8")
    proc = subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    job = jobs.current()
    if job:  # Cancel closes the upload window too
        with job.lock:
            job.procs.append(proc)
    deadline = time.time() + 6 * 3600
    while not result.exists() and time.time() < deadline:
        jobs.sleep(5)
    try:
        code = int(result.read_text(encoding="utf-8").strip() or "1")
    except (OSError, ValueError):
        return False, "The GOG upload window closed without a result."
    if code != 0:
        return False, f"Pipeline Builder exit code {code}; see the GOG upload window or its logs in %TEMP%\\__gog\\logs."
    builds.mark_uploaded(project, "gog-windows", f"GOG {version}" + (f" ({gog['branch']})" if gog["branch"] else ""))
    return True, f"Uploaded {version}. Publish it to a branch in the GOG Developer Portal."
