"""Epic Games Store: listing and art checks, Windows build upload through Epic's BuildPatch Tool (BPT).

The store page has no public API (copy each value into the Developer Portal). Uploads go to the product's Dev
sandbox; attaching the binary to the artifact's platform and promoting it are done in the Developer Portal.
The BPT client secret lives in Windows Credential Manager. A PowerShell helper reads it into an environment variable
of the BPT process only (BPT's -ClientSecretEnvVar), so this Python process never holds it."""
import re
import subprocess
from pathlib import Path

from . import art, builds, images, jobs, release
from .project import CONFIG_DIR

RULES = art.rules("epic")
BPT_DIR = CONFIG_DIR / "BuildPatchTool"
SECRET_ENV = "RELEASE_DESK_BPT_SECRET"
IDS = (("organizationId", "Organization ID"), ("productId", "Product ID"), ("artifactId", "Artifact ID"), ("clientId", "BPT client ID"))
IGNORE = ['W"*.pdb"', 'W"*_BurstDebugInformation_DoNotShip/*"', 'W"*_BackUpThisFolder_ButDontShipItWithYourGame/*"', 'W"*DoNotShip*"']

# Reads a generic credential with CredRead (same code as the Unity package) and runs BPT with it in one env var.
_RUNNER = r'''
param([string]$Target, [string]$Exe, [string]$ArgFile, [string]$EnvName)
$ErrorActionPreference = "Stop"
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public static class DeskCred {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  struct Credential { public int Flags; public int Type; public string TargetName; public string Comment;
    public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten; public int CredentialBlobSize; public IntPtr CredentialBlob;
    public int Persist; public int AttributeCount; public IntPtr Attributes; public string TargetAlias; public string UserName; }
  [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
  static extern bool CredRead(string target, int type, int flags, out IntPtr credential);
  [DllImport("advapi32.dll")] static extern void CredFree(IntPtr buffer);
  public static string Read(string target) {
    IntPtr handle; if (!CredRead(target, 1, 0, out handle)) return null;
    try { var c = (Credential)Marshal.PtrToStructure(handle, typeof(Credential));
      return c.CredentialBlobSize > 0 ? Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2) : null; }
    finally { CredFree(handle); } }
}
"@
$secret = [DeskCred]::Read($Target)
if (-not $secret) { Write-Output "ERROR: no BPT client secret in Credential Manager ($Target)."; exit 3 }
[Environment]::SetEnvironmentVariable($EnvName, $secret, "Process")
$secret = $null
$arguments = Get-Content -LiteralPath $ArgFile -Encoding UTF8
& $Exe @arguments 2>&1 | ForEach-Object { "$_" }
exit $LASTEXITCODE
'''


def settings(project):
    return ((project.read("store.json", {}) or {}).get("epic", {}) or {})


def bpt():
    found = sorted(BPT_DIR.glob("**/BuildPatchTool.exe"))
    return found[0] if found else None


def credential(project):
    return f"release-desk/epic/{settings(project).get('productId') or 'product'}/bpt-secret"


def key_state(project):
    data, target = settings(project), credential(project)
    stored = False
    try:
        out = subprocess.run(["cmdkey", f"/list:{target}"], capture_output=True, text=True, timeout=15).stdout
        stored = any(l.strip().lower().startswith("target:") and target.lower() in l.lower() for l in out.splitlines())
    except (OSError, subprocess.SubprocessError):
        pass
    exe = bpt()
    missing = [label for key, label in IDS if not data.get(key)]
    return {"bpt": str(exe or ""), "bptFolder": str(BPT_DIR), "installed": bool(exe), "ids": {k: data.get(k, "") for k, _ in IDS},
            "missing": missing, "credential": target, "stored": stored, "ready": bool(exe) and not missing and stored}


