"""Microsoft Store (PC): listing and art checks, MSIX packaging of the Windows build, updates through the Microsoft
Store Developer CLI (msstore).

The first release is created and submitted by hand in Partner Center (the CLI cannot do it). After that, Publish
packages the Windows build as an MSIX with Windows' makeappx and runs `msstore publish`. The Partner Center API
credentials are entered once in msstore's own console setup (`msstore reconfigure`); the desk never sees them.
The Store signs MSIX packages it distributes, so no signing certificate is needed here."""
import os
import re
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from . import art, builds, jobs, raster, release, storekit

RULES = art.rules("microsoft")
FIELDS = (("productId", "Store ID"), ("identityName", "Package identity name"), ("publisher", "Publisher"), ("publisherName", "Publisher display name"))


def settings(project):
    data = (project.read("store.json", {}) or {}).get("microsoft", {}) or {}
    return {**{k: data.get(k, "") for k, _ in FIELDS}, "capabilities": data.get("capabilities", ["microphone"])}


def makeappx():
    root = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    found = sorted(root.glob("*/x64/makeappx.exe")) if root.is_dir() else []
    return found[-1] if found else None


def msstore():
    found = shutil.which("msstore")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "msstore.exe"
    return str(candidate) if candidate.exists() else None


def key_state(project):
    data = settings(project)
    missing = [label for key, label in FIELDS if not data.get(key)]
    tool, cli = makeappx(), msstore()
    return {"makeappx": str(tool or ""), "msstore": str(cli or ""), "ids": {k: data[k] for k, _ in FIELDS}, "missing": missing,
            "ready": bool(tool) and bool(cli) and not missing}


def msix_version(project):
    """Store packages need four numbers with the last one 0: major.minor.build.0 (build = release build number)."""
    rel = release.effective(project, "microsoft")
    parts = [int(p) for p in re.findall(r"\d+", str(rel["version"]))[:2]] + [0, 0]
    return f"{parts[0]}.{parts[1]}.{int(rel['build'])}.0"


def _build(project):
    info = builds.latest(project, "microsoft-windows")
    info["folder"] = info["path"]
    info["history"] = builds.history(project, "microsoft-windows")
    return info


def status(project):
    fields = storekit.fields(project, "microsoft", RULES)
    art_items, shots, build, key = art.check(project, "microsoft"), storekit.screenshots(project, RULES), _build(project), key_state(project)
    partner = "https://partner.microsoft.com/dashboard"
    steps = [
        {"title": "Partner Center account and app name", "state": "ok" if key["ids"]["productId"] else "todo", "kind": "hand", "link": partner,
         "go": "microsoft/keys/ids-microsoft-productId",
         "detail": "Register as a Windows app developer, reserve the game's name, then copy the Store ID and the Product identity values (Package/Identity/Name, Publisher, Publisher display name) into Keys & accounts."},
        {"title": "Packaging tool", "state": "ok" if key["makeappx"] else "todo", "kind": "hand", "go": "microsoft/keys/microsoft-tools",
         "link": "https://developer.microsoft.com/windows/downloads/windows-sdk/",
         "detail": "makeappx comes with the Windows SDK."},
        {"title": "Store listing text", "state": "ok" if not any(f["problem"] for f in fields) else "todo", "kind": "copy", "go": "microsoft/listing/microsoft-text",
         "detail": "Paste into the Partner Center store listing."},
        {"title": "Store images", "state": "ok" if all(a["state"] in ("ok", "optional") for a in art_items) else "todo", "kind": "copy", "go": "microsoft/listing/microsoft-art",
         "detail": "2:3 poster art and 1:1 box art are needed for games; tile icon and 16:9 super hero art are recommended."},
        {"title": "Screenshots", "state": "ok" if shots["good"] >= shots["min"] else "todo", "kind": "copy", "go": "microsoft/listing/microsoft-shots",
         "detail": f"{shots['good']} usable (1366×768 or larger) in Store/{shots['folder']}."},
        {"title": "Windows build and MSIX", "state": "ok" if build["exists"] else "todo", "kind": "desk", "go": "microsoft/builds/microsoft-builds",
         "detail": "Built by Unity into Build/Microsoft/Windows; Package MSIX wraps it with the Store identity."},
        {"title": "First submission by hand", "state": "todo", "kind": "hand", "link": partner,
         "detail": "Upload the first MSIX, age ratings questionnaire, pricing and listing in Partner Center and submit for certification. The CLI only publishes updates after this."},
        {"title": "msstore CLI signed in", "state": "ok" if key["msstore"] else "todo", "kind": "desk", "go": "microsoft/keys/microsoft-tools",
         "link": "https://learn.microsoft.com/en-us/windows/apps/publish/msstore-dev-cli/overview",
         "detail": "Install the Microsoft Store Developer CLI, then Set up msstore (Keys & accounts) and enter the Microsoft Entra app's tenant, seller, client ID and secret in its own console."},
        {"title": "Publish updates", "state": "ok" if any(h.get("uploaded") for h in build["history"][:1]) else "todo", "kind": "desk",
         "go": "microsoft/builds/microsoft-upload",
         "detail": "msstore publish uploads the MSIX as a new submission. Microsoft's CLI updates free products only for now."},
    ]
    return {"fields": fields, "art": art_items, "screenshots": shots, "build": build, "key": key, "steps": steps, "msixVersion": msix_version(project),
            "rules": {"checked": RULES["checked"], "sources": RULES["sources"]}}


