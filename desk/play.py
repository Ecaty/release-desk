"""Google Play: upload key, listing checks, and publishing an App Bundle with its listing through the Play Developer API.

Secrets never pass through the desk: keytool and cmdkey ask for the upload key password in their own console window,
Unity reads it from Windows Credential Manager during the release build, and the service account JSON is only read
from the path in PLAY_SERVICE_ACCOUNT_JSON to sign the token request."""
import os
import subprocess
import tempfile
from pathlib import Path

from . import art, builds, images, jobs, playapi, release

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


TRACKS = {"internal": "Internal testing", "alpha": "Closed testing", "beta": "Open testing", "production": "Production"}
STATUSES = {"draft": "Draft (finish in Play Console)", "completed": "Roll out"}


def save_settings(project, track, status):
    if track not in TRACKS or status not in STATUSES:
        raise ValueError("Unknown track or status")
    data = project.read("store.json", {}) or {}
    data.setdefault("play", {}).update({"track": track, "status": status})
    project.write("store.json", data)


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
    for key, rule in RULES["text"].items():
        if key in fields and not rule.get("from"):
            data[key] = str(fields[key]).strip()
    project.write("play/listing.json", data)
    return data


def _fields(project):
    text, rel = listing(project), release.effective(project, "play")
    out = [{"key": "title", "label": "Title (game name)", "value": rel["name"], "max": RULES["titleMax"], "readonly": True,
            "note": "From Release (game name; override it for Google Play there).",
            "problem": "" if rel["name"] and len(rel["name"]) <= RULES["titleMax"] else
            ("empty" if not rel["name"] else f"{len(rel['name'])} / {RULES['titleMax']} characters")}]
    out.extend(release.text_fields(project, "play", RULES, text))
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


TESTING_RULE = "https://support.google.com/googleplay/android-developer/answer/14151465"
PLAY_HELP = "https://support.google.com/googleplay/android-developer"

CONSOLE = "https://play.google.com/console"
CLOUD = "https://console.cloud.google.com"

# Each guide: the direct link first, then at most 4 short clicks. Labels as Google showed them in Nov 2026.
ACCOUNT_GUIDE = [
    {"text": "Sign in with the Google account you will publish with.", "link": CONSOLE + "/signup"},
    {"text": "Scroll down to Yourself, press Get started. Type developer name, email, phone; answer the questions."},
    {"text": "Pay US$25 by card, then upload a photo of your ID."},
    {"text": "On your Android phone: install Play Console, sign in.", "link": "https://play.google.com/store/apps/details?id=com.google.android.apps.playconsole"},
]

CREATE_APP_GUIDE = [
    {"text": "Press Create app.", "link": CONSOLE},
    {"text": "Type the game name and the package name (Keys & accounts shows it; it can never change). Press Check availability."},
    {"text": "Pick Game and Free. Tick the three boxes."},
    {"text": "Press Create app."},
]

CLOUD_PROJECT_GUIDE = [
    {"text": "Project name: e.g. tunu-play. Leave No organization. Press Create.", "link": CLOUD + "/projectcreate"},
    {"text": "Wait until the bell (top right) says it's created."},
    {"text": "Open this page, check your project is shown at the top, press Enable.", "link": CLOUD + "/apis/library/androidpublisher.googleapis.com"},
]

KEY_FILE_GUIDE = [
    {"text": "Press + Create service account. Name: desk-upload. Create and continue, Continue, Done.", "link": CLOUD + "/iam-admin/serviceaccounts"},
    {"text": "Click desk-upload > Keys tab > Add key > Create new key > JSON > Create."},
    {"text": "Move the downloaded file into a folder outside every project (e.g. Documents > keys). Never send it to anyone."},
]

INVITE_GUIDE = [
    {"text": "Copy the desk-upload address from the Email column (ends in iam.gserviceaccount.com).", "link": CLOUD + "/iam-admin/serviceaccounts"},
    {"text": "Press Invite new users, paste the address. Leave both switches off.", "link": CONSOLE + "/developers/users-and-permissions"},
    {"text": "Give permissions for specific apps > Add app > your game > Apply. Tick Release to testing tracks > Apply."},
    {"text": "Press Invite user at the bottom."},
]

APP_CONTENT_GUIDE_1 = [
    {"text": "Open your game, then in the left menu: Monitor and improve > Policy and programs > App content.", "link": CONSOLE},
    {"text": "Privacy policy: paste the web address of your privacy policy, Save."},
    {"text": "Ads: No (the game shows no ads), Save."},
]

APP_CONTENT_GUIDE_2 = [
    {"text": "Same App content page: Content rating > Start, answer for what the game contains, Submit.", "link": CONSOLE},
    {"text": "Target audience: pick the ages, Save. Under 13 adds the Families rules.", "link": PLAY_HELP + "/answer/9893335"},
    {"text": "Data safety: only data that leaves the phone counts. Save."},
]

TESTERS_GUIDE = [
    {"text": "Open your game, then Test and release > Testing > Closed testing. Press Manage track on Closed testing - Alpha.", "link": CONSOLE},
    {"text": "Testers tab > Create email list: name it, add 12 or more emails, Save changes."},
    {"text": "Tick the list, Save changes."},
]

