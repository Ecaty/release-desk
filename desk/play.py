"""Google Play: upload key, listing checks, and publishing an App Bundle with its listing through the Play Developer API.

Secrets never pass through the desk: keytool and cmdkey ask for the upload key password in their own console window,
Unity reads it from Windows Credential Manager during the release build, and the service account JSON is only read
from the path in PLAY_SERVICE_ACCOUNT_JSON to sign the token request."""
import os
import subprocess
import tempfile
from pathlib import Path

from . import art, builds, images, playapi, release

RULES = art.rules("play")
KEY_DIR = Path(os.environ.get("USERPROFILE", Path.home())) / ".release-keys"
ALIAS = "upload"
IMAGE_TYPES = {"icon": "icon", "feature_graphic": "featureGraphic"}  # rules file name -> Play image type


def package(project):
    return ((project.read("store.json", {}) or {}).get("android", {}) or {}).get("package", "")


def settings(project):
    """Store/store.json "play": {"track": "internal", "status": "draft"}. Draft releases wait in Play Console for a
    click (and are the only kind Play accepts while the app was never published); "completed" rolls out to the track."""
    data = (project.read("store.json", {}) or {}).get("play", {}) or {}
    return {"track": data.get("track", "internal"), "status": data.get("status", "draft")}


# Upload key ---------------------------------------------------------------------------------------------------

def keytool(project):
    editor = project.unity_settings()["editor"]
    for root in (Path("C:/Program Files/Unity") / editor, Path("C:/Program Files/Unity/Hub/Editor") / editor):
        exe = root / "Editor" / "Data" / "PlaybackEngines" / "AndroidPlayer" / "OpenJDK" / "bin" / "keytool.exe"
        if exe.is_file():
            return exe
    return None


def key_state(project):
    pkg = package(project)
    keystore = KEY_DIR / f"{pkg or 'app'}-upload.jks"
    credential = f"release-desk/{pkg or 'app'}/upload-key"
    stored = False
    if pkg:
        try:
            out = subprocess.run(["cmdkey", f"/list:{credential}"], capture_output=True, text=True, timeout=15).stdout
            # "cmdkey /list:<name>" echoes the name even when nothing is stored; a stored one has a Target line.
            stored = any(l.strip().lower().startswith("target:") and credential.lower() in l.lower() for l in out.splitlines())
        except (OSError, subprocess.SubprocessError):
            pass
    return {"package": pkg, "keystore": str(keystore), "exists": keystore.is_file(), "credential": credential,
            "stored": stored, "keytool": str(keytool(project) or ""), "ready": bool(pkg) and keystore.is_file() and stored}


def create_key(project):
    """Opens a console where keytool creates the upload keystore and cmdkey stores its password. The desk never sees it."""
    state = key_state(project)
    if not state["package"]:
        return False, "Set the Android package in Store/store.json (android.package) first."
    if not state["keytool"]:
        return False, "keytool not found; install the Android module for this Unity version."
    name = release.effective(project, "play")["name"] or "Game"
    lines = ["@echo off", "title Upload key", "echo Google Play upload key for " + state["package"],
             "echo keytool and cmdkey ask for the password here; Release Desk never sees it. Use one password for both.", "echo.",
             f'if not exist "{KEY_DIR}" mkdir "{KEY_DIR}"']
    if not state["exists"]:
        lines += [f'"{state["keytool"]}" -genkeypair -v -storetype PKCS12 -keystore "{state["keystore"]}" -alias {ALIAS} '
                  f'-keyalg RSA -keysize 2048 -validity 10000 -dname "CN={name.replace(chr(34), "")}"',
                  "if errorlevel 1 goto end", "echo."]
    lines += ["echo Now enter the same password once more for Windows Credential Manager:",
              f"cmdkey /generic:{state['credential']} /user:{ALIAS} /pass", ":end", "echo.",
              "echo Back up the keystore file somewhere safe (not in a repository). You can close this window.", "pause"]
    script = Path(tempfile.gettempdir()) / "release-desk-upload-key.cmd"
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return True, "Opened a console window; finish there, then Refresh."


# Listing ------------------------------------------------------------------------------------------------------

def listing(project):
    return project.read("play/listing.json", {}) or {}


def save_listing(project, fields):
    data = listing(project)
    for key in RULES["text"]:
        if key in fields:
            data[key] = str(fields[key]).strip()
    project.write("play/listing.json", data)
    return data


