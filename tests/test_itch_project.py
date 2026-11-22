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
        for text in ("https://itch.io/game/edit/123", "https://evil.com/tunugames/tunu-christmas", "tunugames", "a/b/c", "https://tunugames.itch.io/"):
            with self.assertRaises(ValueError, msg=text):
                itch.project_id(text)


if __name__ == "__main__":
    unittest.main()
