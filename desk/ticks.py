"""By-hand setup steps the desk cannot see (accounts and forms on the stores' own sites): the user ticks them Done.
Kept per store in Store/ticks.json as step titles (no secrets)."""
FILE = "ticks.json"


def _tickable(step):
    return step.get("kind") == "hand" and not step.get("go")


def apply(project, store_id, status):
    """Marks ticked by-hand steps done and flags every by-hand step the desk cannot check, so the page shows a tick."""
    done = set(((project.read(FILE, {}) or {}).get(store_id)) or [])
    for step in status.get("steps", []):
        if not _tickable(step):
            continue
        if step.get("state") == "ok" and step["title"] not in done:
            continue  # the desk found it done by itself
        step["tick"] = True
        if step["title"] in done:
            step["state"] = "ok"
    return status


def save(project, store_id, status, title, on):
    titles = {s["title"] for s in status.get("steps", []) if _tickable(s)}
    if title not in titles:
        raise ValueError(f"No by-hand step called {title!r} on {store_id}.")
    all_ = project.read(FILE, {}) or {}
    mine = set(all_.get(store_id) or [])
    (mine.add if on else mine.discard)(title)
    all_[store_id] = sorted(mine & titles)
    project.write(FILE, all_)
