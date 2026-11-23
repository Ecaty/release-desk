"""itch.io project id: user/game or the page address."""
import unittest

from desk import itch


class ProjectId(unittest.TestCase):
    def test_forms(self):
        for text in ("tunugames/tunu-christmas", "https://tunugames.itch.io/tunu-christmas", "tunugames.itch.io/tunu-christmas",
                     "https://TunuGames.itch.io/tunu-christmas/", "http://www.tunugames.itch.io/tunu-christmas?secret=x", " tunugames/tunu-christmas "):
            self.assertEqual(itch.project_id(text), "tunugames/tunu-christmas", text)
        self.assertEqual(itch.project_id(""), "")

    def test_refused(self):
        for text in ("https://itch.io/game/edit/123", "https://evil.com/tunugames/tunu-christmas", "tunugames", "a/b/c", "https://tunugames.itch.io/",
                     "www.itch.io/game", "https://www.itch.io/game", "www/game", "-x/game", "user/-x", "tunugames/tunu-chrıstmas", "Kelvin/game"):
            with self.assertRaises(ValueError, msg=text):
                itch.project_id(text)


    def test_settings_never_pass_an_unusable_value(self):
        class P:
            def __init__(self, value):
                self.value = value

            def read(self, rel, default=None):
                return {"itch": {"project": self.value}}
        self.assertEqual(itch.settings(P("https://tunugames.itch.io/tunu-christmas"))["project"], "tunugames/tunu-christmas")
        for bad in ("-x", "--help", "https://evil.com/a/b", "www/game"):
            self.assertEqual(itch.settings(P(bad))["project"], "", bad)


class PageAndGuides(unittest.TestCase):
    def test_page_url(self):
        self.assertEqual(itch.page_url("tunugames/tunu-christmas"), "https://tunugames.itch.io/tunu-christmas")
        self.assertEqual(itch.page_url(""), "")

    def test_guides_are_well_formed(self):
        from desk import play
        guides = [itch._guide_new_page(), itch._guide_edit_page("x"), play.ACCOUNT_GUIDE, play.CREATE_APP_GUIDE, play.SERVICE_ACCOUNT_GUIDE]
        for g in guides:
            for line in g:
                self.assertTrue(line["text"].strip())
                self.assertTrue(line.get("link", "https://").startswith("https://"), line)


if __name__ == "__main__":
    unittest.main()
