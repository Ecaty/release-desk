"""Google Play Developer API (androidpublisher v3) over urllib, signed in with a service account.

The service account JSON stays outside every repository; its path is in PLAY_SERVICE_ACCOUNT_JSON. The OAuth token
request needs an RS256 signature, made here with Python's integers (no packages). Nothing secret is logged."""
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/androidpublisher"
API = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications/"
UPLOAD = "https://androidpublisher.googleapis.com/upload/androidpublisher/v3/applications/"
ENV = "PLAY_SERVICE_ACCOUNT_JSON"
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


# RSA signing ------------------------------------------------------------------------------------------------

def _der(data, pos):
    """One DER element at pos: (tag, content, next position)."""
    tag, length = data[pos], data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    return tag, data[pos:pos + length], pos + length


def _sequence(data):
    items, pos = [], 0
    while pos < len(data):
        tag, content, pos = _der(data, pos)
        items.append((tag, content))
    return items


def private_key(pem):
    """(n, d) from a PEM 'PRIVATE KEY' (PKCS#8) or 'RSA PRIVATE KEY' (PKCS#1)."""
    lines = [l.strip() for l in pem.strip().splitlines()]
    body = base64.b64decode("".join(l for l in lines if l and not l.startswith("-----")))
    _, outer, _ = _der(body, 0)
    items = _sequence(outer)
    if len(items) >= 3 and items[1][0] == 0x30 and items[2][0] == 0x04:  # PKCS#8 wraps the PKCS#1 key
        _, outer, _ = _der(items[2][1], 0)
        items = _sequence(outer)
    numbers = [int.from_bytes(content, "big") for tag, content in items if tag == 0x02]
    if len(numbers) < 4:
        raise ValueError("not an RSA private key")
    return numbers[1], numbers[3]


def sign_rs256(message, key):
    """RSASSA-PKCS1-v1_5 with SHA-256."""
    n, d = key
    size = (n.bit_length() + 7) // 8
    digest = _SHA256_PREFIX + hashlib.sha256(message).digest()
    block = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    return pow(int.from_bytes(block, "big"), d, n).to_bytes(size, "big")


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


# Key file location ------------------------------------------------------------------------------------------

def _user_variable():
    """The Windows user variable, so a path set after the desk started counts without a restart."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, ENV)[0])
    except (ImportError, OSError):
        return ""


def key_path():
    return os.environ.get(ENV, "") or _user_variable()


def _in_repository(path):
    return any((parent / ".git").exists() for parent in Path(path).resolve().parents)


def check_key_file(path):
    """Why a chosen file can't be the service account key, or "" when it can. Only the file's type is checked."""
    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".json":
        return "Pick the .json file Google downloaded."
    if _in_repository(p):
        return "That file is inside a project folder. Move it to a folder of its own (e.g. Documents\\keys) and pick it there."
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "That file can't be read as a key file."
    if not isinstance(data, dict) or data.get("type") != "service_account" or not data.get("private_key"):
        return "That isn't a service account key file. Make one on desk-upload's Keys tab (JSON)."
    return ""


def save_key_path(path):
    """Remembers where the key file is: the Windows user variable (for later desk starts) and this desk process."""
    import winreg
    path = str(Path(path).resolve())
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, ENV, 0, winreg.REG_SZ, path)
    os.environ[ENV] = path
    return path


# Session ----------------------------------------------------------------------------------------------------

def account_state():
    """What the desk may show: whether the path is set and readable, and the service account's email (not secret)."""
    path = key_path()
    state = {"env": ENV, "set": bool(path), "found": False, "email": ""}
    if path and Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            state["found"] = data.get("type") == "service_account" and bool(data.get("private_key"))
            state["email"] = data.get("client_email", "")
        except (OSError, ValueError):
            pass
    return state


class Play:
    def __init__(self, package):
        path = key_path()
        if not path or not Path(path).is_file():
            raise ValueError(f"Set {ENV} to the service account JSON file (outside every repository).")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.package = package
        self._email, self._token_uri = data["client_email"], data.get("token_uri", "https://oauth2.googleapis.com/token")
        self._key = private_key(data["private_key"])
        self._token, self._expires = "", 0

    def _bearer(self):
        if time.time() < self._expires - 60:
            return self._token
        now = int(time.time())
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": self._email, "scope": SCOPE, "aud": self._token_uri, "iat": now, "exp": now + 3600}).encode())
        unsigned = header + b"." + claims
        assertion = (unsigned + b"." + _b64(sign_rs256(unsigned, self._key))).decode()
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}).encode()
        reply = self._send(urllib.request.Request(self._token_uri, data=body, method="POST",
                                                  headers={"Content-Type": "application/x-www-form-urlencoded"}), auth=False)
        self._token, self._expires = reply["access_token"], now + int(reply.get("expires_in", 3600))
        return self._token

    def _send(self, request, auth=True, timeout=120):
        if auth:
            request.add_header("Authorization", "Bearer " + self._bearer())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                text = reply.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("error", {}).get("message", detail) if auth else json.loads(detail).get("error_description", detail)
            except (ValueError, AttributeError):
                pass
            raise RuntimeError(f"Play API {error.code}: {str(detail)[:300]}") from None
        return json.loads(text) if text.strip() else {}

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(API + self.package + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"} if data else {})
        return self._send(request)

    def upload(self, path, file, kind):
        size = Path(file).stat().st_size
        with open(file, "rb") as f:
            request = urllib.request.Request(UPLOAD + self.package + path + "?uploadType=media", data=f, method="POST",
                                             headers={"Content-Type": kind, "Content-Length": str(size)})
            return self._send(request, timeout=3600)
