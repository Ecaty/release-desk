"""Release check on the build laptop: builds, test suites and Explore for one pushed commit.

The project's own Tools/Test-On-Laptop.ps1 does the work over the user's SSH key (ssh-agent); the desk holds no
key or token and never reaches the laptop itself. Contract (agreed with the laptop side):
  Test-On-Laptop.ps1 -Commit <pushed sha> -Request <id> -Steps <a,b> [-ExploreSeed n] [-ExploreMinutes m] -NoWait
                                     start, exit 0/1/2
  Test-On-Laptop.ps1 -Status <id>    one JSON line {request, state, step, stepsDone, stepsTotal}
  Test-On-Laptop.ps1 -Cancel <id>    stops the laptop run (Unity closed, saves restored)
Exit codes: 0 passed / started, 1 failed or cancelled, 2 could not run (busy prints "busy: <id>").
A step can come back "skipped" with its reason as the summary (no phone reachable, a commit without the simulated
player, ...). Builds are listed per step in details.builds (name, size, sha256).
Results come back to <project>/Logs/release-check/<request>/result.json (git-ignored)."""
import json
import re
import subprocess
from datetime import datetime

from . import jobs

SCRIPT = "Tools/Test-On-Laptop.ps1"
STEPS = {
    "build-windows-dev": "Windows dev build",
    "build-android-dev": "Phone APK",
    "run-all": "Run-All",
    "extended": "Extended",
    "scenarios": "Scenarios",
    "explore-windows": "Explore on Windows",
    "explore-android": "Explore on the phone",
}
DONE = ("passed", "failed", "cancelled")
EXPLORE_MINUTES = 10
POLL = 30


def script(project):
    return project.root / SCRIPT


def supported(project):
    """The script exists and already speaks the release-check contract (it takes -Request)."""
    path = script(project)
    try:
        return path.is_file() and re.search(r"\$Request\b", path.read_text(encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


def _git(project, *args):
    run = subprocess.run(["git", "-C", str(project.root), *args], capture_output=True, text=True)
    return run.stdout.strip() if run.returncode == 0 else ""


def head(project):
    """The commit a check would run: HEAD of the open project, and whether origin has it."""
    sha = _git(project, "rev-parse", "HEAD")
    branch = _git(project, "rev-parse", "--abbrev-ref", "HEAD")
    pushed = bool(sha) and bool(_git(project, "branch", "-r", "--contains", sha))
    subject = _git(project, "log", "-1", "--format=%s")
    dirty = bool(_git(project, "status", "--porcelain", "--untracked-files=no"))
    return {"sha": sha, "short": sha[:9], "branch": branch, "pushed": pushed, "subject": subject, "dirty": dirty}


def new_request():
    return "rc-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def _ps(project, *args):
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script(project)), *args]


def _last_json(text):
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def _tail(run):
    text = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
    return "\n".join(text.splitlines()[-6:]) or f"exit {run.returncode}"


def status(project, request):
    run = jobs.run(_ps(project, "-Status", request), cwd=str(project.root), timeout=120)
    return _last_json(run.stdout) or {"request": request, "state": "unknown"}


def folder(project, request):
    return project.root / "Logs" / "release-check" / request


def result(project, request):
    """result.json as written by the laptop, with malformed parts dropped so one bad file cannot break the page."""
    try:
        r = json.loads((folder(project, request) / "result.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    r.setdefault("request", request)
    for key in ("steps", "builds", "links"):
        r[key] = [x for x in r.get(key) or [] if isinstance(x, dict)] if isinstance(r.get(key), list) else []
    for step in r["steps"]:
        if not isinstance(step.get("details"), dict):
            step["details"] = {}
    # Builds come per step (details.builds); list them once for the page.
    if not r["builds"]:
        r["builds"] = [b for step in r["steps"] for b in step["details"].get("builds") or [] if isinstance(b, dict)]
    return r


def results(project, limit=10):
    """Finished checks copied back from the laptop, newest first."""
    base = project.root / "Logs" / "release-check"
    out = []
    if base.is_dir():
        for d in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
            r = result(project, d.name)
            if r:
                out.append(r)
    return out


def check(project, steps, seed=None, minutes=None):
    """Starts a release check on the laptop and follows it until it ends. Cancel stops the laptop run too."""
    if not supported(project):
        return False, f"{SCRIPT} does not take release-check requests yet (laptop side, card #72)."
    steps = [s for s in steps if s in STEPS] or list(STEPS)
    h = head(project)
    if not h["sha"]:
        return False, "Not a git checkout."
    if not h["pushed"]:
        return False, f"{h['short']} is not on origin yet; push it first (the laptop checks out pushed commits only)."
    request = new_request()
    args = ["-Commit", h["sha"], "-Request", request, "-Steps", ",".join(steps)]
    if seed:
        args += ["-ExploreSeed", str(int(seed))]
    if minutes and int(minutes) != EXPLORE_MINUTES and any(x.startswith("explore") for x in steps):
        args += ["-ExploreMinutes", str(max(1, min(240, int(minutes))))]
    jobs.say("Starting on the laptop")
    run = jobs.run(_ps(project, *args, "-NoWait"), cwd=str(project.root), timeout=600)
    if run.returncode == 2:
        busy = re.search(r"busy:\s*([a-z0-9-]+)", (run.stdout or "") + (run.stderr or "")) or re.search(r"\b(rc-[a-z0-9-]+)\b", (run.stdout or "") + (run.stderr or ""))
        return False, f"Laptop busy{' with ' + busy.group(1) if busy else ''}, or it could not start:\n{_tail(run)}"
    if run.returncode != 0:
        return False, f"Could not start the check:\n{_tail(run)}"
    unknown = 0
    try:
        while True:
            jobs.sleep(POLL)
            st = status(project, request)
            state = st.get("state", "unknown")
            if state in DONE:
                break
            unknown = unknown + 1 if state == "unknown" else 0
            if unknown >= 20:
                return False, f"{request}: the laptop has not reported for {unknown * POLL // 60} min; see {SCRIPT} -Status {request}."
            step = STEPS.get(st.get("step", ""), st.get("step", "") or state)
            jobs.say(f"{request} · {step} ({st.get('stepsDone', 0)} of {st.get('stepsTotal', len(steps))} steps)")
    except jobs.Cancelled:
        # The job is cancelled, so jobs.run would refuse; stop the laptop run directly.
        subprocess.run(_ps(project, "-Cancel", request), cwd=str(project.root), capture_output=True, text=True, timeout=300)
        raise jobs.Cancelled(f"Cancelled; {request} was stopped on the laptop.")
    for _ in range(10):  # the result folder is copied back as the run ends
        r = result(project, request)
        if r:
            break
        jobs.sleep(6)
    else:
        return state == "passed", f"{request}: {state}, but no result.json came back to {folder(project, request)}."
    lines = [f"{request} on {h['short']}: {r.get('state', state)}. {r.get('summary', '')}".strip()]
    for s in r.get("steps", []):
        lines.append(f"{STEPS.get(s.get('name'), s.get('name'))}: {s.get('state')}{' · ' + s['summary'] if s.get('summary') else ''}")
    return r.get("state", state) == "passed", "\n".join(lines)


def summary_lines(project):
    last = results(project, 1)
    if not last:
        return ["Release check: none yet"]
    r = last[0]
    return [f"Release check {r.get('request')}: {r.get('state')} ({str(r.get('commit', ''))[:9]})"]


def state(project):
    return {"supported": supported(project), "script": SCRIPT, "head": head(project), "steps": STEPS,
            "exploreMinutes": EXPLORE_MINUTES, "results": results(project)}