def save_secret(project):
    """Console where cmdkey asks for the BPT client secret; the desk never sees it."""
    state = key_state(project)
    if not state["ids"]["productId"] or not state["ids"]["clientId"]:
        return False, "Put productId and clientId under \"epic\" in Store/store.json first."
    lines = ["@echo off", "title Epic BPT client secret", "echo Paste the BPT client secret from the Developer Portal (Product Settings > BPT credentials).",
             "echo Release Desk never sees it.", "echo.", f"cmdkey /generic:{state['credential']} /user:{state['ids']['clientId']} /pass", "echo.", "pause"]
    script = CONFIG_DIR / "epic-secret.cmd"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return True, "Opened a console window; paste the secret there, then Refresh."


# Listing ------------------------------------------------------------------------------------------------------

def listing(project):
    return project.read("epic/listing.json", {}) or {}


def save_listing(project, fields):
    data = listing(project)
    for key, rule in RULES["text"].items():
        if key in fields and not rule.get("from"):
            data[key] = str(fields[key]).strip()
    project.write("epic/listing.json", data)
    return data


def _fields(project):
    text, rel = listing(project), release.effective(project, "epic")
    out = [{"key": "name", "label": "Product name", "value": rel["name"], "readonly": True,
            "note": "From Release (game name; override it for Epic there).", "problem": "" if rel["name"] else "empty"}]
    out.extend(release.text_fields(project, "epic", RULES, text))
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
        ok = (w, h) == (rule["width"], rule["height"]) and path.stat().st_size <= 4 * 1048576
        shots.append({"file": path.name, "size": f"{w}×{h}", "ok": ok})
    good = sum(s["ok"] for s in shots)
    return {"items": shots, "good": good, "min": rule["min"], "recommended": rule["recommended"], "folder": rule["folder"], "note": rule["note"]}


def _build(project):
    info = builds.latest(project, "epic-windows")
    info["folder"] = info["path"]
    info["history"] = builds.history(project, "epic-windows")
    return info


def status(project):
    fields, art_items, shots, build, key = _fields(project), art.check(project, "epic"), _screenshots(project), _build(project), key_state(project)
    portal = "https://dev.epicgames.com/portal"
    steps = [
        {"title": "Epic developer organization and product", "go": "epic/keys/ids-epic-organizationId", "state": "ok" if key["ids"]["productId"] else "todo", "kind": "hand", "link": portal,
         "detail": "Create the organization (one-time submission fee) and the product in the Developer Portal, then put organizationId, productId and artifactId under \"epic\" in Store/store.json."},
        {"title": "BuildPatch Tool", "go": "epic/keys/epic-bpt", "state": "ok" if key["installed"] else "todo", "kind": "hand", "link": portal,
         "detail": f"Developer Portal > your product > Epic Games Store > Artifacts and Binaries > Download build patch tool, and unzip it into {key['bptFolder']}."},
        {"title": "BPT credentials", "go": "epic/keys/epic-secret", "state": "ok" if key["ids"]["clientId"] and key["stored"] else "todo", "kind": "desk",
         "detail": "Product Settings > BPT credentials: put the client ID under \"epic\" in Store/store.json, then Save BPT secret (Keys & accounts) stores the secret in Credential Manager."},
        {"title": "Store page text", "go": "epic/listing/epic-text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy",
         "detail": "Paste the Listing fields into the Developer Portal (Store Settings and Pages)."},
        {"title": "Store art", "go": "epic/listing/epic-art", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy",
         "detail": "Product logo in Store Settings; offer images (general and library, landscape and portrait) in Offers; from Store/epic/art."},
        {"title": "Media carousel", "go": "epic/listing/epic-shots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy",
         "detail": f"{shots['good']} usable 1920×1080 screenshots in Store/{shots['folder']} (at least {shots['min']}; Epic recommends {shots['recommended']} and a video)."},
        {"title": "Windows build", "go": "epic/builds/epic-builds", "state": "ok" if build["exists"] else "todo", "kind": "desk", "detail": "Built by Unity into Build/Epic/Windows (Builds tab)."},
        {"title": "Upload to the Dev sandbox", "go": "epic/builds/epic-upload", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "detail": "BuildPatch Tool UploadBinary with a unique build version."},
        {"title": "Attach, rate and submit", "state": "todo", "kind": "hand", "link": portal,
         "detail": "In the Developer Portal: attach the binary to the artifact's Windows platform, set regions and age ratings, price, then submit for review and promote through Release Management."},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "build": build, "key": key, "steps": steps,
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project):
    s = status(project)
    lines = [f"Epic listing: {f['label']} {f['problem']}" for f in s["fields"] if f["problem"]]
    missing = [a["label"] for a in s["art"] if a["state"] == "missing"]
    if missing:
        lines.append("Epic art missing: " + ", ".join(missing))
    lines.append(f"Epic: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open")
    return lines


