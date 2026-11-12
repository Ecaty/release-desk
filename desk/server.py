"""Release Desk local server. Usage: python -m desk.server [unity-project-folder]  (serves http://127.0.0.1:27760)"""
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import builds, steam, unity
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
    return {"project": str(p.root), "editor": unity_settings["editor"], "hasStore": p.has_store(), "shared": shared, "sync": sync,
            "stores": [{"id": "steam", "name": "Steam", "done": len(s["steps"]) - len(open_steps), "total": len(s["steps"]),
                        "next": open_steps[0]["title"] if open_steps else "Ready"},
                       {"id": "epic", "name": "Epic Games Store", "later": True},
                       {"id": "play", "name": "Google Play", "builds": True}],
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
        p.log(f"{name}: {'ok' if ok else 'failed'} ({minutes} min)", str(message).splitlines()[:12] + steam.summary_lines(p, load_config()))

    threading.Thread(target=work, daemon=True).start()
    return STATE["jobs"][name]


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
            if self.path in ("/", "/index.html"):
                return self.send(200, (ROOT / "web" / "index.html").read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/start":
                return self.send(200, {"project": str(STATE["project"].root) if STATE["project"] else "", "recent": load_config().get("recent", [])})
            if self.path == "/api/overview":
                return self.send(200, overview())
            if self.path == "/api/steam":
                return self.send(200, steam.status(project(), load_config()))
            if self.path == "/api/keys":
                config = load_config()
                return self.send(200, {"steamcmd": steam.steamcmd_state(config), "unityCli": bool(unity.cli())})
            if self.path == "/api/play":
                p = project()
                return self.send(200, {"builds": [builds.latest(p, "play-dev-apk"), builds.latest(p, "play-aab")],
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
            if self.path == "/api/open":
                open_project(data["path"])
                return self.send(200, {"ok": True})
            if self.path == "/api/steam/listing":
                steam.save_listing(project(), data)
                return self.send(200, {"ok": True})
            if self.path == "/api/shared":
                shared = project().read("store.json", {}) or {}
                for key in ("name", "version"):
                    if key in data:
                        shared[key] = str(data[key]).strip()
                if "build" in data:
                    shared["build"] = int(data["build"])
                project().write("store.json", shared)
                return self.send(200, {"ok": True})
            if self.path == "/api/keys/steam-user":
                config = load_config()
                config["steamUser"] = str(data.get("user", "")).strip()
                save_config(config)
                return self.send(200, {"ok": True})
            if self.path == "/api/refresh":
                text = project().log("Refresh: Steam", steam.summary_lines(project(), load_config()))
                return self.send(200, {"text": text})
            if self.path == "/api/unity/apply":
                return self.send(200, run_job("Push to Unity", apply_to_unity))
            if self.path == "/api/build":
                kind = data["kind"]
                spec = builds.KINDS[kind]
                return self.send(200, run_job(f"Build {spec['store']} {spec['label']}", lambda: builds.build(project(), kind)))
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
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Release Desk: {url}")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
