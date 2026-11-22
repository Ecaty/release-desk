"""butler install: only a real butler archive that starts replaces the tool folder. Offline; the download is faked."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from desk import itch


def archive(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Install(unittest.TestCase):
    def run_install(self, zip_bytes, starts=True, latest=b"15.32.0"):
        tmp = Path(tempfile.mkdtemp())
        tool = tmp / "butler"
        tool.mkdir()
        (tool / "butler.exe").write_text("old")

        def urlopen(url, timeout=None):
            return FakeResponse(latest if url.endswith("/LATEST") else zip_bytes)

        with mock.patch.object(itch, "TOOL_DIR", tool), mock.patch.object(itch.urllib.request, "urlopen", urlopen), \
                mock.patch.object(itch, "version", lambda exe: "v15.32.0" if starts else ""):
            ok, message = itch.install()
        return ok, message, tool, tmp

    def test_good_archive_replaces_old_copy(self):
        ok, message, tool, tmp = self.run_install(archive({"butler.exe": "new", "c7zip.dll": "x"}))
        self.assertTrue(ok, message)
        self.assertEqual((tool / "butler.exe").read_text(), "new")
        self.assertFalse((tmp / "butler-download.zip").exists())
        self.assertFalse((tmp / "butler-new").exists())

    def test_archive_without_butler_keeps_old_copy(self):
        ok, _, tool, _ = self.run_install(archive({"readme.txt": "x"}))
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_path_escape_is_refused(self):
        ok, _, tool, tmp = self.run_install(archive({"butler.exe": "new", "../evil.txt": "x"}))
        self.assertFalse(ok)
        self.assertFalse((tmp / "evil.txt").exists())
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_butler_that_does_not_start_keeps_old_copy(self):
        ok, _, tool, _ = self.run_install(archive({"butler.exe": "new"}), starts=False)
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_odd_version_text_is_refused(self):
        ok, _, tool, _ = self.run_install(archive({"butler.exe": "new"}), latest=b"<html>nope</html>")
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")


if __name__ == "__main__":
    unittest.main()
