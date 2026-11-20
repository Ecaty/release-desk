"""Stores to evaluate: not wired up yet, listed so their cost, devices, review and fit with this game's AI and
runtime Flecs Script can be judged before any work starts. Facts and setup steps live in rules/evaluate.json
(with sources and the date they were checked); the user's ticks and notes per store in Store/evaluate.json."""
import json
from pathlib import Path

RULES = Path(__file__).resolve().parent.parent / "rules" / "evaluate.json"
FILE = "evaluate.json"
LEVELS = ("ok", "warn", "bad", "unknown")


def rules():
    return json.loads(RULES.read_text(encoding="utf-8"))


def stores():
    """Short list for the navigation: id, name, icon and how well the store fits the AI and runtime scripts."""
    r = rules()
    return [{"id": s["id"], "name": s["name"], "icon": s.get("icon", ""), "fit": s["fit"]["level"], "group": s.get("group", "")}
            for s in r["stores"]]


def store(project, store_id):
    r = rules()
    s = next((x for x in r["stores"] if x["id"] == store_id), None)
    if not s:
        raise ValueError(f"Unknown store: {store_id}")
    mine = ((project.read(FILE, {}) or {}).get(store_id) or {}) if project else {}
    done = set(mine.get("done", []))
    steps = [dict(step, state="ok" if i in done else "todo", kind=step.get("kind", "hand")) for i, step in enumerate(s.get("steps", []))]
    return dict(s, steps=steps, notes=mine.get("notes", ""), checked=r.get("checked", ""), common=r.get("common", ""))


def save(project, store_id, data):
    store(project, store_id)  # unknown ids raise
    all_ = project.read(FILE, {}) or {}
    entry = all_.get(store_id) or {}
    if "done" in data:
        entry["done"] = sorted({int(i) for i in data["done"]})
    if "notes" in data:
        entry["notes"] = str(data["notes"])[:4000]
    all_[store_id] = entry
    project.write(FILE, all_)
