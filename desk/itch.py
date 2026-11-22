"""itch.io: listing and art checks, Windows and Android build uploads with butler (itch.io's official upload tool).

One itch.io page carries both downloads: the Windows build goes to the windows channel, the Android APK (signed with
the Google Play upload key, so players can update it) to the android channel. The desk shows the Android part as its
own store under Android; text, art and the page itself are shared with itch.io.

No review or fee; the page is edited on itch.io. butler keeps its own login after `butler login` (a browser sign-in
in its console); the desk never reads it. Pushes only send what changed since the previous build."""
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from . import art, builds, jobs, release, storekit
from .project import CONFIG_DIR

RULES = art.rules("itch")
TOOL_DIR = CONFIG_DIR / "butler"
IGNORE = ["*.pdb", "*_BurstDebugInformation_DoNotShip*", "*_BackUpThisFolder_ButDontShipItWithYourGame*"]
# itch.io's own download service for butler builds (the source is on GitHub, itchio/butler; releases come from here).
BROTH = "https://broth.itch.zone/butler/windows-amd64"
ANDROID = "itch-android-apk"
CREDS = Path(os.environ.get("USERPROFILE", Path.home())) / ".config" / "itch" / "butler_creds"


def settings(project):
    data = (project.read("store.json", {}) or {}).get("itch", {}) or {}
    return {"project": data.get("project", ""), "channel": data.get("channel", "windows"), "androidChannel": data.get("androidChannel", "android")}


def butler():
    local = sorted(TOOL_DIR.glob("**/butler.exe"))
    return str(local[0]) if local else shutil.which("butler")


def version(exe):
    try:
        out = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=30)
        return (out.stdout + out.stderr).strip().splitlines()[0] if (out.stdout + out.stderr).strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def install(project=None):
    """Downloads the latest Windows butler from itch.io's broth service into the desk's tool folder and checks that it
    runs. A previous copy there is replaced only once the new one works. No login happens here."""
    with urllib.request.urlopen(f"{BROTH}/LATEST", timeout=30) as r:
        latest = r.read().decode("utf-8").strip()
    if not latest or len(latest) > 40 or not all(c.isalnum() or c in ".-" for c in latest):
        return False, "itch.io's download service did not name a butler version."
    jobs.say(f"Downloading butler {latest}")
    TOOL_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive = TOOL_DIR.parent / "butler-download.zip"
    fresh = TOOL_DIR.parent / "butler-new"
    shutil.rmtree(fresh, ignore_errors=True)
    try:
        with urllib.request.urlopen(f"{BROTH}/{latest}/archive/default", timeout=120) as r, open(archive, "wb") as f:
            while chunk := r.read(1 << 20):
                jobs.check()
                f.write(chunk)
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if "butler.exe" not in names or any(n.startswith(("/", "\\")) or ".." in Path(n).parts for n in names):
                return False, "The download is not a butler archive; nothing was installed."
            z.extractall(fresh)
        got = version(str(fresh / "butler.exe"))
        if not got:
            return False, "The downloaded butler does not start; nothing was installed."
        shutil.rmtree(TOOL_DIR, ignore_errors=True)
        fresh.rename(TOOL_DIR)
        return True, f"butler {latest} installed in {TOOL_DIR} ({got})."
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(fresh, ignore_errors=True)


def key_state(project):
    exe, s = butler(), settings(project)
    logged = CREDS.is_file() or bool(os.environ.get("BUTLER_API_KEY"))
    return {"butler": exe or "", "toolFolder": str(TOOL_DIR), "installed": bool(exe), "loggedIn": logged, "project": s["project"],
            "channel": s["channel"], "androidChannel": s["androidChannel"], "ready": bool(exe) and logged and "/" in s["project"]}


def _build(project, kind="itch-windows"):
    info = builds.latest(project, kind)
    info["folder"] = info["path"] if kind == "itch-windows" else str(Path(info["path"]).parent)
    info["history"] = builds.history(project, kind)
    return info


