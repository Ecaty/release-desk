"""By-hand steps the desk cannot check can be ticked Done by the user; desk-checked steps cannot."""
import unittest

from desk import ticks


class FakeProject:
    def __init__(self):
        self.files = {}

    def read(self, rel, default=None):
        return self.files.get(rel, default)

    def write(self, rel, data):
        self.files[rel] = data


def status():
    return {"steps": [
        {"title": "Play developer account", "state": "todo", "kind": "hand"},
        {"title": "Android package", "state": "todo", "kind": "hand", "go": "play/keys/x"},
        {"title": "Release AAB", "state": "todo", "kind": "desk"},
        {"title": "Found by the desk", "state": "ok", "kind": "hand"},
    ]}


class Ticks(unittest.TestCase):
    def test_tick_and_untick(self):
        p = FakeProject()
        s = ticks.apply(p, "play", status())
        self.assertEqual([x.get("tick", False) for x in s["steps"]], [True, False, False, False])
        ticks.save(p, "play", status(), "Play developer account", True)
        s = ticks.apply(p, "play", status())
        self.assertEqual(s["steps"][0]["state"], "ok")
        self.assertTrue(s["steps"][0]["tick"])
        self.assertEqual(ticks.apply(p, "itch", status())["steps"][0]["state"], "todo")  # per store
        ticks.save(p, "play", status(), "Play developer account", False)
        self.assertEqual(ticks.apply(p, "play", status())["steps"][0]["state"], "todo")

    def test_only_by_hand_steps_without_a_desk_check(self):
        p = FakeProject()
        for title in ("Android package", "Release AAB", "Not a step"):
            with self.assertRaises(ValueError):
                ticks.save(p, "play", status(), title, True)
        self.assertEqual(p.files, {})

    def test_odd_file_counts_as_no_ticks(self):
        for content in ([], "x", {"play": "Play developer account"}, {"play": [1, None]}):
            p = FakeProject()
            p.files[ticks.FILE] = content
            self.assertEqual(ticks.apply(p, "play", status())["steps"][0]["state"], "todo")
            ticks.save(p, "play", status(), "Play developer account", True)
            self.assertEqual(p.files[ticks.FILE]["play"], ["Play developer account"])

    def test_file_written_whole(self):
        import tempfile
        from pathlib import Path
        from desk.project import Project
        with tempfile.TemporaryDirectory() as d:
            proj = Project.__new__(Project)
            proj.store = Path(d)
            proj.write(ticks.FILE, {"play": ["a"]})
            self.assertEqual(proj.read(ticks.FILE), {"play": ["a"]})
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()), [ticks.FILE])


if __name__ == "__main__":
    unittest.main()
