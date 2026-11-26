"""itch.io: listing and art checks, Windows and Android build uploads with butler (itch.io's official upload tool).

One itch.io page carries both downloads: the Windows build goes to the windows channel, the Android APK (signed with
the Google Play upload key, so players can update it) to the android channel. The desk shows the Android part as its
own store under Android; text, art and the page itself are shared with itch.io.

No review or fee; the page is edited on itch.io. butler keeps its own login after `butler login` (a browser sign-in
in its console); the desk never reads it. butler's key may only upload, so the game's number (for a direct Edit game
link) comes from `butler status` once a build is uploaded. Pushes only send what changed since the previous build."""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
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
# Every .exe and .dll in the butler archive carries itch.io's Authenticode signature (checked 2026-11-22 on 15.32.0:
# butler.exe, 7z.dll and c7zip.dll, "CN=itch corp., O=itch corp.", issued by Microsoft ID Verified CS AOC CA 04).
SIGNER_SUBJECT = "CN=itch corp., O=itch corp., L=San Francisco, S=California, C=US"
# Microsoft Trusted Signing issues from rotating intermediates ("... CS AOC CA 04" today), so the issuer is matched
# by its fixed shape, not one CA number; the chain must still validate for Windows to report Valid.
SIGNER_ISSUER = re.compile(r"CN=Microsoft ID Verified CS [A-Z]{2,4} CA [0-9]{2}, O=Microsoft Corporation, C=US")
# itch.io's mirror bucket that broth redirects to (seen 2026-11-22); another account's bucket is refused.
MIRROR_HOST = "itchio-mirror.cb031a832f44726753d6267436f3b414.r2.cloudflarestorage.com"
MAX_DOWNLOAD = 200 * 1024 * 1024  # 15.32.0 is 10.35 MiB
MAX_UNPACKED = 500 * 1024 * 1024  # 15.32.0 unpacks to 26 MiB


def project_id(text):
    """butler wants user/game. Accepts that, or the page address as copied from the browser
    (https://user.itch.io/game, with or without https://, www., a trailing slash or a query)."""
    text = str(text or "").strip()
    m = re.fullmatch(r"(?:https?://)?(?:www\.)?([a-z0-9][a-z0-9_-]*)\.itch\.io/([a-z0-9][a-z0-9_-]*)/?(?:[?#].*)?", text, re.I | re.ASCII)
    if m and m.group(1).lower() != "www":
        return f"{m.group(1)}/{m.group(2)}".lower()
    m = re.fullmatch(r"([a-z0-9][a-z0-9_-]*)/([a-z0-9][a-z0-9_-]*)", text, re.I | re.ASCII)
    if m and m.group(1).lower() != "www":
        return text.lower()
    if text:
        raise ValueError("itch.io project: use user/game or the page address (https://user.itch.io/game).")
    return ""


def settings(project):
    data = (project.read("store.json", {}) or {}).get("itch", {}) or {}
    try:
        pid = project_id(data.get("project", ""))  # an address saved before the desk normalised it still works
    except ValueError:
        pid = ""  # unusable: never handed to butler; the setup step asks for it again
    return {"project": pid, "channel": data.get("channel", "windows"), "androidChannel": data.get("androidChannel", "android")}


def butler():
    local = sorted(TOOL_DIR.glob("**/butler.exe"))
    return str(local[0]) if local else shutil.which("butler")