def status(project):
    fields = storekit.fields(project, "itch", RULES, name_label="Title")
    art_items, shots, build, key = art.check(project, "itch"), storekit.screenshots(project, RULES), _build(project), key_state(project)
    page = f"https://itch.io/game/edit/{key['project']}" if key["project"] else "https://itch.io/game/new"
    steps = [
        {"title": "itch.io account and project page", "state": "ok" if "/" in key["project"] else "todo", "kind": "hand",
         "link": "https://itch.io/game/new", "go": "itch/keys/ids-itch-project",
         "detail": "Create the project page on itch.io (free, no review), then put user/game (the page address, lower case) in Keys & accounts."},
        {"title": "butler installed and logged in", "state": "ok" if key["installed"] and key["loggedIn"] else "todo", "kind": "desk",
         "link": "https://itchio.itch.io/butler", "go": "itch/keys/itch-butler",
         "detail": "Install butler (Keys & accounts downloads itch.io's latest build), then Log in to itch.io."},
        {"title": "AI disclosure", "state": "todo", "kind": "hand", "link": "https://itch.io/docs/creators/quality-guidelines#ai-disclosure",
         "detail": "On the Edit game page, disclose generative AI use: Code (shipped code includes generated contributions), and describe optional live generation and manual creation in the description."},
        {"title": "Page text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy", "go": "itch/listing/itch-text",
         "detail": "Paste the tagline and description into Edit game."},
        {"title": "Cover image", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy", "go": "itch/listing/itch-art",
         "detail": "630×500 cover (Make capsules) on Edit game."},
        {"title": "Screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy", "go": "itch/listing/itch-shots",
         "detail": f"{shots['good']} usable in Store/{shots['folder']}; add 3 to 5 on Edit game."},
        {"title": "Windows build", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "itch/builds/itch-builds",
         "detail": "Built by Unity into Build/Itch/Windows."},
        {"title": "Push with butler", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "itch/builds/itch-upload", "detail": f"Pushes to the {key['channel']} channel with the release version; only changes are sent."},
        {"title": "Publish the page", "state": "todo", "kind": "hand", "link": page,
         "detail": "Set visibility to Public (or Restricted for testers) and pricing on Edit game."},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "build": build, "key": key, "steps": steps,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def android_status(project):
    """itch.io Android: the same page, an APK on the android channel."""
    from . import play  # play imports builds
    key, build, sign = key_state(project), _build(project, ANDROID), play.key_state(project)
    page = f"https://itch.io/game/edit/{key['project']}" if key["project"] else "https://itch.io/game/new"
    steps = [
        {"title": "itch.io page and butler", "state": "ok" if key["ready"] else "todo", "kind": "hand", "go": "itch-android/keys/ids-itch-project",
         "detail": "The same itch.io page as the Windows download: project, butler and its login."},
        {"title": "Android package and upload key", "state": "ok" if sign["ready"] else "todo", "kind": "desk", "go": "itch-android/keys/play-key",
         "detail": "The APK is signed with the Google Play upload key, so an update installs over the previous one and the same key serves Play later."},
        {"title": "Android APK", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "itch-android/builds/itch-android-builds",
         "detail": "Built by Unity into Build/Itch/Android."},
        {"title": "Push with butler", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "itch-android/builds/itch-android-upload", "detail": f"Pushes the APK to the {key['androidChannel']} channel; itch.io marks it as the Android download."},
        {"title": "Android on the page", "state": "todo", "kind": "hand", "link": page,
         "detail": "On Edit game, check the APK upload is tagged Android and say in the description that it installs outside Google Play (players allow it once)."},
    ]
    return {"build": build, "key": key, "sign": {"ready": sign["ready"], "package": sign.get("package", "")}, "steps": steps,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project, android=False):
    s = android_status(project) if android else status(project)
    return [f"itch.io{' Android' if android else ''}: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open"]


def login(project):
    exe = butler()
    if not exe:
        return False, "Install butler first."
    subprocess.Popen(["cmd", "/c", f'title itch.io login & "{exe}" login & echo. & pause'], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return True, "Opened a console window; butler opens the itch.io sign-in in your browser."


def _push(project, preview, kind="itch-windows"):
    key, info = key_state(project), _build(project, kind)
    if not key["ready"]:
        return False, "Finish the itch.io setup first (Keys & accounts)."
    if not info["exists"]:
        return False, f"Build {builds.KINDS[kind]['label']} first."
    source = info["path"]
    if kind == ANDROID:
        # butler pushes a folder; stage only the newest APK so older ones next to it are not sent.
        stage = Path(info["path"]).parent / "push"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        shutil.copy2(info["path"], stage / Path(info["path"]).name)
        source = str(stage)
    channel = key["androidChannel"] if kind == ANDROID else key["channel"]
    target = f"{key['project'].lower()}:{channel}"
    rel = release.effective(project, "itch")
    ignores = [arg for pattern in IGNORE for arg in ("--ignore", pattern)]
    if preview:
        args = [key["butler"], "push-preview", "--changes-only", source, target] + ignores
    else:
        args = [key["butler"], "push", source, target, "--userversion", f"{rel['version']}+{rel['build']}", "--if-changed"] + ignores
    run = jobs.run(args, timeout=6 * 3600, encoding="utf-8", errors="replace")
    output = (run.stdout or "") + (run.stderr or "")
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "butler.txt").write_text(output, encoding="utf-8")
    tail = "\n".join([l for l in output.splitlines() if l.strip()][-8:])
    if run.returncode != 0:
        return False, f"butler exit code {run.returncode}\n{tail}"
    if not preview:
        builds.mark_uploaded(project, kind, f"{channel} {rel['version']}+{rel['build']}")
    return True, tail or ("Nothing would change." if preview else "Pushed.")


def preview(project, android=False):
    return _push(project, True, ANDROID if android else "itch-windows")


def push(project, android=False):
    return _push(project, False, ANDROID if android else "itch-windows")