def summary_lines(project):
    s = status(project)
    return [f"Microsoft Store: {len([x for x in s['steps'] if x['state'] != 'ok'])} steps open"]


def setup_cli(project):
    """Console where msstore asks for its Partner Center API credentials and keeps them itself."""
    cli = msstore()
    if not cli:
        return False, "Install the Microsoft Store Developer CLI first."
    subprocess.Popen(["cmd", "/c", "title msstore setup & echo Enter the Partner Center API values; Release Desk never sees them. & echo. & "
                      f'"{cli}" reconfigure & echo. & pause'], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return True, "Opened a console window; finish msstore's setup there."


def _manifest(project, exe_name, version):
    s, rel = settings(project), release.effective(project, "microsoft")
    caps = "".join(f'\n    <DeviceCapability Name="{escape(c)}"/>' for c in s["capabilities"])
    return f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="{escape(s['identityName'])}" Publisher="{escape(s['publisher'], {'"': '&quot;'})}" Version="{version}" ProcessorArchitecture="x64"/>
  <Properties>
    <DisplayName>{escape(rel['name'])}</DisplayName>
    <PublisherDisplayName>{escape(s['publisherName'])}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0"/>
  </Dependencies>
  <Resources>
    <Resource Language="en-us"/>
  </Resources>
  <Applications>
    <Application Id="Game" Executable="{escape(exe_name)}" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{escape(rel['name'])}" Description="{escape(rel['name'])}" BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png"/>
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust"/>{caps}
  </Capabilities>
</Package>
'''


def package(project):
    """Copies the Windows build into a staging folder with AppxManifest.xml and logos, then runs makeappx."""
    key, info = key_state(project), _build(project)
    missing = [m for m in key["missing"] if m != "Store ID"]
    if missing:
        return False, "Fill in " + ", ".join(missing) + " (Keys & accounts)."
    if not key["makeappx"]:
        return False, "makeappx not found; install the Windows SDK."
    if not info["exists"]:
        return False, "Build Windows (Microsoft) first."
    icon_path = project.store / art.sources(project)["icon"]
    if not icon_path.is_file():
        return False, f"Add the source icon Store/{art.sources(project)['icon']} first (it makes the package logos)."
    root = Path(info["path"])
    exes = [p for p in root.glob("*.exe") if "UnityCrashHandler" not in p.name]
    if not exes:
        return False, f"No game executable in {root}."
    out_dir = project.root / "Build" / "Microsoft"
    stage = out_dir / "package"
    if stage.exists():
        shutil.rmtree(stage)
    jobs.check()
    shutil.copytree(root, stage, ignore=shutil.ignore_patterns("*.pdb", "*DoNotShip*", "*DontShipItWithYourGame*"))
    assets = stage / "Assets"
    assets.mkdir(exist_ok=True)
    icon = raster.read_png(icon_path)
    for spec in RULES["package"]:
        jobs.check()
        raster.write_png(raster.resize(icon, spec["size"], spec["size"]), assets / f"{spec['file']}.png", alpha=True)
    version = msix_version(project)
    (stage / "AppxManifest.xml").write_text(_manifest(project, exes[0].name, version), encoding="utf-8")
    msix = out_dir / f"{builds._safe(release.effective(project, 'microsoft')['name'])}_{version}.msix"
    run = jobs.run([key["makeappx"], "pack", "/d", str(stage), "/p", str(msix), "/o"], timeout=3600)
    output = (run.stdout or "") + (run.stderr or "")
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "makeappx.txt").write_text(output, encoding="utf-8")
    if run.returncode != 0 or not msix.is_file():
        tail = [l for l in output.splitlines() if l.strip()][-6:]
        return False, "makeappx failed:\n" + "\n".join(tail)
    return True, f"Packaged {msix.name} ({round(msix.stat().st_size / 1048576)} MB), version {version}."


def latest_msix(project):
    out_dir = project.root / "Build" / "Microsoft"
    found = sorted(out_dir.glob("*.msix"), key=lambda p: p.stat().st_mtime, reverse=True) if out_dir.is_dir() else []
    return found[0] if found else None


def publish(project):
    key = key_state(project)
    if not key["ready"]:
        return False, "Finish the Microsoft Store setup first (Keys & accounts)."
    msix = latest_msix(project)
    if not msix:
        return False, "Package an MSIX first."
    run = jobs.run([key["msstore"], "publish", str(msix), "-id", key["ids"]["productId"]], timeout=6 * 3600,
                   encoding="utf-8", errors="replace")
    output = (run.stdout or "") + (run.stderr or "")
    (project.store / "Logs").mkdir(parents=True, exist_ok=True)
    (project.store / "Logs" / "msstore.txt").write_text(output, encoding="utf-8")
    tail = "\n".join([l for l in output.splitlines() if l.strip()][-8:])
    if run.returncode != 0:
        return False, f"msstore exit code {run.returncode}\n{tail}"
    builds.mark_uploaded(project, "microsoft-windows", f"Store submission {msix.stem.split('_')[-1]}")
    return True, f"Submitted {msix.name}. Certification follows in Partner Center.\n{tail}"