def version(exe):
    try:
        out = subprocess.run([exe, "-V"], capture_output=True, text=True, timeout=30)
        return (out.stdout + out.stderr).strip().splitlines()[0] if (out.stdout + out.stderr).strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def allowed_url(url):
    """Downloads go only over https to broth.itch.zone or the itch.io mirror it redirects to."""
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and host in ("broth.itch.zone", MIRROR_HOST) and u.port in (None, 443)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError(f"butler download was redirected to an unexpected address ({urllib.parse.urlsplit(newurl).hostname}); nothing was installed.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, timeout):
    if not allowed_url(url):
        raise ValueError("Unexpected butler download address.")
    r = urllib.request.build_opener(_Redirects).open(url, timeout=timeout)
    if not allowed_url(r.geturl()):
        r.close()
        raise ValueError("butler download ended at an unexpected address; nothing was installed.")
    return r


def signatures(folder):
    """Authenticode status and signer organisation of every .exe and .dll in folder, read by Windows itself."""
    script = ("Get-ChildItem -LiteralPath $env:RD_CHECK_FOLDER -Recurse -Force -Include *.exe,*.dll | ForEach-Object { $s = Get-AuthenticodeSignature -LiteralPath $_.FullName; "
              "[pscustomobject]@{name=$_.Name; status=[string]$s.Status; subject=[string]$s.SignerCertificate.Subject; issuer=[string]$s.SignerCertificate.Issuer} } | ConvertTo-Json -Compress")
    env = dict(os.environ, RD_CHECK_FOLDER=str(folder))  # passed by environment, never pasted into the command text
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=120, env=env)
    data = json.loads(out.stdout or "[]")
    return data if isinstance(data, list) else [data]


def _signed_ok(x):
    return x.get("status") == "Valid" and x.get("subject") == SIGNER_SUBJECT and bool(SIGNER_ISSUER.fullmatch(x.get("issuer") or ""))


def signed_by_itch(folder):
    sigs = signatures(folder)
    names = {x.get("name", "").lower() for x in sigs}
    good = all(_signed_ok(x) for x in sigs)
    return bool(sigs) and "butler.exe" in names and good, sigs


def install(project=None):
    """Downloads the latest Windows butler from itch.io's broth service into the desk's tool folder. Nothing in it runs
    until Windows confirms every .exe and .dll is signed by itch.io; the old copy is kept as a backup until the new one
    is in place and starts. No login happens here."""
    with _open(f"{BROTH}/LATEST", 30) as r:
        latest = r.read(100).decode("utf-8", "replace").strip()
    if not latest or len(latest) > 40 or not all(c.isalnum() or c in ".-" for c in latest):
        return False, "itch.io's download service did not name a butler version."
    jobs.say(f"Downloading butler {latest}")
    TOOL_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive = TOOL_DIR.parent / "butler-download.zip"
    fresh = TOOL_DIR.parent / "butler-new"
    backup = TOOL_DIR.parent / "butler-old"
    shutil.rmtree(fresh, ignore_errors=True)
    try:
        size = 0
        with _open(f"{BROTH}/{latest}/archive/default", 120) as r, open(archive, "wb") as f:
            while chunk := r.read(1 << 20):
                jobs.check()
                size += len(chunk)
                if size > MAX_DOWNLOAD:
                    return False, "The butler download is far larger than expected; nothing was installed."
                f.write(chunk)
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if "butler.exe" not in names or any(n.startswith(("/", "\\")) or ".." in Path(n).parts or ":" in n for n in names):
                return False, "The download is not a butler archive; nothing was installed."
            if sum(i.file_size for i in infos) > MAX_UNPACKED:
                return False, "The butler archive unpacks far larger than expected; nothing was installed."
            z.extractall(fresh)
        jobs.say("Checking itch.io's signature")
        ok, sigs = signed_by_itch(fresh)
        if not ok:
            bad = ", ".join(f"{x.get('name')}: {x.get('status')}" for x in sigs if not _signed_ok(x)) or "no signed files"
            return False, f"The download is not signed by itch.io ({bad}); nothing was installed or run."
        got = version(str(fresh / "butler.exe"))
        if not got:
            return False, "The downloaded butler does not start; nothing was installed."
        shutil.rmtree(backup, ignore_errors=True)
        if TOOL_DIR.exists():
            try:
                TOOL_DIR.rename(backup)
            except OSError:
                return False, "The installed butler is in use (an upload may be running); try again when it has finished."
        try:
            fresh.rename(TOOL_DIR)
        except OSError:
            if backup.exists():
                backup.rename(TOOL_DIR)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return True, f"butler {latest} installed in {TOOL_DIR} ({got}), signed by itch.io."
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(fresh, ignore_errors=True)


DASHBOARD = "https://itch.io/dashboard"


