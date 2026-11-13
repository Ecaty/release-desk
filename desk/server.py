"""Release Desk local server. Usage: python -m desk.server [unity-project-folder]  (serves http://127.0.0.1:27760)"""
import json
import subprocess
import sys
import threading
import urllib.parse
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import art, builds, play, release, shots, steam, unity
from .project import Project, load_config, save_config

ROOT = Path(__file__).resolve().parent.parent
PORT = 27760
STATE = {"project": None, "jobs": {}}
LOCK = threading.Lock()


def project():
    if STATE["project"] is None:
        raise ValueError("Choose a Unity project folder first.")
    return STATE["project"]


def open_project(path):
    STATE["project"] = Project(path)
    release.migrate(STATE["project"])
    config = load_config()
    recent = [p for p in config.get("recent", []) if p != str(STATE["project"].root)]
    config["recent"] = [str(STATE["project"].root)] + recent[:5]
    save_config(config)


def overview():
    p = project()
    unity_settings = p.unity_settings()
    shared = p.read("store.json", {}) or {}
    sync = [
        {"label": "Product name", "desk": shared.get("name", ""), "unity": unity_settings["productName"]},
        {"label": "Version", "desk": shared.get("version", ""), "unity": unity_settings["version"]},
        {"label": "Build number", "desk": str(shared.get("build", "")), "unity": unity_settings["androidBuild"]},
    ]
    if shared.get("android", {}).get("package"):
        sync.append({"label": "Android package", "desk": shared["android"]["package"], "unity": unity_settings["androidPackage"]})
    for row in sync:
        row["same"] = row["desk"] == row["unity"]
    config = load_config()
    s = steam.status(p, config)
    open_steps = [x for x in s["steps"] if x["state"] != "ok"]
    g = play.status(p)
    play_open = [x for x in g["steps"] if x["state"] != "ok"]
    return {"project": str(p.root), "editor": unity_settings["editor"], "hasStore": p.has_store(), "shared": shared, "sync": sync,
            "stores": [{"id": "steam", "name": "Steam", "done": len(s["steps"]) - len(open_steps), "total": len(s["steps"]),
                        "next": open_steps[0]["title"] if open_steps else "Ready"},
                       {"id": "epic", "name": "Epic Games Store", "later": True},
                       {"id": "play", "name": "Google Play", "done": len(g["steps"]) - len(play_open), "total": len(g["steps"]),
                        "next": play_open[0]["title"] if play_open else "Ready"}],
            "jobs": STATE["jobs"]}


def run_job(name, fn):
    """Long work (Unity builds, uploads) runs in the background; the page polls /api/jobs."""
    with LOCK:
        if STATE["jobs"].get(name, {}).get("state") == "running":
            return {"state": "running"}
        STATE["jobs"][name] = {"state": "running", "message": "", "started": time.time()}

    def work():
        started = time.time()
        try:
            ok, message = fn()
        except Exception as error:  # report any failure to the page and the log
            ok, message = False, f"{type(error).__name__}: {error}"
        STATE["jobs"][name] = {"state": "done" if ok else "failed", "message": str(message)[:1500], "started": started, "ended": time.time()}
        p = STATE["project"]
        minutes = round((time.time() - started) / 60, 1)
        p.log(f"{name}: {'ok' if ok else 'failed'} ({minutes} min)", str(message).splitlines()[:12]
              + (play.summary_lines(p) if "Play" in name or "AAB" in name else steam.summary_lines(p, load_config())))

    threading.Thread(target=work, daemon=True).start()
    return STATE["jobs"][name]


# A native folder picker in its own process (Tk wants the main thread; the server runs request threads).
PICK_FOLDER = """
import sys, tkinter
from tkinter import filedialog
root = tkinter.Tk(); root.withdraw(); root.attributes('-topmost', True)
print(filedialog.askdirectory(parent=root, initialdir=sys.argv[1] or None, mustexist=True,
                              title='Choose the Unity project folder') or '')
"""


def browse(start=""):
    """Asks for a folder with the system dialog; returns '' when cancelled."""
    run = subprocess.run([sys.executable, "-c", PICK_FOLDER, start], capture_output=True, text=True, timeout=600)
    return str(Path(run.stdout.strip())) if run.stdout.strip() else ""


