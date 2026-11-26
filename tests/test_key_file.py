"""Choosing the Play key file: only a service account .json outside every repository and synced folder is accepted,
and no answer ever carries the file's path or contents. Made-up files only; the registry and the dialog are mocked."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desk import playapi, server

SECRET = "made-up-private-key-for-tests"
FAKE = {"type": "service_account", "private_key": SECRET, "client_email": "x@y.iam.gserviceaccount.com",
        "token_uri": "https://evil.example/token"}


class KeyFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = mock.patch.dict("os.environ", {"OneDrive": str(self.dir / "OneDrive")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write(self, name, data):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def test_service_account_file_accepted(self):
        self.assertEqual(playapi.check_key_file(self.write("keys/k.json", FAKE)), "")

    def test_refused_without_path_or_contents(self):
        (self.dir / "repo" / ".git").mkdir(parents=True)
        self.write("worktree/.git", "gitdir: somewhere")  # a worktree's .git is a file
        cases = [self.dir / "missing.json", self.write("k.txt", FAKE), self.write("repo/Store/k.json", FAKE),
                 self.write("worktree/sub/k.json", FAKE), self.write("OneDrive/keys/k.json", FAKE),
                 self.write("Dropbox/k.json", FAKE), self.write("bad.json", "{not json " + SECRET),
                 self.write("other.json", {"type": "authorized_user", "private_key": SECRET}),
                 self.write("list.json", [1]), self.write("nokey.json", {"type": "service_account"})]
        for path in cases:
            why = playapi.check_key_file(path)
            self.assertTrue(why, path)
            self.assertNotIn(SECRET, why)
            self.assertNotIn(str(self.dir), why)
            self.assertNotIn(path.name, why)

    def test_unreadable_folder_is_refused_not_raised(self):
        with mock.patch.object(Path, "is_file", side_effect=PermissionError("denied")):
            self.assertTrue(playapi.check_key_file(self.dir / "k.json"))

    def test_path_comes_from_the_user_variable_when_the_process_has_none(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(playapi, "_user_variable", lambda: "C:/k.json"):
            self.assertEqual(playapi.key_path(), "C:/k.json")
        with mock.patch.dict("os.environ", {playapi.ENV: "C:/env.json"}), mock.patch.object(playapi, "_user_variable", lambda: "C:/k.json"):
            self.assertEqual(playapi.key_path(), "C:/env.json")

    def test_a_path_set_by_hand_is_checked_too(self):
        bad = self.write("repo2/.git/x", "")  # makes repo2 a repository
        inside = self.write("repo2/k.json", FAKE)
        with mock.patch.object(playapi, "key_path", lambda: str(inside)):
            self.assertFalse(playapi.account_state()["found"])
            with self.assertRaises(ValueError):
                playapi.Play("com.someone.game")
        good = self.write("keys/k.json", FAKE)
        with mock.patch.object(playapi, "key_path", lambda: str(good)), mock.patch.object(playapi, "private_key", lambda pem: (1, 1)):
            self.assertTrue(playapi.account_state()["found"])
            self.assertEqual(playapi.Play("com.someone.game")._token_uri, "https://oauth2.googleapis.com/token")
        self.assertTrue(bad.exists())

    def test_save_key_path_writes_the_user_variable(self):
        good = self.write("keys/k.json", FAKE)
        written = {}
        fake = mock.MagicMock()
        fake.HKEY_CURRENT_USER, fake.KEY_SET_VALUE, fake.REG_SZ = "HKCU", 2, 1
        fake.SetValueEx.side_effect = lambda k, name, _r, _t, value: written.update({name: value})
        with mock.patch.dict("sys.modules", {"winreg": fake}), mock.patch.dict("os.environ", {}):
            playapi.save_key_path(good)
            self.assertEqual(written[playapi.ENV], str(good.resolve()))
            self.assertEqual(playapi.key_path(), str(good.resolve()))

    def test_pick_key_file_answers_with_fixed_messages(self):
        good = self.write("keys/k.json", FAKE)
        done = subprocess.CompletedProcess([], 0, stdout=str(good) + "\n", stderr="")
        with mock.patch("subprocess.run", return_value=done), mock.patch.object(playapi, "save_key_path", lambda p: p):
            self.assertTrue(server.pick_key_file()["ok"])
        with mock.patch("subprocess.run", return_value=done), mock.patch.object(playapi, "save_key_path", side_effect=OSError("C:/secret/place")):
            r = server.pick_key_file()
            self.assertFalse(r["ok"]); self.assertNotIn("secret", r["message"])
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 600)):
            self.assertFalse(server.pick_key_file()["ok"])
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout="", stderr="")):
            self.assertEqual(server.pick_key_file()["message"], "No file chosen.")


if __name__ == "__main__":
    unittest.main()
