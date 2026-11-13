"""Listing text and screenshot checks shared by the stores whose page is filled in by hand (GOG, Microsoft Store)."""
from . import images, release


def listing(project, store):
    return project.read(f"{store}/listing.json", {}) or {}


def save_listing(project, store, rules, fields):
    data = listing(project, store)
    for key in rules["text"]:
        if key in fields:
            data[key] = str(fields[key]).strip()
    project.write(f"{store}/listing.json", data)
    return data


def fields(project, store, rules, name_label="Product name"):
    text, rel = listing(project, store), release.effective(project, store)
    out = [{"key": "name", "label": name_label, "value": rel["name"], "readonly": True,
            "note": "From Release (game name; override it for this store there).", "problem": "" if rel["name"] else "empty"}]
    for key, rule in rules["text"].items():
        value = text.get(key, "")
        problem = "empty" if rule.get("required") and not value else (
            f"{len(value)} / {rule['max']} characters" if rule.get("max") and len(value) > rule["max"] else "")
        out.append({"key": key, "label": rule["label"], "value": value, "max": rule.get("max"), "multiline": rule.get("multiline", False),
                    "note": rule.get("note", ""), "problem": problem})
    return out


def screenshots(project, rules):
    rule = rules["screenshots"]
    folder = project.store / rule["folder"]
    shots = []
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        dims = images.size(path)
        if not dims or dims[2] not in ("png", "jpg"):
            continue
        w, h, _ = dims
        ok = w >= rule["minWidth"] and h >= rule["minHeight"]
        shots.append({"file": path.name, "path": str(path), "size": f"{w}×{h}", "ok": ok})
    good = sum(s["ok"] for s in shots)
    return {"items": shots, "good": good, "min": rule["min"], "folder": rule["folder"], "note": rule["note"]}