FIRST_RELEASE_GUIDE = [
    {"text": "In the desk: set Track to Closed testing, Save. Later uploads then go there by themselves.", "go": "play/builds/play-publish"},
    {"text": "Same Closed testing - Alpha track > Releases tab > Create new release: upload the AAB from Builds, Next, Save.", "link": CONSOLE},
    {"text": "Left menu: Publishing overview > Send for review. Testers get it once Google approves."},
]

PRODUCTION_GUIDE = [
    {"text": "After 14 days with 12 or more testers: open your game's Dashboard, press Apply for production.", "link": CONSOLE},
    {"text": "Answer the three parts of the form, press Apply."},
]


def status(project):
    fields, art_items, shots = _fields(project), art.check(project, "play"), _screenshots(project)
    key, account, aab = key_state(project), playapi.account_state(), builds.latest(project, "play-aab")
    rel, play = release.effective(project, "play"), settings(project)
    notes_ok = len(rel["whatsNew"]) <= RULES["releaseNotesMax"]
    history = builds.history(project, "play-aab")
    steps = [
        {"title": "Play developer account", "state": "todo", "kind": "hand", "link": CONSOLE + "/signup",
         "detail": "Once: US$25 and an ID check. New personal accounts need a 14-day closed test with 12 testers before going public.",
         "guide": ACCOUNT_GUIDE},
        {"title": "Android package", "go": "play/keys/ids-play-package", "state": "ok" if key["package"] else "todo", "kind": "hand",
         "detail": "The game's permanent id, e.g. com.tunu.christmas. Type it in Keys & accounts, then Push to Unity."},
        {"title": "Upload key", "go": "play/keys/play-key", "state": "ok" if key["ready"] else "todo", "kind": "desk",
         "detail": f"Press Create upload key in Keys & accounts. Keystore {key['keystore']}; its password stays in Credential Manager."},
        {"title": "Create the app in Play Console", "state": "todo", "kind": "hand", "link": CONSOLE,
         "detail": "Once, by hand: Google's API can't create apps.", "guide": CREATE_APP_GUIDE},
        {"title": "Google Cloud project", "state": "todo", "kind": "hand", "link": CLOUD + "/projectcreate",
         "detail": "Needed so the desk may upload. Free.", "guide": CLOUD_PROJECT_GUIDE},
        {"title": "Service account key file", "state": "todo", "kind": "hand", "link": CLOUD + "/iam-admin/serviceaccounts",
         "detail": "The desk's own login for uploads. You keep the file.", "guide": KEY_FILE_GUIDE},
        {"title": "Invite the service account in Play Console", "state": "todo", "kind": "hand", "link": CONSOLE + "/developers/users-and-permissions",
         "detail": "Lets it upload test releases of this game only.", "guide": INVITE_GUIDE},
        {"title": "Service account", "go": "play/keys/play-account", "state": "ok" if account["found"] else "todo", "kind": "hand",
         "detail": "Tell the desk where the key file is.",
         "guide": [{"text": f"In PowerShell, with your file's path: [Environment]::SetEnvironmentVariable('{playapi.ENV}', 'C:\\path\\to\\file.json', 'User')"},
                   {"text": "Tell Release Desk on the board; it restarts the desk. Keys & accounts then shows found.", "go": "play/keys/play-account"}]},
        {"title": "Store listing text", "go": "play/listing/play-text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "desk",
         "detail": "Title, short and full description (Listing tab); uploaded with each publish."},
        {"title": "Store art", "go": "play/listing/play-art", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "desk",
         "detail": "App icon and feature graphic (Make icons / Make capsules); uploaded with each publish."},
        {"title": "Phone screenshots", "go": "play/listing/play-shots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "desk",
         "detail": f"{shots['good']} of at least {shots['min']} usable in Store/{shots['folder']} (add \"play\" to a shot's stores in Store/shots.json)."},
        {"title": "Release AAB", "go": "play/builds/play-builds", "state": "ok" if aab["exists"] else "todo", "kind": "desk",
         "detail": "Press Build release AAB (Builds tab). Signed with the upload key."},
        {"title": "App content: privacy policy and ads", "state": "todo", "kind": "hand", "link": CONSOLE,
         "detail": "Google won't review a release without these.", "guide": APP_CONTENT_GUIDE_1},
        {"title": "App content: rating, audience, data safety", "state": "todo", "kind": "hand", "link": CONSOLE,
         "detail": "Three short questionnaires.", "guide": APP_CONTENT_GUIDE_2},
        {"title": "Closed test: testers", "state": "todo", "kind": "hand", "link": CONSOLE,
         "detail": "12 or more people with a Google account, for 14 days in a row. Invite a few extra.", "guide": TESTERS_GUIDE},
        {"title": "Closed test: first release", "state": "todo", "kind": "hand", "link": CONSOLE,
         "detail": "The first AAB goes up by hand once; the desk uploads the next ones.", "guide": FIRST_RELEASE_GUIDE},
        {"title": f"Upload to {TRACKS.get(play['track'], play['track'])}", "go": "play/builds/play-publish", "state": "ok" if any(h.get("uploaded") for h in history[:1]) else "todo", "kind": "desk",
         "detail": f"Press Publish (Builds tab): the AAB, release notes, listing and art in one go{'' if notes_ok else '; What’s new is too long'}."},
        {"title": "Apply for production", "state": "todo", "kind": "hand", "link": TESTING_RULE,
         "detail": "After the 14-day closed test. Then the game can go public.", "guide": PRODUCTION_GUIDE},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "key": key, "account": account, "aab": aab, "steps": steps,
            "play": play, "tracks": TRACKS, "statuses": STATUSES, "language": RULES["language"], "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


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
        notes = release_notes(project, aab["path"])
        entry = {"versionCodes": [code], "status": play["status"], "name": f"{rel['version']} ({code})"}
        if notes:
            entry["releaseNotes"] = [{"language": lang, "text": notes}]
        jobs.check()
        api.call("PUT", f"/edits/{edit}/tracks/{play['track']}", {"track": play["track"], "releases": [entry]})
        lines.append(f"Track {play['track']}: {play['status']}")
        text = {f["key"]: f["value"] for f in s["fields"]}
        jobs.check()
        api.call("PUT", f"/edits/{edit}/listings/{lang}", {"language": lang, "title": text["title"],
                                                          "shortDescription": text["shortDescription"], "fullDescription": text["fullDescription"]})
        lines.append(f"Listing {lang}: title, short and full description")
        jobs.check()
        for item in s["art"]:
            kind = IMAGE_TYPES.get(Path(item["file"]).stem)
            if kind and item["state"] == "ok":
                api.call("DELETE", f"/edits/{edit}/listings/{lang}/{kind}")
                api.upload(f"/edits/{edit}/listings/{lang}/{kind}", project.store / item["file"], _mime(item["file"]))
                lines.append(f"Image {kind}: {item['file']}")
        jobs.check()
        shots = [x for x in s["screenshots"]["items"] if x["ok"]][:RULES["screenshots"]["max"]]
        if shots:
            api.call("DELETE", f"/edits/{edit}/listings/{lang}/phoneScreenshots")
            for shot in shots:
                api.upload(f"/edits/{edit}/listings/{lang}/phoneScreenshots", shot["path"], _mime(shot["file"]))
            lines.append(f"Phone screenshots: {len(shots)}")
        jobs.check()
        api.call("POST", f"/edits/{edit}:validate")
        lines.append("Validated by Play")
        if preview:
            api.call("DELETE", f"/edits/{edit}")
            lines.append("Preview: edit deleted, nothing changed in Play Console")
            return True, "\n".join(lines)
        jobs.check()
        api.call("POST", f"/edits/{edit}:commit")
    except Exception:
        try:
            api.call("DELETE", f"/edits/{edit}")
        except Exception:  # the edit expires on its own
            pass
        raise
    builds.mark_uploaded(project, "play-aab", play["track"])
    lines.append(f"Committed: {play['track']} track")
    lines.append(f"Build number raised to {release.bump_build(project, 'play')} for the next upload")
    return True, "\n".join(lines)


def check(project):
    """Read-only: what each track holds in Play Console (opens an edit, reads the tracks, deletes the edit)."""
    pkg = package(project)
    if not pkg:
        return False, "Set android.package in Store/store.json first."
    api = playapi.Play(pkg)
    edit = api.call("POST", "/edits", {})["id"]
    try:
        tracks = api.call("GET", f"/edits/{edit}/tracks").get("tracks", [])
    finally:
        api.call("DELETE", f"/edits/{edit}")
    lines, highest = [], 0
    for track in tracks:
        for rel in track.get("releases", []):
            codes = [int(c) for c in rel.get("versionCodes", [])]
            highest = max([highest] + codes)
            lines.append(f"{TRACKS.get(track['track'], track['track'])}: {rel.get('name', '')} codes {', '.join(map(str, codes)) or '-'} ({rel.get('status', '')})")
    build = release.effective(project, "play")["build"]
    lines.append(f"Highest version code on Play: {highest or 'none'}; next AAB uses build number {build}"
                 + ("" if build > highest else " - raise it above the highest code before building"))
    return True, "\n".join(lines) or "No releases on any track yet."


def release_notes(project, aab_path):
    """The notes recorded with this AAB when it was built (What's new, or its Release-note lines), as a list Play
    accepts: whole lines only, at most 500 characters."""
    entry = next((h for h in builds.history(project, "play-aab") if h.get("path") == str(aab_path)), {})
    lines = entry.get("changes") or release.changes(release.effective(project, "play")["whatsNew"])
    text = ""
    for line in lines:
        candidate = (text + "\n" if text else "") + "• " + line
        if len(candidate) > RULES["releaseNotesMax"]:
            break
        text = candidate
    return text


def _mime(name):
    return "image/jpeg" if str(name).lower().endswith(".jpg") else "image/png"
