"""Calls into the Unity Editor of a project through the Unity CLI, opening the Editor first when it is closed."""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import jobs

NOT_RUNNING = "No Pipeline instance found"
# Messages that mean "closed, starting or busy reloading": wait, do not fail.
NOT_READY = (NOT_RUNNING, "still settling", "not serviceable", "did not answer", "did not start within")


def _not_ready(message):
    return any(text in str(message) for text in NOT_READY)
OPEN_TIMEOUT = 45 * 60  # a first import of a large project can take long


def cli():
    found = shutil.which("unity")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "unity.exe"
    return str(candidate) if candidate.exists() else None


def editor_version(project_root):
    try:
        text = (Path(project_root) / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"m_EditorVersion:\s*(\S+)", text)
    return m.group(1) if m else ""


def editor_exe(project_root):
    """The Editor of exactly the project's Unity version, from the Hub install folders."""
    version = editor_version(project_root)
    roots = [Path("C:/Program Files/Unity"), Path("C:/Program Files/Unity/Hub/Editor")]
    try:
        hub = json.loads((Path(os.environ.get("APPDATA", "")) / "UnityHub" / "secondaryInstallPath.json").read_text(encoding="utf-8"))
        if hub:
            roots.insert(0, Path(hub))
    except (OSError, ValueError):
        pass
    for root in roots:
        exe = root / version / "Editor" / "Unity.exe"
        if version and exe.is_file():
            return exe
    return None


def project_open(project_root):
    """True while an Editor holds the project's lock file (so a second Editor must not be started)."""
    lock = Path(project_root) / "Temp" / "UnityLockfile"
    if not lock.exists():
        return False
    try:
        with open(lock, "a"):
            return False
    except OSError:
        return True


def _call(project_root, code, timeout):
    exe = cli()
    if not exe:
        return False, "Unity CLI not found (install it from Unity Hub or the Microsoft Store)."
    args = [exe, "command", "--timeout", str(timeout), "--project-path", str(project_root),
            "--caller", "plugin", "--skill", "unity-cli", "--format", "json", "script", "eval", code]
    try:
        run = jobs.run(args, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return False, "Unity did not answer in time; it may still be working."
    # Pipeline 1.0 prints the eval value itself and reports failures on stderr with a non-zero exit;
    # 0.10 wrapped both in {"success", "result" | "errors"}. Accept either.
    try:
        data = json.loads(run.stdout)
    except ValueError:
        data = None
        if run.returncode == 0 and run.stdout.strip():
            return False, run.stdout.strip()[:400]
    if isinstance(data, dict) and "success" in data and ("result" in data or "errors" in data or not data["success"]):
        if data["success"]:
            return True, data.get("result")
        errors = data.get("errors") or [{}]
        return False, str(errors[0].get("message", "Unity command failed."))[:400]
    if run.returncode == 0 and run.stdout.strip():
        return True, data
    text = "\n".join(line[7:] if line.startswith("error: ") else line for line in (run.stderr or run.stdout).strip().splitlines())
    return False, (text or f"Unity command failed (exit {run.returncode}).")[:400]


def ensure_editor(project_root):
    """Opens the project in its Unity version when no Editor has it, then waits until the Editor answers."""
    ok, message = _call(project_root, "return 1;", 30)
    if ok or not _not_ready(message):
        return ok, message
    if NOT_RUNNING in str(message) and not project_open(project_root):
        exe = editor_exe(project_root)
        if not exe:
            return False, f"Unity {editor_version(project_root)} is not installed; install it from Unity Hub."
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(exe), "-projectPath", str(project_root)], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + OPEN_TIMEOUT
    while time.time() < deadline:
        jobs.sleep(15)
        ok, message = _call(project_root, "return 1;", 30)
        if ok:
            jobs.sleep(5)  # let the Editor finish its first domain reload
            return True, "Unity ready"
        if not _not_ready(message):
            return False, message
    return False, "Unity did not finish opening in time."


def call(project_root, code, timeout=300):
    """Evaluate a C# statement in the project's Editor, opening the Editor first if it is closed.
    Returns (ok, result or error text)."""
    ok, message = _call(project_root, code, timeout)
    if ok or not _not_ready(message) or "did not answer" in str(message):
        return ok, message
    opened, why = ensure_editor(project_root)
    if not opened:
        return False, why
    return _call(project_root, code, timeout)


def literal(text):
    return json.dumps(str(text))
