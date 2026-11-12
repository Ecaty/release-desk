"""A game project: its Unity settings and its Store/ data folder."""
import datetime
import json
import os
import re
import subprocess
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "release-desk"


def load_config():
    try:
        return json.loads((CONFIG_DIR / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


class Project:
    def __init__(self, unity_path):
        self.root = Path(unity_path).resolve()
        if not (self.root / "ProjectSettings" / "ProjectSettings.asset").is_file():
            raise ValueError(f"Not a Unity project: {self.root}")
        self.store = self.root / "Store"

    # Unity ---------------------------------------------------------------
    def unity_settings(self):
        text = (self.root / "ProjectSettings" / "ProjectSettings.asset").read_text(encoding="utf-8", errors="replace")

        def scalar(key):
            m = re.search(rf"^\s*{key}:\s*(.*)$", text, re.M)
            return m.group(1).strip() if m else ""

        android = ""
        m = re.search(r"applicationIdentifier:\s*\n((?:\s+\w+:.*\n)+)", text)
        if m:
            a = re.search(r"Android:\s*(.*)", m.group(1))
            android = a.group(1).strip() if a else ""
        version = (self.root / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8")
        editor = re.search(r"m_EditorVersion:\s*(\S+)", version)
        return {
            "productName": scalar("productName"),
            "version": scalar("bundleVersion"),
            "androidBuild": scalar("AndroidBundleVersionCode"),
            "androidPackage": android,
            "editor": editor.group(1) if editor else "",
        }

    # Store data ------------------------------------------------------------
    def has_store(self):
        return (self.store / "store.json").is_file()

    def read(self, rel, default=None):
        try:
            return json.loads((self.store / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def write(self, rel, data):
        path = self.store / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def git_commit(self, path):
        try:
            return subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    # Log -------------------------------------------------------------------
    def log(self, title, lines):
        """Write the run summary agents and people read first: Store/Logs/latest.txt."""
        logs = self.store / "Logs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        body = f"[{stamp}] {title}\n" + "".join(f"  {line}\n" for line in lines)
        (logs / "latest.txt").write_text(body, encoding="utf-8")
        with open(logs / "history.txt", "a", encoding="utf-8") as f:
            f.write(body + "\n")
        return body

    def latest_log(self):
        try:
            return (self.store / "Logs" / "latest.txt").read_text(encoding="utf-8")
        except OSError:
            return ""
