"""Per-store builds: where each build goes, what it is called, and how to run it locally.

Layout (inside the Unity project, which ignores Build/):
  Build/Steam/Windows/<Name>.exe              folder SteamPipe uploads
  Build/GooglePlay/Android/<Name>_<ver>_<n>-dev.apk   phone testing
  Build/GooglePlay/Android/<Name>_<ver>_<n>.aab       release upload
Each build writes <file or folder>.json next to it with version, build number and result.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import jobs, release, unity

KINDS = {
    "steam-windows": {"store": "Steam", "target": "windows", "label": "Windows", "folder": True, "development": False},
    "epic-windows": {"store": "Epic", "target": "windows", "label": "Windows (Epic)", "folder": True, "development": False},
    "gog-windows": {"store": "GOG", "target": "windows", "label": "Windows (GOG)", "folder": True, "development": False},
    "microsoft-windows": {"store": "Microsoft", "target": "windows", "label": "Windows (Microsoft Store)", "folder": True, "development": False},
    "play-dev-apk": {"store": "GooglePlay", "target": "android", "label": "Phone test APK", "ext": "-dev.apk", "development": True},
    "play-aab": {"store": "GooglePlay", "target": "android", "label": "Release AAB", "ext": ".aab", "development": False},
}


def _safe(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "", str(text).replace(" ", "")) or "Game"


def output(project, kind):
    spec = KINDS[kind]
    shared = release.effective(project, release.BUILD_STORE[spec["store"]])
    folder = project.root / "Build" / spec["store"] / ("Windows" if spec["target"] == "windows" else "Android")
    if spec.get("folder"):
        return folder
    name = f"{_safe(shared.get('name', 'Game'))}_{_safe(shared.get('version', '0'))}_{shared.get('build', 0)}{spec['ext']}"
    return folder / name


def record_path(path):
    return Path(str(path).rstrip("\\/") + ".json")


def latest(project, kind):
    """The newest existing build of this kind, with its record."""
    spec = KINDS[kind]
    if spec.get("folder"):
        path = output(project, kind)
        candidates = [path] if path.is_dir() and any(path.glob("*.exe")) else []
    else:
        folder = output(project, kind).parent
        candidates = sorted(folder.glob("*" + spec["ext"]), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    if not candidates:
        return {"kind": kind, "label": spec["label"], "exists": False, "path": str(output(project, kind))}
    path = candidates[0]
    info = {"kind": kind, "label": spec["label"], "exists": True, "path": str(path)}
    try:
        info.update(json.loads(record_path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    info["path"] = str(path)
    size = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() else path.stat().st_size
    info["sizeMB"] = round(size / 1048576)
    return info


def _git(project, *args):
    try:
        return subprocess.run(["git", "-C", str(project.root), *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _history_file(project):
    return project.root / "Build" / "history.json"


def history(project, kind=None):
    """Every build the desk made, newest first. Only the newest of a kind still exists on disk for folder builds."""
    try:
        items = json.loads(_history_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []
    if not items:
        current = latest(project, kind) if kind else None
        if current and current.get("exists") and current.get("finished"):
            items = [{"kind": kind, "version": current.get("version", ""), "build": current.get("build", 0), "branch": "",
                      "commit": "", "finished": current["finished"], "minutes": current.get("minutes"), "sizeMB": current.get("sizeMB"),
                      "result": current.get("result", ""), "path": current["path"], "uploaded": current.get("uploaded", "")}]
    items = [i for i in items if kind is None or i.get("kind") == kind]
    for i in items:
        i["exists"] = Path(i.get("path", "")).exists()
    return sorted(items, key=lambda i: i.get("finished", ""), reverse=True)


def _add_history(project, entry):
    items = history(project)
    for i in items:
        i.pop("exists", None)
    items.insert(0, entry)
    _history_file(project).parent.mkdir(parents=True, exist_ok=True)
    _history_file(project).write_text(json.dumps(items[:200], indent=2), encoding="utf-8")


def mark_uploaded(project, kind, where):
    items = history(project)
    for i in items:
        i.pop("exists", None)
        if i.get("kind") == kind:
            i["uploaded"] = where
            break
    _history_file(project).write_text(json.dumps(items, indent=2), encoding="utf-8")


def build(project, kind):
    """Runs the Unity build. A first Android build can take over an hour, longer than the CLI call, so wait for the record."""
    spec = KINDS[kind]
    path = output(project, kind)
    record = record_path(path)
    started = time.time()
    branch, commit = _git(project, "rev-parse", "--abbrev-ref", "HEAD"), _git(project, "rev-parse", "--short", "HEAD")
    if _git(project, "status", "--porcelain", "--untracked-files=no"):
        commit += "+changes"
    if record.exists():
        record.unlink()
    store = release.BUILD_STORE[spec["store"]]
    # What's new as written; when empty, the Release-note lines committed since the previous build of this kind.
    notes = release.changes(release.effective(project, store)["whatsNew"] or release.draft(project, last_commit(project, kind)))
    unity.call(project.root, f"return ReleaseDesk.Editor.DeskEntry.ApplySettings({unity.literal(release.unity_file(project, store))});")
    signing = ""
    if kind == "play-aab":
        from . import play  # play imports builds
        key = play.key_state(project)
        if not key["ready"]:
            return False, "Create the upload key first (Keys & accounts)."
        signing = f", {unity.literal(key['keystore'])}, {unity.literal(key['credential'])}"
    code = (f"return ReleaseDesk.Editor.DeskEntry.Build({unity.literal(spec['target'])}, {unity.literal(path)}, "
            f"{'true' if spec['development'] else 'false'}, {unity.literal(record)}{signing});")
    ok, message = unity.call(project.root, code, timeout=600)
    still_running = "did not answer" in str(message) or "timeout" in str(message).lower()
    if not ok and not still_running and not record.exists():
        return False, message
    deadline = time.time() + 4 * 3600
    try:
        while not record.exists() and time.time() < deadline:
            jobs.sleep(10)
    except jobs.Cancelled:
        raise jobs.Cancelled("Stopped waiting for Unity. If it is still building, press Cancel in Unity's build progress window.") from None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        errors = unity_errors(project, started)
        return False, f"{message}\n{errors[-1200:]}" if errors else message
    info = latest(project, kind)
    _add_history(project, {"kind": kind, "version": data.get("version", ""), "build": data.get("build", 0), "branch": branch,
                           "commit": commit, "finished": data.get("finished", ""), "minutes": data.get("minutes"),
                           "sizeMB": info.get("sizeMB") if data.get("result") == "Succeeded" else None,
                           "result": data.get("result", ""), "path": str(path), "uploaded": "", "changes": notes})
    if data.get("result") != "Succeeded":
        errors = unity_errors(project, started)
        return False, f"{spec['label']} build {data.get('result')} with {data.get('errors')} errors\n{errors[-1200:]}"
    return True, f"{spec['label']} {data['version']} ({data['build']}) in {data['minutes']} min: {path}"


def last_commit(project, kind=None):
    """Commit of the newest build (of this kind), where the next change list starts."""
    return next((h.get("commit", "") for h in history(project, kind) if h.get("commit")), "")


def build_all(project, kinds):
    """Builds the chosen kinds one after another (Unity runs one build at a time); stops at the first failure."""
    kinds = [k for k in kinds if k in KINDS]
    if not kinds:
        return False, "Choose at least one build."
    lines = []
    for kind in kinds:
        ok, message = build(project, kind)
        lines.append(message)
        if not ok:
            rest = ", ".join(KINDS[k]["label"] for k in kinds[len(lines):])
            return False, "\n".join(lines + ([f"Stopped; not built: {rest}"] if rest else []))
    return True, "\n".join(lines)


def unity_errors(project, since):
    """Errors and exceptions from the Unity Editor log written after `since`, saved to Store/Logs/unity-build.txt."""
    # Projects can redirect the Editor log into <project>/Logs/Editor.log; prefer that when it exists.
    log = project.root / "Logs" / "Editor.log"
    if not log.is_file():
        log = Path(os.environ.get("LOCALAPPDATA", "")) / "Unity" / "Editor" / "Editor.log"
    try:
        if log.stat().st_mtime < since:
            return ""
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    keep = [l for l in lines[-20000:] if re.search(r"error|exception|failed|Build Finished|Build completed", l, re.I)
            and "Licensing" not in l][-60:]
    text = "\n".join(keep)
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "unity-build.txt").write_text(text, encoding="utf-8")
    return text


def unity_activity():
    """What the Unity Editor says it is doing (window title), e.g. 'Compiling shader variants (busy for 12:03)'."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-Process Unity -ErrorAction SilentlyContinue | Where-Object MainWindowTitle | Select-Object -First 1).MainWindowTitle"],
                             capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return out if "busy" in out.lower() or "..." in out else ""


