"""itch.io project id: user/game or the page address."""
import unittest
from unittest import mock

from desk import itch


class ProjectId(unittest.TestCase):
    def test_forms(self):
        for text in ("someone/some-game", "https://someone.itch.io/some-game", "someone.itch.io/some-game",
                     "https://SomeOne.itch.io/some-game/", "http://www.someone.itch.io/some-game?secret=x", " someone/some-game "):
            self.assertEqual(itch.project_id(text), "someone/some-game", text)
        self.assertEqual(itch.project_id(""), "")

    def test_refused(self):
        for text in ("https://itch.io/game/edit/123", "https://evil.com/someone/some-game", "someone", "a/b/c", "https://someone.itch.io/",
                     "www.itch.io/game", "https://www.itch.io/game", "www/game", "-x/game", "user/-x", "someone/some-gıme", "Kelvin/game"):
            with self.assertRaises(ValueError, msg=text):
                itch.project_id(text)


    def test_settings_never_pass_an_unusable_value(self):
        class P:
            def __init__(self, value):
                self.value = value

            def read(self, rel, default=None):
                return {"itch": {"project": self.value}}
        self.assertEqual(itch.settings(P("https://someone.itch.io/some-game"))["project"], "someone/some-game")
        for bad in ("-x", "--help", "https://evil.com/a/b", "www/game"):
            self.assertEqual(itch.settings(P(bad))["project"], "", bad)


class PageAndGuides(unittest.TestCase):
    def test_page_url(self):
        self.assertEqual(itch.page_url("someone/some-game"), "https://someone.itch.io/some-game")
        self.assertEqual(itch.page_url(""), "")

    def test_guides_are_well_formed(self):
        from desk import play
        guides = [itch._guide_new_page(), itch._guide_edit_page("", "x"), itch._guide_edit_page("https://itch.io/game/edit/1", "x"), play.ACCOUNT_GUIDE, play.CREATE_APP_GUIDE, play.SERVICE_ACCOUNT_GUIDE]
        for g in guides:
            for line in g:
                self.assertTrue(line["text"].strip())
                self.assertTrue(line.get("link", "https://").startswith("https://"), line)


class EditLink(unittest.TestCase):
    def setUp(self):
        itch._EDIT.clear()

    def test_found_from_uploaded_channel(self):
        chans = [{"name": "windows", "upload": {"id": 9, "gameId": 42}}]
        with mock.patch.object(itch, "_channels", lambda pid: chans):
            self.assertEqual(itch.edit_url("someone/some-game"), "https://itch.io/game/edit/42")

    def test_none_before_first_push_and_waits_before_retrying(self):
        calls = []
        def none(pid):
            calls.append(1)
            return []
        with mock.patch.object(itch, "_channels", none):
            self.assertEqual(itch.edit_url("someone/some-game"), "")
            self.assertEqual(itch.edit_url("someone/some-game"), "")
        self.assertEqual(len(calls), 1)
        self.assertEqual(itch.edit_url(""), "")

    def test_odd_ids_ignored(self):
        with mock.patch.object(itch, "_channels", lambda pid: [{"upload": {"gameId": "42/../x"}}]):
            self.assertEqual(itch.edit_url("someone/some-game"), "")


class Consoles(unittest.TestCase):
    """The login consoles reach cmd as written (a list once turned the quotes into \" and cmd refused the path)."""
    def test_quotes_reach_cmd_as_written(self):
        from desk import microsoft
        exe = r"C:\Users\x\AppData\Roaming\release-desk\butler\butler.exe"
        for module, fn, tool in ((itch, "login", "butler"), (microsoft, "setup_cli", "msstore")):
            with mock.patch.object(module, tool, lambda: exe), mock.patch.object(module.subprocess, "Popen") as popen:
                getattr(module, fn)("x")
            line = popen.call_args[0][0]
            self.assertIsInstance(line, str)
            self.assertNotIn('\\"', line)
            self.assertIn(f'"{exe}"', line)
            self.assertTrue(line.startswith('cmd /s /c "') and line.endswith('"'))


if __name__ == "__main__":
    unittest.main()
