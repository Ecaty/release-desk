"""One release shared by every store: name, version, build number and What's new live in Store/store.json.
A store can override a field ("overrides": {"<store>": {"<field>": value}}); everything else uses the shared value."""
import json
import subprocess

FIELDS = {
    "name": {"label": "Game name"},
    "short": {"label": "Short description", "multiline": True,
              "note": "One or two sentences: Steam short description (300), Google Play short description (80), itch.io tagline."},
    "description": {"label": "Description", "multiline": True,
                    "note": "The long store text: Steam About this game, Play full description (4000), Epic About, GOG, Microsoft Store, itch.io."},
    "version": {"label": "Version", "note": "Unity bundleVersion"},
    "build": {"label": "Build number", "note": "Android version code; raise it for each store upload", "number": True},
    "whatsNew": {"label": "What's new", "multiline": True, "max": 500,
                 "note": "What players notice, not technical work. Leave it empty and each build records the 'Release-note:' lines committed since the previous build; Fill from commits shows them here to edit. Play shows it as “What’s new” (500 characters). On Steam, paste it into an update event in Steamworks (players see events, not build descriptions)."},
}
STORES = {"steam": "Steam", "itch": "itch.io", "epic": "Epic Games Store", "gog": "GOG", "microsoft": "Microsoft Store", "play": "Google Play", "samsung": "Galaxy Store"}
BUILD_STORE = {"Steam": "steam", "Itch": "itch", "Epic": "epic", "GOG": "gog", "Microsoft": "microsoft", "GooglePlay": "play"}
NOTES = {"steam": {"name": "Cannot be changed after Valve's pre-release review."}}


def _clean(field, value):
    if FIELDS[field].get("number"):
        return int(value or 0)
    return str(value or "").strip()


def limits(store):
    """Shared field -> maximum length on this store, from its rules file."""
    from . import art
    try:
        rules = art.rules(store)
    except OSError:
        return {}
    out = {rule["from"]: rule["max"] for rule in rules.get("text", {}).values() if rule.get("from") and rule.get("max")}
    if rules.get("titleMax"):
        out["name"] = rules["titleMax"]
    return out


def too_long(project, store):
    """Fields whose value for this store is over the store's limit: {field: "120 / 80 characters"}."""
    values = effective(project, store)
    return {f: f"{len(str(values.get(f, '')))} / {m} characters" for f, m in limits(store).items() if len(str(values.get(f, ""))) > m}


def text_fields(project, store, rules, text):
    """A store's listing text: fields marked "from" in its rules show the release value (shared or this store's
    override) and are edited in the Release box; the rest are the store's own text in <store>/listing.json."""
    values, own = effective(project, store), overrides(project, store)
    out = []
    for key, rule in rules["text"].items():
        src = rule.get("from")
        value = str(values.get(src, "")) if src else text.get(key, "")
        problem = "empty" if rule.get("required") and not value else (
            f"{len(value)} / {rule['max']} characters" if rule.get("max") and len(value) > rule["max"] else "")
        note = rule.get("note", "")
        if src:
            origin = "this store's override" if src in own else "the shared text"
            note = (f"From Release ({FIELDS[src]['label'].lower()}, {origin})."
                    + (" Too long here: tick override in the Release box and shorten it." if problem and "characters" in problem else "")
                    + (" " + note if note else ""))
        out.append({"key": key, "label": rule["label"], "value": value, "max": rule.get("max"), "multiline": rule.get("multiline", False),
                    "note": note, "problem": problem, "readonly": bool(src)})
    return out


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
                         "notes": NOTES.get(s, {}), "limits": limits(s), "tooLong": too_long(project, s)}
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


MOVED = {"steam": {"name": "name", "shortDescription": "short", "about": "description"},
         "play": {"shortDescription": "short", "fullDescription": "description"}, "epic": {"about": "description"},
         "gog": {"description": "description"}, "microsoft": {"description": "description"},
         "itch": {"tagline": "short", "description": "description"}}


def migrate(project):
    """Earlier desks kept the game name and descriptions per store in <store>/listing.json; they are now shared
    release fields. The first store's text becomes the shared value; text that differs becomes that store's override."""
    for store, mapping in MOVED.items():
        listing = project.read(f"{store}/listing.json", None)
        if not listing or not any(k in listing for k in mapping):
            continue
        for key, field in mapping.items():
            if key not in listing:
                continue
            value = str(listing.pop(key) or "").strip()
            if not value:
                continue
            if not shared(project)[field]:
                save(project, {field: value})
            elif value != shared(project)[field] and field not in overrides(project, store):
                save(project, {field: value}, store, {field: True})
        project.write(f"{store}/listing.json", listing)
