"""Release check: the laptop contract (Tools/Test-On-Laptop.ps1, card #72) as the desk calls and reads it. Offline."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desk import laptop


class FakeProject:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp())


def write_result(p, request, data):
    folder = laptop.folder(p, request)
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps(data), encoding="utf-8")


class Results(unittest.TestCase):
    def test_builds_per_step_and_skipped(self):
        p = FakeProject()
        write_result(p, "rc-1", {"request": "rc-1", "state": "passed", "steps": [
            {"name": "build-windows-dev", "state": "passed", "details": {"builds": [{"name": "Ecaty.zip", "size": 1, "sha256": "ab"}]}},
            {"name": "explore-android", "state": "skipped", "summary": "No phone reachable"},
            "not a step"],
            "links": [{"label": "Explore report", "path": "explore/report.html"}]})
        r = laptop.result(p, "rc-1")
        self.assertEqual([b["name"] for b in r["builds"]], ["Ecaty.zip"])
        self.assertEqual(r["steps"][1]["state"], "skipped")
        self.assertEqual(len(r["steps"]), 2)
        self.assertEqual(r["links"][0]["label"], "Explore report")

    def test_scenarios_step_between_extended_and_explore(self):
        names = list(laptop.STEPS)
        self.assertEqual(names.index("scenarios"), names.index("extended") + 1)
        self.assertEqual(names.index("explore-windows"), names.index("scenarios") + 1)


class Start(unittest.TestCase):
    def start(self, returncode=0, out="", steps=None, minutes=None):
        p = FakeProject()
        calls = []

        def run(args, **kw):
            calls.append(args)
            return subprocess.CompletedProcess(args, returncode, out, "")

        with mock.patch.object(laptop, "supported", lambda p: True), \
                mock.patch.object(laptop, "head", lambda p: {"sha": "abc123", "short": "abc123", "pushed": True}), \
                mock.patch.object(laptop.jobs, "run", run), mock.patch.object(laptop.jobs, "say", lambda t: None), \
                mock.patch.object(laptop, "status", lambda p, r: {"state": "passed"}), mock.patch.object(laptop.jobs, "sleep", lambda s: None), \
                mock.patch.object(laptop, "result", lambda p, r: {"state": "passed", "summary": "ok", "steps": []}):
            ok, message = laptop.check(p, steps or ["run-all", "explore-windows"], None, minutes)
        return ok, message, calls

    def test_explore_minutes_passed_only_when_changed(self):
        _, _, calls = self.start(minutes=25)
        self.assertIn("-ExploreMinutes", calls[0])
        self.assertEqual(calls[0][calls[0].index("-ExploreMinutes") + 1], "25")
        _, _, calls = self.start(minutes=10)
        self.assertNotIn("-ExploreMinutes", calls[0])
        _, _, calls = self.start(minutes=25, steps=["run-all"])
        self.assertNotIn("-ExploreMinutes", calls[0])

    def test_busy_names_the_running_request(self):
        ok, message, _ = self.start(returncode=2, out="busy: rc-42")
        self.assertFalse(ok)
        self.assertIn("rc-42", message)


if __name__ == "__main__":
    unittest.main()
