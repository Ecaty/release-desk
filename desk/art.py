"""Store art made from the game's sources in Store/art: one square icon becomes every store icon size."""
import json
from pathlib import Path

from . import images, jobs, raster

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
ICO_SIZES = (256, 48, 32, 16)
SOURCES = {"icon": "art/icon.png"}


def rules(store):
    return json.loads((RULES_DIR / f"{store}.json").read_text(encoding="utf-8"))


def stores():
    return sorted(p.stem for p in RULES_DIR.glob("*.json"))


def check(project, store):
    """Each art file in the store's rules: present, readable and the right size."""
    folder = project.store / store / "art"
    out = []
    for spec in rules(store).get("art", []):
        found = None
        for ext in spec.get("formats", ["png", "jpg"]):
            candidate = folder / f"{spec['file']}.{ext}"
            if candidate.is_file():
                found = candidate
                break
        item = {"label": spec["label"], "expected": f"{spec['width']}×{spec['height']}", "required": spec["required"],
                "file": f"{store}/art/{spec['file']}.{spec.get('formats', ['png'])[0]}", "note": spec.get("note", ""), "make": spec.get("make", "")}
        if not found:
            item["state"] = "missing" if spec["required"] else "optional"
        else:
            dims = images.size(found)
            item["file"] = str(found.relative_to(project.store)).replace("\\", "/")
            if not dims:
                item["state"], item["problem"] = "bad", "not a readable image"
            else:
                w, h, fmt = dims
                item["actual"] = f"{w}×{h}"
                if spec.get("fit") == "either":
                    ok = (w == spec["width"] and h <= spec["height"]) or (h == spec["height"] and w <= spec["width"])
                else:
                    ok = (w, h) == (spec["width"], spec["height"])
                item["state"] = "ok" if ok else "bad"
                if not ok:
                    item["problem"] = f"is {w}×{h}, needs {item['expected']}"
        out.append(item)
    return out


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
        jobs.check()
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


# Capsules: key art (rendered by Unity from a shot in Store/shots.json) plus the logo --------------------------

SOURCES.update({"keyArt": "shots/art/key-art.png", "logo": "art/logo.png"})


def _settings(project, store, spec):
    """Rule defaults for one output, overridden by Store/art.json "outputs": {"<store>/<file>": {...}}."""
    data = project.read("art.json", {}) or {}
    custom = data.get("outputs", {}).get(f"{store}/{spec['file']}", {})
    logo = {**spec.get("logo", {}), **custom.get("logo", {})}
    return {"focus": custom.get("focus", spec.get("focus", [0.5, 0.5])), "zoom": custom.get("zoom", 1.0), "logo": logo}


def _place_logo(canvas, logo, box):
    """Fit the logo into box (fractions x, y = centre; w, h = max size) and composite it."""
    w = max(1, int(canvas.width * box.get("w", 0.6)))
    h = max(1, int(canvas.height * box.get("h", 0.5)))
    fitted = raster.contain(logo, w, h)
    x = int(canvas.width * box.get("x", 0.5) - fitted.width / 2)
    y = int(canvas.height * box.get("y", 0.5) - fitted.height / 2)
    raster.paste(canvas, fitted, x, y)


def _save(image, out, fmt):
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jpg":
        raster.write_jpeg(image, out)
    else:
        raster.write_png(image, out)


def make_capsules(project, only=""):
    """Every rules entry with make = capsule (key art + logo), hero (key art only) or logo (logo alone)."""
    src = sources(project)
    key_path, logo_path = project.store / src["keyArt"], project.store / src["logo"]
    wanted = [(s, spec) for make in ("capsule", "hero", "logo") for s, spec in _outputs(make)
              if not only or f"{s}/{spec['file']}" == only]
    if not wanted:
        return False, "No capsule outputs in the rules" + (f" named {only}." if only else ".")
    needs_key = any(spec["make"] != "logo" for _, spec in wanted)
    needs_logo = any(spec["make"] != "hero" for _, spec in wanted)
    missing = []
    if needs_key and not key_path.is_file():
        missing.append(f"key art Store/{src['keyArt']} (capture the key-art shot)")
    if needs_logo and not logo_path.is_file():
        missing.append(f"logo Store/{src['logo']} (transparent PNG)")
    if missing:
        return False, "Missing " + " and ".join(missing) + "."
    key = raster.read_png(key_path) if needs_key else None
    logo = raster.trim(raster.read_png(logo_path)) if needs_logo else None
    lines = []
    if logo and not logo.has_alpha():
        lines.append(f"Note: Store/{src['logo']} has no transparency; the logo will cover the art as a rectangle.")
    for store, spec in wanted:
        jobs.check()
        width, height = spec["width"], spec["height"]
        fmt = spec.get("formats", ["png"])[0]
        out = project.store / store / "art" / f"{spec['file']}.{fmt}"
        settings = _settings(project, store, spec)
        if spec["make"] == "logo":
            fitted = raster.contain(logo, width, height)
            image = fitted
            if spec.get("pad"):  # exact canvas size, logo centred on transparency
                image = raster.Image(width, height)
                raster.paste(image, fitted, (width - fitted.width) // 2, (height - fitted.height) // 2)
            if logo.width < fitted.width:
                lines.append(f"Note: the logo is {logo.width}×{logo.height}; a larger logo would keep {spec['label']} sharp.")
        else:
            if key.width < width or key.height < height:
                lines.append(f"Note: key art {key.width}×{key.height} is smaller than {spec['label']} {width}×{height}; it is enlarged.")
            image = raster.cover(key, width, height, tuple(settings["focus"]), settings["zoom"])
            if spec["make"] == "capsule":
                _place_logo(image, logo, settings["logo"])
        _save(image, out, fmt)
        lines.append(f"{store}: {spec['label']} {image.width}×{image.height} → Store/{out.relative_to(project.store).as_posix()}")
    return True, "\n".join(lines)