# BuildPatch Tool ----------------------------------------------------------------------------------------------

def build_version(project, info):
    rel = release.effective(project, "epic")
    commit = (info.get("commit") or project.git_commit(project.root) or "").split("+")[0]
    text = f"{rel['version']}-b{rel['build']}" + (f"-{commit}" if commit else "")
    return re.sub(r"[^A-Za-z0-9.+_-]", "", text)[:100]


def _run(project, args):
    """Runs BPT with the secret from Credential Manager in its environment. Returns (exit code, output)."""
    key = key_state(project)
    scripts = project.root / "Build" / "Epic" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    ids = key["ids"]
    full = [f"-OrganizationId={ids['organizationId']}", f"-ProductId={ids['productId']}", f"-ArtifactId={ids['artifactId']}",
            f"-ClientId={ids['clientId']}", f"-ClientSecretEnvVar={SECRET_ENV}"] + args
    arg_file = scripts / "bpt-args.txt"
    arg_file.write_text("\n".join(full) + "\n", encoding="utf-8")
    runner = scripts / "run-bpt.ps1"
    runner.write_text(_RUNNER, encoding="utf-8")
    run = jobs.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner),
                          "-Target", key["credential"], "-Exe", key["bpt"], "-ArgFile", str(arg_file), "-EnvName", SECRET_ENV],
                         timeout=6 * 3600, encoding="utf-8", errors="replace")
    output = run.stdout + run.stderr
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "buildpatchtool.txt").write_text(output, encoding="utf-8")
    return run.returncode, output


def _tail(output):
    keep = [l for l in output.splitlines() if re.search(r"error|fail|success|complete|uploaded|registered|version|binar", l, re.I)]
    return "\n".join(keep[-8:]) or "See Store/Logs/buildpatchtool.txt"


def check(project):
    """ListBinaries: proves the IDs and the secret work, and shows what is registered. Changes nothing."""
    key = key_state(project)
    if not key["ready"]:
        return False, "Finish the BuildPatch Tool setup first (Keys & accounts)."
    code, output = _run(project, ["-mode=ListBinaries", "-Num=5"])
    return code == 0, _tail(output)


def upload(project):
    key, info = key_state(project), _build(project)
    if not key["ready"]:
        return False, "Finish the BuildPatch Tool setup first (Keys & accounts)."
    if not info["exists"]:
        return False, "Build Windows (Epic) first."
    root = Path(info["path"])
    exes = [p for p in root.glob("*.exe") if "UnityCrashHandler" not in p.name]
    if not exes:
        return False, f"No game executable in {root}."
    scripts = project.root / "Build" / "Epic" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    ignore = scripts / "ignore.txt"
    ignore.write_text("\n".join(IGNORE) + "\n", encoding="utf-8")
    cloud = project.root / "Build" / "Epic" / "cloud"
    cloud.mkdir(parents=True, exist_ok=True)
    version = build_version(project, info)
    code, output = _run(project, ["-mode=UploadBinary", f"-BuildRoot={root.as_posix()}", f"-CloudDir={cloud.as_posix()}",
                                  f"-BuildVersion={version}", f"-AppLaunch={exes[0].name}", "-AppArgs=",
                                  f"-FileIgnoreList={ignore.as_posix()}"])
    if code != 0:
        return False, f"BuildPatch Tool exit code {code}\n" + _tail(output)
    builds.mark_uploaded(project, "epic-windows", f"Dev sandbox {version}")
    return True, f"Uploaded {version} to the Dev sandbox. Attach it to the Windows platform in the Developer Portal.\n" + _tail(output)
