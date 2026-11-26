"""Every setup guide: at most 4 short lines, the first one a direct link or a Go button, links over https."""
import unittest

from desk import guides, itch, play


def all_guides():
    out = [("itch new page", itch._guide_new_page()), ("itch edit", itch._guide_edit_page("", "x")),
           ("itch edit link", itch._guide_edit_page("https://itch.io/game/edit/1", "x"))]
    out += [(name, g) for name, g in vars(play).items() if name.endswith("_GUIDE") or name.startswith("APP_CONTENT_GUIDE")]
    out += [(f"{store}: {title}", g) for store, steps in guides.GUIDES.items() for title, g in steps.items()]
    return out


class Guides(unittest.TestCase):
    def test_short_and_linked(self):
        found = all_guides()
        self.assertGreater(len(found), 30)
        for name, g in found:
            self.assertTrue(1 <= len(g) <= 4, name)
            self.assertTrue(g[0].get("link") or g[0].get("go"), name)
            for line in g:
                self.assertTrue(line["text"].strip(), name)
                self.assertLessEqual(len(line["text"]), 160, (name, line["text"]))
                self.assertTrue(line.get("link", "https://").startswith("https://"), (name, line))

    def test_applied_by_title_without_replacing(self):
        status = {"steps": [{"title": "Build account"}, {"title": "Review by Valve", "guide": [{"text": "own"}]}, {"title": "Other"}]}
        guides.apply("steam", status)
        self.assertEqual(status["steps"][0]["guide"], guides.GUIDES["steam"]["Build account"])
        self.assertEqual(status["steps"][1]["guide"], [{"text": "own"}])
        self.assertNotIn("guide", status["steps"][2])


if __name__ == "__main__":
    unittest.main()
