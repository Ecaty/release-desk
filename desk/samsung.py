"""Samsung Galaxy Store: the same release AAB as Google Play, submitted through the Galaxy Store Developer API
(Content Publish API).

No Samsung device is needed: Samsung reviews the app on its own devices (Remote Test Lab is there for checks). The
first registration of the app is done by hand in Seller Portal (the API cannot register new apps). The service
account's private key stays outside every repository (path in SAMSUNG_SERVICE_ACCOUNT_KEY); the desk signs the token
request with it using its own RS256 code and never shows it."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import art, builds, jobs, playapi, release

RULES = art.rules("samsung")
API = "https://devapi.samsungapps.com"
ENV = "SAMSUNG_SERVICE_ACCOUNT_KEY"


def settings(project):
    data = (project.read("store.json", {}) or {}).get("samsung", {}) or {}
    return {"contentId": str(data.get("contentId", "")), "serviceAccountId": str(data.get("serviceAccountId", "")),
            "gms": data.get("gms", ""), "language": data.get("language", "ENG")}


def key_state(project):
    path = os.environ.get(ENV, "")
    found = False
    if path and Path(path).is_file():
        try:
            playapi.private_key(Path(path).read_text(encoding="utf-8"))
            found = True
        except (OSError, ValueError, IndexError):
            found = False
    s = settings(project)
    return {"env": ENV, "set": bool(path), "found": found, "contentId": s["contentId"], "serviceAccountId": s["serviceAccountId"],
            "ready": found and bool(s["contentId"]) and bool(s["serviceAccountId"])}


class _Multipart:
    """Streams a multipart/form-data body (sessionId field + one file) without reading the file into memory."""

    def __init__(self, fields, name, path):
        self.boundary = uuid.uuid4().hex
        head = b"".join(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
        head += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{Path(path).name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n").encode()
        self.parts = [head, None, f"\r\n--{self.boundary}--\r\n".encode()]
        self.file = open(path, "rb")
        self.length = len(head) + Path(path).stat().st_size + len(self.parts[2])
        self.index = 0

    def read(self, size=-1):
        while self.index < 3:
            if self.index == 1:
                chunk = self.file.read(size if size and size > 0 else 1 << 20)
                if chunk:
                    return chunk
                self.file.close()
                self.index = 2
                continue
            part = self.parts[self.index]
            self.index += 1
            return part
        return b""


class Galaxy:
    def __init__(self, project):
        s = settings(project)
        path = os.environ.get(ENV, "")
        if not path or not Path(path).is_file():
            raise ValueError(f"Set {ENV} to the Galaxy Store service account private key file (outside every repository).")
        self.account = s["serviceAccountId"]
        key = playapi.private_key(Path(path).read_text(encoding="utf-8"))
        now = int(time.time())
        header = playapi._b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = playapi._b64(json.dumps({"iss": self.account, "scopes": ["publishing"], "iat": now, "exp": now + 1200}).encode())
        unsigned = header + b"." + claims
        jwt = (unsigned + b"." + playapi._b64(playapi.sign_rs256(unsigned, key))).decode()
        reply = self._send("POST", API + "/auth/accessToken", headers={"Authorization": "Bearer " + jwt, "content-type": "application/json"})
        self.token = reply["createdItem"]["accessToken"]

    def _send(self, method, url, body=None, headers=None, timeout=120):
        request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                text = reply.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise RuntimeError(f"Galaxy Store API {error.code}: {detail[:300]}") from None
        return json.loads(text) if text.strip() else {}

    def _auth(self, extra=None):
        return {"Authorization": "Bearer " + self.token, "service-account-id": self.account, **(extra or {})}

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        return self._send(method, API + path, data, self._auth({"content-type": "application/json"} if data else {}))

    def upload(self, path):
        session = self.call("POST", "/seller/createUploadSessionId")
        body = _Multipart({"sessionId": session["sessionId"]}, "file", path)
        headers = self._auth({"Content-Type": f"multipart/form-data; boundary={body.boundary}", "Content-Length": str(body.length)})
        reply = self._send("POST", session.get("url") or "https://seller.samsungapps.com/galaxyapi/fileUpload", body, headers, timeout=6 * 3600)
        if not reply.get("fileKey"):
            raise RuntimeError(f"Galaxy Store upload failed: {reply.get('errorMsg') or reply}")
        return reply["fileKey"]


def _info(api, content_id):
    data = api.call("GET", f"/seller/contentInfo?contentId={content_id}")
    items = data if isinstance(data, list) else [data]
    if not items or not items[0]:
        raise RuntimeError("Galaxy Store returned no app information for this content ID.")
    return items[0]


def status(project):
    key, aab, s = key_state(project), builds.latest(project, "play-aab"), settings(project)
    art_items = art.check(project, "samsung")
    history = builds.history(project, "play-aab")
    seller = "https://seller.samsungapps.com/"
    steps = [
        {"title": "Seller Portal account", "state": "ok" if s["contentId"] else "todo", "kind": "hand", "link": seller,
         "detail": "Register a free Galaxy Store seller account (no Samsung device needed)."},
        {"title": "Register the app by hand", "state": "ok" if s["contentId"] else "todo", "kind": "hand", "link": seller, "go": "keys//ids-samsung-contentId",
         "detail": "Add the app once in Seller Portal with the release AAB, store listing, screenshots, age rating and countries; choose Galaxy Store's signing key or your own. Then put its 12-digit content ID in Keys & accounts."},
        {"title": "Service account", "state": "ok" if key["found"] and s["serviceAccountId"] else "todo", "kind": "hand", "go": "keys//ids-samsung-serviceAccountId",
         "link": "https://developer.samsung.com/galaxy-store/galaxy-store-developer-api/create-an-access-token.html",
         "detail": f"Seller Portal > Assistance > API Service > Create Service Account (Publishing & ITEM). Save the private key outside every repository, set {ENV} to its path and put the service account ID in Keys & accounts."},
        {"title": "App icon", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy", "go": "samsung/listing/samsung-art",
         "detail": "512×512 icon (Make icons); listing images are kept in Seller Portal."},
        {"title": "Release AAB", "state": "ok" if aab["exists"] else "todo", "kind": "desk", "go": "play/builds/play-builds",
         "detail": "The same signed AAB as Google Play (Google Play > Builds). Galaxy Store makes a universal APK from it; Play Asset Delivery is not supported."},
        {"title": "Submit update", "state": "ok" if any(h.get("galaxy") for h in history[:1]) else "todo", "kind": "desk",
         "go": "samsung/builds/samsung-upload",
         "detail": "Uploads the AAB as a new binary (device targeting copied from the previous one), What's new as the update notes, then submits for Samsung's review."},
    ]
    return {"art": art_items, "aab": aab, "key": key, "steps": steps, "history": history,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project):
    s = status(project)
    return [f"Galaxy Store: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open"]


def check(project):
    """Signs in and reads the app's status in Galaxy Store. Changes nothing."""
    key = key_state(project)
    if not key["ready"]:
        return False, "Finish the Galaxy Store setup first (Keys & accounts)."
    api = Galaxy(project)
    info = _info(api, key["contentId"])
    binaries = info.get("binaryList") or []
    last = binaries[-1] if binaries else {}
    return True, (f"{info.get('appTitle', '')}: status {info.get('contentStatus', '?')}, {len(binaries)} binaries"
                  + (f"; newest version {last.get('versionName', '?')} (code {last.get('versionCode', '?')})" if last else ""))


