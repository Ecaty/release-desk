"""Which stores a project's desk shows. Store/store.json "stores" holds {id: false} for each store turned off; a store
that is not listed is on, so a store added to the desk later shows in every project until it is turned off there
(the user's choice on card #118, 2026-11-22: "On"). "first" lists platform groups that come first for this project,
e.g. ["android"] puts Android above PC in the menu, Overview, the stores table and the status page; the other groups
keep the desk's order, and so do the stores within a group."""
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


def clean_first(value):
    """Only a list of known group ids counts, without duplicates; anything else (null, a number, a string, nested
    lists) is ignored, so a hand-edited store.json cannot break the desk."""
    if not isinstance(value, list):
        return []
    out = []
    for g in value:
        if isinstance(g, str) and g in dict(GROUPS) and g not in out:
            out.append(g)
    return out


def groups(project):
    data = (project.read("store.json", {}) or {}) if project else {}
    first = clean_first(data.get("first") if isinstance(data, dict) else None)
    return [[g, dict(GROUPS)[g]] for g in first] + [g for g in GROUPS if g[0] not in first]


def desk_order(project):
    """Desk stores in menu order for this project."""
    order = [g for g, _ in groups(project)]
    return sorted(DESK, key=lambda s: order.index(s[2]))


def known():
    return [s[0] for s in DESK] + [s["id"] for s in evaluate.stores()]


def name(store_id):
    return next((n for i, n, _g, _icon in DESK if i == store_id), store_id)


def is_on(project, store_id):
    return store_id not in _off(project)


def listing(project):
    off = _off(project)
    desk = [{"id": i, "name": n, "group": g, "icon": icon, "kind": "desk", "on": i not in off} for i, n, g, icon in DESK]
    later = [{"id": s["id"], "name": s["name"], "group": s["group"], "icon": s["icon"], "kind": "evaluate", "fit": s["fit"],
              "on": s["id"] not in off} for s in evaluate.stores()]
    return {"groups": groups(project), "stores": desk + later}


def save(project, changes):
    ids = set(known())
    store = project.read("store.json", {}) or {}
    changes = dict(changes or {})
    if "first" in changes:
        first = clean_first(changes.pop("first"))
        if first:
            store["first"] = first
        else:
            store.pop("first", None)
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
