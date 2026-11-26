"""Every setup guide: at most 4 short lines, the first one a direct link or a Go button, links over https.
Checked on the real steps of every store (built for a small made-up Unity project), so inline guides count too,
and every title in desk/guides.py must name a real step."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desk import guides, server
from desk.project import Project

SETTINGS = """%YAML 1.1
PlayerSettings:
  companyName: Someone
  productName: Some Game
  bundleVersion: 1.0
  applicationIdentifier:
    Android: com.someone.somegame
"""


def statuses():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "ProjectSettings").mkdir()
        (root / "ProjectSettings" / "ProjectSettings.asset").write_text(SETTINGS, encoding="utf-8")
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n", encoding="utf-8")
        (root / "Store").mkdir()
        p = Project(root)
        with mock.patch("subprocess.run", side_effect=OSError("no tools in tests")):
            return {sid: server.store_status(sid, p) for sid in server.RAW}


class Guides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.all = statuses()

    def test_short_and_linked(self):
        count = 0
        for sid, status in self.all.items():
            for step in status["steps"]:
                g = step.get("guide")
                if not g:
                    continue
                count += 1
                name = f"{sid}: {step['title']}"
                self.assertTrue(1 <= len(g) <= 4, name)
                self.assertTrue(g[0].get("link") or g[0].get("go"), name)
                for line in g:
                    self.assertTrue(line["text"].strip(), name)
                    self.assertLessEqual(len(line["text"]), 170, (name, line["text"]))
                    self.assertTrue(line.get("link", "https://").startswith("https://"), (name, line))
        self.assertGreater(count, 30)

    def test_every_guide_title_is_a_real_step(self):
        for sid, titles in guides.GUIDES.items():
            real = {s["title"] for s in self.all[sid]["steps"]}
            for title in titles:
                self.assertIn(title, real, f"{sid}: {title}")

    def test_applied_by_title_without_replacing(self):
        status = {"steps": [{"title": "Build account"}, {"title": "Review by Valve", "guide": [{"text": "own"}]}, {"title": "Other"}]}
        guides.apply("steam", status)
        self.assertEqual(status["steps"][0]["guide"], guides.GUIDES["steam"]["Build account"])
        self.assertEqual(status["steps"][1]["guide"], [{"text": "own"}])
        self.assertNotIn("guide", status["steps"][2])


if __name__ == "__main__":
    unittest.main()
