"""Which stores a project's desk shows. Store/store.json "stores" holds {id: false} for each store turned off; a store
that is not listed is on, so a store added to the desk later shows in every project until it is turned off there."""
from . import evaluate

# Stores the desk is wired up for, in menu order within their group.
DESK = [("steam", "Steam", "pc", "steam"), ("itch", "itch.io", "pc", "itch"), ("epic", "Epic Games Store", "pc", "epic"),
        ("gog", "GOG", "pc", "gog"), ("microsoft", "Microsoft Store", "pc", "microsoft"),
        ("itch-android", "itch.io Android", "android", "itch"), ("play", "Google Play", "android", "play"),
        ("samsung", "Galaxy Store", "android", "")]
# Which store page each build kind belongs to.
KIND_STORE = {"steam-windows": "steam", "itch-windows": "itch", "itch-android-apk": "itch-android", "epic-windows": "epic",
              "gog-windows": "gog", "microsoft-windows": "microsoft", "play-dev-apk": "play", "play-aab": "play"}
GROUPS = [["pc", "PC"], ["android", "Android"], ["xr", "XR"], ["console", "Console"], ["apple", "Apple"]]


def _off(project):
    data = (project.read("store.json", {}) or {}).get("stores", {}) or {} if project else {}
    return {k for k, v in data.items() if v is False}


def known():
    return [s[0] for s in DESK] + [s["id"] for s in evaluate.stores()]


def is_on(project, store_id):
    return store_id not in _off(project)


def listing(project):
    off = _off(project)
    desk = [{"id": i, "name": n, "group": g, "icon": icon, "kind": "desk", "on": i not in off} for i, n, g, icon in DESK]
    later = [{"id": s["id"], "name": s["name"], "group": s["group"], "icon": s["icon"], "kind": "evaluate", "fit": s["fit"],
              "on": s["id"] not in off} for s in evaluate.stores()]
    return {"groups": GROUPS, "stores": desk + later}


def save(project, changes):
    ids = set(known())
    store = project.read("store.json", {}) or {}
    current = store.get("stores", {}) or {}
    for k, v in (changes or {}).items():
        if k not in ids:
            raise ValueError(f"Unknown store: {k}")
        if v:
            current.pop(k, None)
        else:
            current[k] = False
    store["stores"] = current
    project.write("store.json", store)


def on_kinds(project, kinds):
    off = _off(project)
    return [k for k in kinds if KIND_STORE.get(k) not in off]
