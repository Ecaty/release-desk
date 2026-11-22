"""butler install: only a butler archive from itch.io's hosts, signed by itch.io, replaces the tool folder.
Offline; the download and the Windows signature check are faked."""
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


GOOD = archive({"butler.exe": "new", "c7zip.dll": "x"})


class Install(unittest.TestCase):
    def run_install(self, zip_bytes, signed=True, starts=True, latest=b"15.32.0"):
        tmp = Path(tempfile.mkdtemp())
        tool = tmp / "butler"
        tool.mkdir()
        (tool / "butler.exe").write_text("old")
        self.ran = False

        def opener(url, timeout):
            return FakeResponse(latest if url.endswith("/LATEST") else zip_bytes)

        def version(exe):
            self.ran = True
            return "v15.32.0" if starts else ""

        sig = [{"name": "butler.exe", "status": "Valid" if signed else "HashMismatch", "subject": "CN=itch corp., O=itch corp., L=San Francisco, S=California, C=US", "issuer": "CN=Microsoft ID Verified CS AOC CA 04, O=Microsoft Corporation, C=US"}]
        with mock.patch.object(itch, "TOOL_DIR", tool), mock.patch.object(itch, "_open", opener), \
                mock.patch.object(itch, "version", version), mock.patch.object(itch, "signatures", lambda folder: sig):
            ok, message = itch.install()
        return ok, message, tool, tmp

    def test_good_archive_replaces_old_copy(self):
        ok, message, tool, tmp = self.run_install(GOOD)
        self.assertTrue(ok, message)
        self.assertEqual((tool / "butler.exe").read_text(), "new")
        for leftover in ("butler-download.zip", "butler-new", "butler-old"):
            self.assertFalse((tmp / leftover).exists(), leftover)

    def test_unsigned_is_never_run(self):
        ok, message, tool, _ = self.run_install(GOOD, signed=False)
        self.assertFalse(ok)
        self.assertIn("not signed by itch.io", message)
        self.assertFalse(self.ran)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

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
        ok, _, tool, _ = self.run_install(GOOD, starts=False)
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_odd_version_text_is_refused(self):
        ok, _, tool, _ = self.run_install(GOOD, latest=b"<html>nope</html>")
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_size_caps(self):
        with mock.patch.object(itch, "MAX_DOWNLOAD", 10):
            ok, message, tool, _ = self.run_install(GOOD)
        self.assertFalse(ok)
        self.assertIn("larger", message)
        with mock.patch.object(itch, "MAX_UNPACKED", 2):
            ok, message, tool, _ = self.run_install(GOOD)
        self.assertFalse(ok)
        self.assertEqual((tool / "butler.exe").read_text(), "old")

    def test_locked_old_copy_stays(self):
        real_rename = Path.rename

        def rename(self_path, target):
            if self_path.name == "butler":
                raise PermissionError("in use")
            return real_rename(self_path, target)

        with mock.patch.object(Path, "rename", rename):
            ok, message, tool, _ = self.run_install(GOOD)
        self.assertFalse(ok)
        self.assertIn("in use", message)
        self.assertEqual((tool / "butler.exe").read_text(), "old")


class Hosts(unittest.TestCase):
    def test_only_https_to_itch_hosts(self):
        self.assertTrue(itch.allowed_url("https://broth.itch.zone/butler/windows-amd64/LATEST"))
        self.assertTrue(itch.allowed_url("https://" + itch.MIRROR_HOST + "/build/1/archive"))
        self.assertFalse(itch.allowed_url("https://itchio-mirror.abc123.r2.cloudflarestorage.com/build/1/archive"))
        self.assertFalse(itch.allowed_url("https://broth.itch.zone:8443/butler"))
        self.assertFalse(itch.allowed_url("http://broth.itch.zone/butler"))
        self.assertFalse(itch.allowed_url("https://broth.itch.zone.evil.com/"))
        self.assertFalse(itch.allowed_url("https://other.r2.cloudflarestorage.com/x"))
        self.assertFalse(itch.allowed_url("file:///C:/butler.zip"))

    def test_signer_must_be_itch(self):
        good = {"name": "butler.exe", "status": "Valid", "subject": "CN=itch corp., O=itch corp., L=San Francisco, S=California, C=US", "issuer": "CN=Microsoft ID Verified CS AOC CA 04, O=Microsoft Corporation, C=US"}
        cases = [
            (dict(good), True),
            (dict(good, subject='CN=x, OU="y, O=itch corp.", O=other, C=US'), False),  # quoted part that once passed
            (dict(good, subject="CN=itch corp., O=itch corp., C=US"), False),  # not the full recorded subject
            (dict(good, issuer="CN=Some Other CA, O=Other, C=US"), False),
            (dict(good, issuer="CN=Microsoft ID Verified CS EOC CA 01, O=Microsoft Corporation, C=US"), True),  # rotated intermediate
            (dict(good, name="c7zip.dll"), False),  # no butler.exe among the signed files
            (dict(good, status="HashMismatch"), False),
        ]
        for sig, expected in cases:
            with mock.patch.object(itch, "signatures", lambda f, sig=sig: [sig]):
                self.assertEqual(itch.signed_by_itch("x")[0], expected, sig)

if __name__ == "__main__":
    unittest.main()