def _fields(project):
    text, rel = listing(project), release.effective(project, "play")
    out = [{"key": "title", "label": "Title (game name)", "value": rel["name"], "max": RULES["titleMax"], "readonly": True,
            "note": "From Release (game name; override it for Google Play there).",
            "problem": "" if rel["name"] and len(rel["name"]) <= RULES["titleMax"] else
            ("empty" if not rel["name"] else f"{len(rel['name'])} / {RULES['titleMax']} characters")}]
    for key, rule in RULES["text"].items():
        value = text.get(key, "")
        problem = "empty" if rule.get("required") and not value else (
            f"{len(value)} / {rule['max']} characters" if rule.get("max") and len(value) > rule["max"] else "")
        out.append({"key": key, "label": rule["label"], "value": value, "max": rule.get("max"), "multiline": rule.get("multiline", False),
                    "note": rule.get("note", ""), "problem": problem})
    return out


def _screenshots(project):
    rule = RULES["screenshots"]
    folder = project.store / rule["folder"]
    shots = []
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        dims = images.size(path)
        if not dims or dims[2] not in ("png", "jpg"):
            continue
        w, h, _ = dims
        ok = rule["minSide"] <= min(w, h) and max(w, h) <= rule["maxSide"] and max(w, h) <= 2 * min(w, h)
        shots.append({"file": path.name, "path": str(path), "size": f"{w}×{h}", "ok": ok})
    good = sum(s["ok"] for s in shots)
    return {"items": shots, "good": good, "min": rule["min"], "folder": rule["folder"], "note": rule["note"]}