def apply_to_unity():
    p = project()
    return unity.call(p.root, f"return ReleaseDesk.Editor.DeskEntry.ApplySettings({unity.literal(p.store / 'store.json')});")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        try:
            if self.path.startswith("/store-file/"):
                p = project()
                rel = urllib.parse.unquote(self.path[len("/store-file/"):].split("?")[0])
                target = (p.store / rel).resolve()
                if p.store.resolve() not in target.parents or target.suffix.lower() not in (".png", ".jpg") or not target.is_file():
                    return self.send(404, {"error": "not found"})
                return self.send(200, target.read_bytes(), "image/png" if target.suffix.lower() == ".png" else "image/jpeg")
            if self.path.split("?")[0] in ("/", "/index.html"):
                return self.send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
            if self.path.startswith("/icons/") and self.path.endswith(".svg"):
                icon = (ROOT / "web" / "icons" / Path(self.path).name)
                return self.send(200, icon.read_bytes(), "image/svg+xml") if icon.is_file() else self.send(404, {"error": "not found"})
            if self.path == "/api/release":
                return self.send(200, {**release.status(project()), "kinds": {k: v["label"] for k, v in builds.KINDS.items()},
                                       "buildStore": {k: release.BUILD_STORE[v["store"]] for k, v in builds.KINDS.items()}})
            if self.path == "/api/start":
                return self.send(200, {"project": str(STATE["project"].root) if STATE["project"] else "", "recent": load_config().get("recent", [])})
            if self.path == "/api/overview":
                return self.send(200, overview())
            if self.path == "/api/steam":
                return self.send(200, steam.status(project(), load_config()))
            if self.path == "/api/keys":
                config = load_config()
                return self.send(200, {"steamcmd": steam.steamcmd_state(config), "unityCli": bool(unity.cli()),
                                       "play": {"key": play.key_state(project()), "account": play.playapi.account_state()}})
            if self.path == "/api/shots":
                return self.send(200, {"shots": shots.shot_list(project())})
            if self.path == "/api/play":
                p = project()
                return self.send(200, {**play.status(p), "builds": [builds.latest(p, "play-dev-apk"), builds.latest(p, "play-aab")],
                                       "history": builds.history(p, "play-dev-apk") + builds.history(p, "play-aab"),
                                       "phones": builds.devices(), "package": p.unity_settings()["androidPackage"]})
            if self.path == "/api/log":
                p = project()
                return self.send(200, {"text": p.latest_log(), "history": p.history(),
                                       "tools": {"SteamCMD": p.tool_log("steamcmd.txt"), "Unity build errors": p.tool_log("unity-build.txt", 60)}})
            if self.path == "/api/jobs":
                jobs = {k: dict(v) for k, v in STATE["jobs"].items()}
                running = [v for v in jobs.values() if v["state"] == "running"]
                for v in running:
                    v["elapsed"] = round(time.time() - v["started"])
                if running:
                    activity = builds.unity_activity()
                    for v in running:
                        v["activity"] = activity
                return self.send(200, jobs)
            self.send(404, {"error": "not found"})
        except ValueError as error:
            self.send(400, {"error": str(error)})

    def do_POST(self):
        try:
            data = self.body()
            p = STATE["project"]
            if self.path == "/api/browse":
                return self.send(200, {"path": browse(str(data.get("start", "")))})
            if self.path == "/api/open":
                open_project(data["path"])
                return self.send(200, {"ok": True})
            if self.path == "/api/play/listing":
                play.save_listing(project(), data)
                return self.send(200, {"ok": True})
            if self.path == "/api/play/key":
                ok, message = play.create_key(project())
                return self.send(200 if ok else 400, {"ok": ok, "error": message, "message": message})
            if self.path == "/api/play/publish":
                preview = bool(data.get("preview", True))
                return self.send(200, run_job("Google Play: publish preview" if preview else "Google Play: publish",
                                              lambda: play.publish(project(), preview)))
            if self.path == "/api/steam/listing":
                steam.save_listing(project(), data)
                return self.send(200, {"ok": True})
            if self.path == "/api/release":
                release.save(project(), data.get("values", {}), data.get("store") or None, data.get("override"))
                return self.send(200, {"ok": True})
            if self.path == "/api/release/draft":
                return self.send(200, {"text": release.draft(project(), builds.last_commit(project()))})
            if self.path == "/api/build/all":
                kinds = [k for k in data.get("kinds", []) if k in builds.KINDS]
                return self.send(200, run_job("Build all", lambda: builds.build_all(project(), kinds)))
            if self.path == "/api/keys/steam-user":
                config = load_config()
                config["steamUser"] = str(data.get("user", "")).strip()
                save_config(config)
                return self.send(200, {"ok": True})
            if self.path == "/api/refresh":
                text = project().log("Refresh", steam.summary_lines(project(), load_config()) + play.summary_lines(project()))
                return self.send(200, {"text": text})
            if self.path == "/api/unity/apply":
                return self.send(200, run_job("Push to Unity", apply_to_unity))
            if self.path == "/api/build":
                kind = data["kind"]
                spec = builds.KINDS[kind]
                return self.send(200, run_job(f"Build {spec['store']} {spec['label']}", lambda: builds.build(project(), kind)))
            if self.path == "/api/shots/capture":
                only = str(data.get("only", ""))
                return self.send(200, run_job("Capture screenshots" + (f" ({only})" if only else ""), lambda: shots.capture(project(), only)))
            if self.path == "/api/art/capsules":
                return self.send(200, run_job("Make capsules", lambda: art.make_capsules(project())))
            if self.path == "/api/art/icons":
                return self.send(200, run_job("Make icons", lambda: art.make_icons(project())))
            if self.path == "/api/run/windows":
                ok, message = builds.run_windows(project())
                return self.send(200 if ok else 400, {"ok": ok, "error": message, "message": message})
            if self.path == "/api/play/install":
                p = project()
                return self.send(200, run_job("Install on phone", lambda: builds.install(p, p.unity_settings()["androidPackage"])))
            if self.path == "/api/steam/upload":
                preview = bool(data.get("preview", True))
                name = "Steam: upload preview" if preview else "Steam: upload"
                return self.send(200, run_job(name, lambda: steam.upload(project(), load_config(), preview)))
            self.send(404, {"error": "not found"})
        except (ValueError, KeyError) as error:
            self.send(400, {"error": str(error)})


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else (load_config().get("recent") or [None])[0]
    if path:
        try:
            open_project(path)
        except ValueError as error:
            print(error)
    # Windows lets several processes share a port when address reuse is on; a second desk must fail instead.
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Release Desk is already running: http://127.0.0.1:{PORT}/")
        if "--no-browser" not in sys.argv:
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Release Desk: {url}")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