def submit(project):
    key, aab = key_state(project), builds.latest(project, "play-aab")
    if not key["ready"]:
        return False, "Finish the Galaxy Store setup first (Keys & accounts)."
    if not aab["exists"]:
        return False, "Build the release AAB first (Google Play > Builds)."
    s, rel = settings(project), release.effective(project, "samsung")
    api = Galaxy(project)
    lines = []
    file_key = api.upload(aab["path"])
    lines.append(f"Uploaded {Path(aab['path']).name}")
    jobs.check()
    info = _info(api, s["contentId"])
    binaries = info.get("binaryList") or []
    last = binaries[-1] if binaries else {}
    update = {"contentId": s["contentId"], "defaultLanguageCode": info.get("defaultLanguageCode") or s["language"],
              "paid": info.get("paid", "N"), "publicationType": info.get("publicationType", "01"), "appTitle": info.get("appTitle", rel["name"]),
              "newFeature": rel["whatsNew"][:4000], "addLanguage": "null", "screenshots": "null", "sellCountryList": "null"}
    api.call("POST", "/seller/contentUpdate", update)
    lines.append("Update opened")
    jobs.check()
    gms = s["gms"] or last.get("gms") or "N"
    binary = {"contentId": s["contentId"], "gms": gms, "filekey": file_key}
    if last.get("binarySeq"):
        binary["binarySeqForDeviceInfo"] = str(last["binarySeq"])
    api.call("POST", "/seller/v2/content/binary", binary)
    lines.append("New binary registered" + (f" (devices from binary {last['binarySeq']})" if last.get("binarySeq") else ""))
    jobs.check()
    api.call("POST", "/seller/contentSubmit", {"contentId": s["contentId"]})
    builds.mark_uploaded(project, "play-aab", "in review", field="galaxy")
    lines.append("Submitted for Samsung's review")
    return True, "\n".join(lines)