def run_windows(project, kind="steam-windows"):
    folder = output(project, kind)
    exes = [p for p in folder.glob("*.exe") if "UnityCrashHandler" not in p.name]
    if not exes:
        return False, "Build Windows first."
    subprocess.Popen([str(exes[0])], cwd=str(folder))
    return True, f"Started {exes[0].name}"


# Android phone -------------------------------------------------------------

def adb():
    for candidate in [os.environ.get("ANDROID_HOME", ""), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")]:
        exe = Path(candidate) / "platform-tools" / "adb.exe"
        if candidate and exe.is_file():
            return str(exe)
    hub = Path("C:/Program Files/Unity")
    for exe in sorted(hub.glob("*/Editor/Data/PlaybackEngines/AndroidPlayer/SDK/platform-tools/adb.exe"), reverse=True):
        return str(exe)
    return None


def devices():
    exe = adb()
    if not exe:
        return {"adb": None, "devices": []}
    try:
        out = subprocess.run([exe, "devices", "-l"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return {"adb": exe, "devices": []}
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), parts[0])
            found.append({"serial": parts[0], "state": parts[1], "model": model.replace("_", " ")})
    return {"adb": exe, "devices": found}


def install(project, package):
    exe = adb()
    info = latest(project, "play-dev-apk")
    if not exe:
        return False, "adb not found (install the Unity Android module)."
    if not info["exists"]:
        return False, "Build the phone test APK first."
    ready = [d for d in devices()["devices"] if d["state"] == "device"]
    if not ready:
        return False, "No phone connected. Plug it in by USB, enable USB debugging and accept the prompt on the phone."
    run = jobs.run([exe, "-s", ready[0]["serial"], "install", "-r", info["path"]], timeout=900)
    if "Success" not in run.stdout:
        return False, (run.stdout + run.stderr).strip()[-400:]
    if package:
        jobs.run([exe, "-s", ready[0]["serial"], "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
                       timeout=60)
    return True, f"Installed {Path(info['path']).name} on {ready[0]['model']}" + (" and started it" if package else "")