def page_url(project_id):
    """The public page of user/game (https://user.itch.io/game); "" when there is none yet.
    itch.io's Edit game address uses a numeric id the desk does not know, so editing goes through the dashboard."""
    if "/" not in (project_id or ""):
        return ""
    user, game = project_id.split("/", 1)
    return f"https://{user}.itch.io/{game}"


def _guide_new_page():
    return [
        {"text": "Log in (or sign up, free), then this opens Create new project.", "link": "https://itch.io/game/new"},
        {"text": "Title: the game's name. Kind of project: Downloadable. Pricing: No payments."},
        {"text": "Press Save & view page (it stays a Draft)."},
        {"text": "Copy the address bar (https://name.itch.io/game), paste it into Project here, Save.", "go": "itch/keys/ids-itch-project"},
    ]


_EDIT = {}  # project id -> (edit url or "", time looked up)
EDIT_RETRY = 300  # seconds before a failed lookup (offline, not logged in, game not found) is tried again


def _channels(project_id):
    exe = butler()
    if not exe:
        return []
    run = subprocess.run([exe, "status", "--json", project_id], capture_output=True, text=True, timeout=5,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for line in (run.stdout or "").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "result":
            return (d.get("value") or {}).get("channels") or []
    return []


def edit_url(project_id):
    """https://itch.io/game/edit/<number> for user/game, from the game id on its uploaded channels; "" before the first push."""
    page = page_url(project_id).lower()
    if not page:
        return ""
    url, at = _EDIT.get(project_id, ("", 0))
    if url or time.time() - at < EDIT_RETRY:
        return url
    url = ""
    try:
        for ch in _channels(project_id):
            up = ch.get("upload") or {}
            gid = up.get("gameId", up.get("game_id"))
            if str(gid or "").isdigit():
                url = f"https://itch.io/game/edit/{gid}"
                break
    except Exception:
        url = ""
    _EDIT[project_id] = (url, time.time())
    return url


def _guide_edit_page(edit, what):
    return [
        {"text": "Open Edit game on itch.io.", "link": edit} if edit else
        {"text": "Press Edit under the game.", "link": DASHBOARD},
        {"text": what},
        {"text": "Press Save at the bottom."},
    ]


def key_state(project):
    exe, s = butler(), settings(project)
    logged = CREDS.is_file() or bool(os.environ.get("BUTLER_API_KEY"))
    return {"butler": exe or "", "toolFolder": str(TOOL_DIR), "installed": bool(exe), "loggedIn": logged, "project": s["project"],
            "channel": s["channel"], "androidChannel": s["androidChannel"], "ready": bool(exe) and logged and "/" in s["project"],
            "page": page_url(s["project"]), "dashboard": DASHBOARD, "edit": edit_url(s["project"]) if logged else ""}


def _build(project, kind="itch-windows"):
    info = builds.latest(project, kind)
    info["folder"] = info["path"] if kind == "itch-windows" else str(Path(info["path"]).parent)
    info["history"] = builds.history(project, kind)
    return info


def status(project):
    fields = storekit.fields(project, "itch", RULES, name_label="Title")
    art_items, shots, build, key = art.check(project, "itch"), storekit.screenshots(project, RULES), _build(project), key_state(project)
    steps = [
        {"title": "itch.io account and project page", "state": "ok" if "/" in key["project"] else "todo", "kind": "hand",
         "link": key["page"] or "https://itch.io/game/new", "go": "itch/keys/ids-itch-project", "guide": _guide_new_page(),
         "detail": "Create the project page on itch.io (free, no review), then paste its address into Keys & accounts."},
        {"title": "butler installed and logged in", "state": "ok" if key["installed"] and key["loggedIn"] else "todo", "kind": "desk",
         "link": "https://itchio.itch.io/butler", "go": "itch/keys/itch-butler",
         "detail": "Install butler (Keys & accounts downloads itch.io's latest build), then Log in to itch.io.",
         "guide": [{"text": "Press Install butler.", "go": "itch/keys/itch-butler"},
                   {"text": "Press Log in to itch.io, sign in in the browser, allow butler."},
                   {"text": "Come back here: Login shows logged in."}]},
        {"title": "AI disclosure", "state": "todo", "kind": "hand", "link": "https://itch.io/docs/creators/quality-guidelines#accurately-tag-your-use-of-generative-ai",
         "detail": "On the Edit game page, disclose generative AI use: Code (shipped code includes generated contributions), and describe optional live generation and manual creation in the description.",
         "guide": _guide_edit_page(key["edit"], "AI disclosure: answer for your game, tick each kind of generated content it ships.")},
        {"title": "Page text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy", "go": "itch/listing/itch-text",
         "detail": "Paste the tagline and description into Edit game.",
         "guide": [{"text": "Copy the tagline and the description here.", "go": "itch/listing/itch-text"}]
         + _guide_edit_page(key["edit"], "Paste them into Short description and Description.")},
        {"title": "Cover image", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy", "go": "itch/listing/itch-art",
         "detail": "630×500 cover (Make capsules) on Edit game.",
         "guide": _guide_edit_page(key["edit"], "Cover image (right side): upload the file from Listing > Art.")},
        {"title": "Screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy", "go": "itch/listing/itch-shots",
         "detail": f"{shots['good']} usable in Store/{shots['folder']}; add 3 to 5 on Edit game.",
         "guide": _guide_edit_page(key["edit"], f"Screenshots (right side): add 3 to 5 from Store/{shots['folder']}.")},
        {"title": "Windows build", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "itch/builds/itch-builds",
         "detail": "Built by Unity into Build/Itch/Windows."},
        {"title": "Push with butler", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "itch/builds/itch-upload", "detail": f"Pushes to the {key['channel']} channel with the release version; only changes are sent."},
        {"title": "Publish the page", "state": "todo", "kind": "hand", "link": key["edit"] or DASHBOARD,
         "detail": "Set visibility to Public (or Restricted for testers) and pricing on Edit game.",
         "guide": _guide_edit_page(key["edit"], "Visibility & access (bottom): Public, or Restricted for testers only.")
         + ([{"text": "Open the page to check it.", "link": key["page"]}] if key["page"] else [])},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "build": build, "key": key, "steps": steps,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def android_status(project):
    """itch.io Android: the same page, an APK on the android channel."""
    from . import play  # play imports builds
    key, build, sign = key_state(project), _build(project, ANDROID), play.key_state(project)
    steps = [
        {"title": "itch.io page and butler", "state": "ok" if key["ready"] else "todo", "kind": "hand", "go": "itch-android/keys/ids-itch-project",
         "detail": "The same itch.io page as the Windows download: project, butler and its login.",
         "guide": ([] if key["project"] else _guide_new_page()[:4]) + [
             {"text": "Paste the page address into Project here, Save.", "go": "itch-android/keys/ids-itch-project"},
             {"text": "Press Install butler, then Log in to itch.io."}]},
        {"title": "Android package and upload key", "state": "ok" if sign["ready"] else "todo", "kind": "desk", "go": "itch-android/keys/play-key",
         "detail": "The APK is signed with the Google Play upload key, so an update installs over the previous one and the same key serves Play later."},
        {"title": "Android APK", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "itch-android/builds/itch-android-builds",
         "detail": "Built by Unity into Build/Itch/Android."},
        {"title": "Push with butler", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "itch-android/builds/itch-android-upload", "detail": f"Pushes the APK to the {key['androidChannel']} channel; itch.io marks it as the Android download."},
        {"title": "Android on the page", "state": "todo", "kind": "hand", "link": key["edit"] or DASHBOARD,
         "detail": "On Edit game, check the APK upload is tagged Android and say in the description that it installs outside Google Play (players allow it once).",
         "guide": _guide_edit_page(key["edit"], "Uploads: tick Android next to the .apk.")
         + ([{"text": "Open the page on a phone, try the download.", "link": key["page"]}] if key["page"] else [])},
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
    # A string, not a list: a list escapes the inner quotes as \" and cmd refuses the path. cmd /s /c drops the outer pair.
    subprocess.Popen(f'cmd /s /c "title itch.io login & "{exe}" login & echo. & pause"', creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
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
