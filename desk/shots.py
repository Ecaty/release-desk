"""Screenshots: Unity plays each shot from Store/shots.json (prepared by the game, e.g. through Flecs Script)
and writes Store/shots/<store>/<name>.png at the exact size."""
import json
import time

from . import builds, jobs, unity


def shot_list(project):
    data = project.read("shots.json", {"shots": []}) or {"shots": []}
    shots = data.get("shots", [])
    for shot in shots:
        files = []
        for store in shot.get("stores", ["steam"]):
            path = project.store / "shots" / store / f"{shot.get('name', '')}.png"
            if path.is_file():
                files.append({"store": store, "file": str(path.relative_to(project.store)).replace("\\", "/"),
                              "made": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))})
        shot["files"] = files
    return shots


def capture(project, only=""):
    shots_path = project.store / "shots.json"
    if not shots_path.is_file():
        return False, "Add Store/shots.json with the shot list first."
    result = project.root / "Build" / "shots-result.json"
    if result.exists():
        result.unlink()
    started = time.time()
    code = (f"return ReleaseDesk.Editor.ShotCapture.Start({unity.literal(shots_path)}, {unity.literal(project.store / 'shots')}, "
            f"{unity.literal(result)}, {unity.literal(only)});")
    ok, message = unity.call(project.root, code, timeout=120)
    if not ok:
        return False, message
    deadline = time.time() + 1800
    while not result.exists() and time.time() < deadline:
        jobs.sleep(3)
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        errors = builds.unity_errors(project, started)
        return False, "Capture did not finish.\n" + errors[-1200:]
    lines = [f"{len(data.get('files', []))} images in {data.get('seconds')} s"] + [f"Problem: {e}" for e in data.get("errors", [])]
    return data.get("result") == "Succeeded", "\n".join(lines)