def status(project):
    fields, art_items, shots = _fields(project), art.check(project, "play"), _screenshots(project)
    key, account, aab = key_state(project), playapi.account_state(), builds.latest(project, "play-aab")
    rel, play = release.effective(project, "play"), settings(project)
    notes_ok = len(rel["whatsNew"]) <= RULES["releaseNotesMax"]
    history = builds.history(project, "play-aab")
    steps = [
        {"title": "Play developer account", "state": "todo", "kind": "hand", "link": "https://play.google.com/console/signup",
         "detail": "Register once (one-time fee, identity checks). New personal accounts must run a closed test with testers before production."},
        {"title": "Android package", "state": "ok" if key["package"] else "todo", "kind": "hand",
         "detail": "Choose the application id (cannot change later) and put it in Store/store.json as android.package, then Push to Unity."},
        {"title": "Upload key", "state": "ok" if key["ready"] else "todo", "kind": "desk",
         "detail": f"Create upload key (Keys & accounts): keystore {key['keystore']}, password in Credential Manager as {key['credential']}. Play App Signing keeps the release key."},
        {"title": "Create the app in Play Console", "state": "todo", "kind": "hand", "link": "https://play.google.com/console",
         "detail": "The API cannot create apps. Create it by hand and upload the first release AAB there once. Releases go up as drafts until you set play.status to \"completed\" in Store/store.json."},
        {"title": "Service account", "state": "ok" if account["found"] else "todo", "kind": "hand",
         "link": "https://developers.google.com/android-publisher/getting_started",
         "detail": f"Create a service account in Google Cloud with the Play Android Developer API enabled, invite its email in Play Console > Users and permissions with release rights for this app, save its JSON key outside every repository and set {playapi.ENV} to its path."},
        {"title": "Store listing text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "desk",
         "detail": "Title, short and full description (Listing tab); uploaded with each publish."},
        {"title": "Store art", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "desk",
         "detail": "App icon and feature graphic (Make icons / Make capsules); uploaded with each publish."},
        {"title": "Phone screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "desk",
         "detail": f"{shots['good']} of at least {shots['min']} usable in Store/{shots['folder']} (add \"play\" to a shot's stores in Store/shots.json)."},
        {"title": "Release AAB", "state": "ok" if aab["exists"] else "todo", "kind": "desk",
         "detail": "Signed with the upload key (Builds tab)."},
        {"title": f"Upload to {play['track']}", "state": "ok" if any(h.get("uploaded") for h in history[:1]) else "todo", "kind": "desk",
         "detail": f"Bundle, release notes (What's new{'' if notes_ok else ', too long'}), listing and art in one edit on the {play['track']} track."},
        {"title": "Content rating, data safety, target audience", "state": "todo", "kind": "hand",
         "detail": "Questionnaires in Play Console; needed before any testing track goes out to testers."},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "key": key, "account": account, "aab": aab, "steps": steps,
            "play": play, "language": RULES["language"], "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project):
    s = status(project)
    lines = [f"Listing: {f['label']} {f['problem']}" for f in s["fields"] if f["problem"]]
    missing = [a["label"] for a in s["art"] if a["state"] == "missing"]
    if missing:
        lines.append("Play art missing: " + ", ".join(missing))
    lines.append(f"Play screenshots: {s['screenshots']['good']} of {s['screenshots']['min']} usable")
    lines.append(f"Upload key: {'ready' if s['key']['ready'] else 'missing'}; service account: {'found' if s['account']['found'] else 'missing'}")
    lines.append(f"Play: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open")
    return lines


# Publish ------------------------------------------------------------------------------------------------------

def publish(project, preview=True):
    """One edit: bundle, track release with notes, listing text, icon, feature graphic and phone screenshots.
    Preview validates the edit and then deletes it, so nothing changes in Play Console."""
    s = status(project)
    pkg, aab = s["key"]["package"], s["aab"]
    if not pkg:
        return False, "Set android.package in Store/store.json first."
    if not aab["exists"]:
        return False, "Build the release AAB first."
    problems = [f"{f['label']} {f['problem']}" for f in s["fields"] if f["problem"]]
    if problems:
        return False, "Fix the listing first: " + "; ".join(problems)
    rel, lang, play = release.effective(project, "play"), s["language"], s["play"]
    api = playapi.Play(pkg)
    edit = api.call("POST", "/edits", {})["id"]
    lines = []
    try:
        bundle = api.upload(f"/edits/{edit}/bundles", aab["path"], "application/octet-stream")
        code = str(bundle["versionCode"])
        lines.append(f"Bundle {Path(aab['path']).name}: version code {code}")
        notes = rel["whatsNew"][:RULES["releaseNotesMax"]]
        entry = {"versionCodes": [code], "status": play["status"], "name": f"{rel['version']} ({code})"}
        if notes:
            entry["releaseNotes"] = [{"language": lang, "text": notes}]
        api.call("PUT", f"/edits/{edit}/tracks/{play['track']}", {"track": play["track"], "releases": [entry]})
        lines.append(f"Track {play['track']}: {play['status']}")
        text = {f["key"]: f["value"] for f in s["fields"]}
        api.call("PUT", f"/edits/{edit}/listings/{lang}", {"language": lang, "title": text["title"],
                                                          "shortDescription": text["shortDescription"], "fullDescription": text["fullDescription"]})
        lines.append(f"Listing {lang}: title, short and full description")
        for item in s["art"]:
            kind = IMAGE_TYPES.get(Path(item["file"]).stem)
            if kind and item["state"] == "ok":
                api.call("DELETE", f"/edits/{edit}/listings/{lang}/{kind}")
                api.upload(f"/edits/{edit}/listings/{lang}/{kind}", project.store / item["file"], _mime(item["file"]))
                lines.append(f"Image {kind}: {item['file']}")
        shots = [x for x in s["screenshots"]["items"] if x["ok"]][:RULES["screenshots"]["max"]]
        if shots:
            api.call("DELETE", f"/edits/{edit}/listings/{lang}/phoneScreenshots")
            for shot in shots:
                api.upload(f"/edits/{edit}/listings/{lang}/phoneScreenshots", shot["path"], _mime(shot["file"]))
            lines.append(f"Phone screenshots: {len(shots)}")
        api.call("POST", f"/edits/{edit}:validate")
        lines.append("Validated by Play")
        if preview:
            api.call("DELETE", f"/edits/{edit}")
            lines.append("Preview: edit deleted, nothing changed in Play Console")
            return True, "\n".join(lines)
        api.call("POST", f"/edits/{edit}:commit")
    except Exception:
        try:
            api.call("DELETE", f"/edits/{edit}")
        except Exception:  # the edit expires on its own
            pass
        raise
    builds.mark_uploaded(project, "play-aab", play["track"])
    lines.append(f"Committed: {play['track']} track")
    return True, "\n".join(lines)


def _mime(name):
    return "image/jpeg" if str(name).lower().endswith(".jpg") else "image/png"
