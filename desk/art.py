"""Store art made from the game's sources in Store/art: one square icon becomes every store icon size."""
import json
from pathlib import Path

from . import raster

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
ICO_SIZES = (256, 48, 32, 16)
SOURCES = {"icon": "art/icon.png"}


def rules(store):
    return json.loads((RULES_DIR / f"{store}.json").read_text(encoding="utf-8"))


def stores():
    return sorted(p.stem for p in RULES_DIR.glob("*.json"))


def sources(project):
    """Source paths in Store/, overridable in Store/art.json ("sources": {...})."""
    data = project.read("art.json", {}) or {}
    return {**SOURCES, **data.get("sources", {})}


def _outputs(make):
    for store in stores():
        for spec in rules(store).get("art", []):
            if spec.get("make") == make:
                yield store, spec


def make_icons(project):
    rel = sources(project)["icon"]
    path = project.store / rel
    if not path.is_file():
        return False, f"Add the source icon as Store/{rel} (square PNG, 1024×1024)."
    icon = raster.read_png(path)
    if icon.width != icon.height:
        return False, f"Store/{rel} is {icon.width}×{icon.height}; it must be square."
    lines = []
    if icon.width < 1024:
        lines.append(f"Note: Store/{rel} is {icon.width}×{icon.width}; 1024×1024 keeps every size sharp.")
    for store, spec in _outputs("icon"):
        size, fmt = spec["width"], spec.get("formats", ["png"])[0]
        out = project.store / store / "art" / f"{spec['file']}.{fmt}"
        out.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "ico":
            out.write_bytes(raster.ico_bytes([raster.resize(icon, s, s) for s in ICO_SIZES if s <= size]))
        elif fmt == "jpg":
            raster.write_jpeg(raster.resize(icon, size, size), out)
        else:
            raster.write_png(raster.resize(icon, size, size), out, alpha=spec.get("alpha", True))
        lines.append(f"{store}: {spec['label']} {size}×{size} → Store/{out.relative_to(project.store).as_posix()}")
    return True, "\n".join(lines)
