"""Choosing the Play key file: only a service account .json outside every repository is accepted. Made-up files only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desk import playapi

FAKE = {"type": "service_account", "private_key": "not a real key", "client_email": "x@y.iam.gserviceaccount.com"}


class KeyFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return p

    def test_service_account_file_accepted(self):
        self.assertEqual(playapi.check_key_file(self.write("keys/k.json", FAKE)), "")

    def test_refused(self):
        (self.dir / "repo" / ".git").mkdir(parents=True)
        cases = [self.dir / "missing.json", self.write("k.txt", FAKE), self.write("repo/Store/k.json", FAKE),
                 self.write("bad.json", "{not json"), self.write("other.json", {"type": "authorized_user"}),
                 self.write("list.json", [1]), self.write("nokey.json", {"type": "service_account"})]
        for path in cases:
            self.assertTrue(playapi.check_key_file(path), path)

    def test_path_comes_from_the_user_variable_when_the_process_has_none(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(playapi, "_user_variable", lambda: "C:/k.json"):
            self.assertEqual(playapi.key_path(), "C:/k.json")
        with mock.patch.dict("os.environ", {playapi.ENV: "C:/env.json"}), mock.patch.object(playapi, "_user_variable", lambda: "C:/k.json"):
            self.assertEqual(playapi.key_path(), "C:/env.json")


if __name__ == "__main__":
    unittest.main()
