"""Calls into the running Unity Editor of a project through the Unity CLI."""
import json
import os
import shutil
import subprocess
from pathlib import Path


def cli():
    found = shutil.which("unity")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "unity.exe"
    return str(candidate) if candidate.exists() else None


def call(project_root, code, timeout=300):
    """Evaluate a C# statement in the project's open Editor. Returns (ok, result or error text)."""
    exe = cli()
    if not exe:
        return False, "Unity CLI not found (install it from Unity Hub or the Microsoft Store)."
    args = [exe, "command", "--timeout", str(timeout), "--project-path", str(project_root),
            "--caller", "plugin", "--skill", "unity-cli", "--format", "json", "script", "eval", code]
    try:
        run = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return False, "Unity did not answer in time; it may still be working."
    try:
        data = json.loads(run.stdout)
    except ValueError:
        return False, (run.stdout or run.stderr).strip()[:400]
    if data.get("success"):
        return True, data.get("result")
    errors = data.get("errors") or [{}]
    return False, errors[0].get("message", "Unity command failed.")[:400]


def literal(text):
    return json.dumps(str(text))
