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

from . import unity

KINDS = {
    "steam-windows": {"store": "Steam", "target": "windows", "label": "Windows", "folder": True, "development": False},
    "play-dev-apk": {"store": "GooglePlay", "target": "android", "label": "Phone test APK", "ext": "-dev.apk", "development": True},
    "play-aab": {"store": "GooglePlay", "target": "android", "label": "Release AAB", "ext": ".aab", "development": False},
}


def _safe(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "", str(text).replace(" ", "")) or "Game"


def output(project, kind):
    spec = KINDS[kind]
    shared = project.read("store.json", {}) or {}
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


def build(project, kind):
    """Runs the Unity build. A first Android build can take over an hour, longer than the CLI call, so wait for the record."""
    spec = KINDS[kind]
    path = output(project, kind)
    record = record_path(path)
    started = time.time()
    if record.exists():
        record.unlink()
    unity.call(project.root, f"return ReleaseDesk.Editor.DeskEntry.ApplySettings({unity.literal(project.store / 'store.json')});")
    code = (f"return ReleaseDesk.Editor.DeskEntry.Build({unity.literal(spec['target'])}, {unity.literal(path)}, "
            f"{'true' if spec['development'] else 'false'}, {unity.literal(record)});")
    ok, message = unity.call(project.root, code, timeout=600)
    still_running = "did not answer" in str(message) or "timeout" in str(message).lower()
    if not ok and not still_running and not record.exists():
        return False, message
    deadline = time.time() + 4 * 3600
    while not record.exists() and time.time() < deadline:
        time.sleep(10)
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        errors = unity_errors(project, started)
        return False, f"{message}\n{errors[-1200:]}" if errors else message
    if data.get("result") != "Succeeded":
        errors = unity_errors(project, started)
        return False, f"{spec['label']} build {data.get('result')} with {data.get('errors')} errors\n{errors[-1200:]}"
    return True, f"{spec['label']} {data['version']} ({data['build']}) in {data['minutes']} min: {path}"


def unity_errors(project, since):
    """Errors and exceptions from the Unity Editor log written after `since`, saved to Store/Logs/unity-build.txt."""
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


def run_windows(project):
    folder = output(project, "steam-windows")
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
    run = subprocess.run([exe, "-s", ready[0]["serial"], "install", "-r", info["path"]], capture_output=True, text=True, timeout=900)
    if "Success" not in run.stdout:
        return False, (run.stdout + run.stderr).strip()[-400:]
    if package:
        subprocess.run([exe, "-s", ready[0]["serial"], "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"],
                       capture_output=True, text=True, timeout=60)
    return True, f"Installed {Path(info['path']).name} on {ready[0]['model']}" + (" and started it" if package else "")
