"""One release shared by every store: name, version, build number and What's new live in Store/store.json.
A store can override a field ("overrides": {"<store>": {"<field>": value}}); everything else uses the shared value."""
import json
import subprocess

FIELDS = {
    "name": {"label": "Game name"},
    "version": {"label": "Version", "note": "Unity bundleVersion"},
    "build": {"label": "Build number", "note": "Android version code; raise it for each store upload", "number": True},
    "whatsNew": {"label": "What's new", "multiline": True, "max": 500,
                 "note": "What players notice, not technical work. Leave it empty and each build records the 'Release-note:' lines committed since the previous build; Fill from commits shows them here to edit. Play shows it as “What’s new” (500 characters). On Steam, paste it into an update event in Steamworks (players see events, not build descriptions)."},
}
STORES = {"steam": "Steam", "epic": "Epic Games Store", "gog": "GOG", "microsoft": "Microsoft Store", "play": "Google Play"}
BUILD_STORE = {"Steam": "steam", "Epic": "epic", "GOG": "gog", "Microsoft": "microsoft", "GooglePlay": "play"}
NOTES = {"steam": {"name": "Cannot be changed after Valve's pre-release review."}}


def _clean(field, value):
    if FIELDS[field].get("number"):
        return int(value or 0)
    return str(value or "").strip()


def shared(project):
    data = project.read("store.json", {}) or {}
    return {f: data.get(f, 0 if FIELDS[f].get("number") else "") for f in FIELDS}


def overrides(project, store):
    return dict(((project.read("store.json", {}) or {}).get("overrides", {}) or {}).get(store, {}))


def effective(project, store):
    values = shared(project)
    values.update({k: v for k, v in overrides(project, store).items() if k in FIELDS})
    return values


def save(project, values, store=None, override=None):
    """store=None saves the shared values. With a store, `override` maps field -> bool: ticked fields keep the
    store's own value, unticked ones go back to the shared value."""
    data = project.read("store.json", {}) or {}
    if store is None:
        for field, value in values.items():
            if field in FIELDS:
                data[field] = _clean(field, value)
    else:
        if store not in STORES:
            raise ValueError(f"Unknown store {store}")
        own = data.setdefault("overrides", {}).setdefault(store, {})
        for field, on in (override or {}).items():
            if field not in FIELDS:
                continue
            if on:
                own[field] = _clean(field, values.get(field, own.get(field, data.get(field, ""))))
            else:
                own.pop(field, None)
        if not own:
            data["overrides"].pop(store)
        if not data["overrides"]:
            data.pop("overrides")
    project.write("store.json", data)
    return data


def bump_build(project, store):
    """Next build number after an upload: raises the store's override when it has one, else the shared number."""
    data = project.read("store.json", {}) or {}
    own = (data.get("overrides", {}) or {}).get(store, {})
    if "build" in own:
        own["build"] = int(own["build"]) + 1
        value = own["build"]
    else:
        data["build"] = int(data.get("build", 0)) + 1
        value = data["build"]
    project.write("store.json", data)
    return value


def status(project):
    return {"fields": FIELDS, "shared": shared(project),
            "stores": {s: {"name": label, "values": effective(project, s), "overrides": sorted(overrides(project, s)),
                         "notes": NOTES.get(s, {})}
                       for s, label in STORES.items()}}


def unity_file(project, store):
    """store.json with the store's effective values, for DeskEntry.ApplySettings before a build."""
    data = dict(project.read("store.json", {}) or {})
    data.update({k: v for k, v in effective(project, store).items() if k != "whatsNew"})
    path = project.root / "Build" / f"release-{store}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def changes(text):
    """What's new as a short list of lines without bullets."""
    return [l.strip().lstrip("-•* ").strip() for l in str(text or "").splitlines() if l.strip().lstrip("-•* ").strip()]


NOTE_TRAILER = "Release-note"


def draft(project, since=""):
    """Player-facing notes since `since` (the last build's commit), oldest first. Only commits that carry a
    'Release-note: <what players or stores notice>' trailer count; technical commits never show up."""
    since = since.split("+")[0]
    args = ["git", "-C", str(project.root), "log", "--reverse",
            f"--format=%(trailers:key={NOTE_TRAILER},valueonly,separator=%x0A)"]
    args += [f"{since}..HEAD"] if since else ["-300"]
    try:
        run = subprocess.run(args, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return ""
    if run.returncode and since:
        return draft(project)
    notes = []
    for line in run.stdout.splitlines():
        line = line.strip()
        if line and line not in notes:
            notes.append(line)
    return "\n".join("- " + n for n in notes)


def migrate(project):
    """Earlier desks kept the Steam game name in steam/listing.json; it is now the shared name or a Steam override."""
    listing = project.read("steam/listing.json", None)
    if not listing or "name" not in listing:
        return
    name = str(listing.pop("name") or "").strip()
    if name and name != shared(project)["name"] and "name" not in overrides(project, "steam"):
        save(project, {"name": name}, "steam", {"name": True})
    project.write("steam/listing.json", listing)
