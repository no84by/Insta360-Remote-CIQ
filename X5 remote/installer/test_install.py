"""Unit tests for install.py (no network, no USB): python3 -m unittest discover -s installer"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import install  # noqa: E402


def asset(name):
    return {"name": name, "browser_download_url": "https://example.invalid/" + name}


def release(tag, *names, draft=False, prerelease=False):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "assets": [asset(n) for n in names]}


class ReleaseSelection(unittest.TestCase):
    def test_newest_x5_release_by_version_not_order(self):
        rels = [
            release("x5-remote-v1.1.2", "insta360-x5-remote-1.1.2-descentmk351mm.prg", "SHA256SUMS"),
            release("v3.0.0", "upstream.prg", "SHA256SUMS"),                       # upstream tag
            release("x5-remote-v1.1.10", "insta360-x5-remote-1.1.10-descentmk351mm.prg", "SHA256SUMS",
                    prerelease=True),
            release("x5-remote-v1.1.4", "insta360-x5-remote-1.1.4-descentmk351mm.prg", "SHA256SUMS",
                    "x5-remote-installer.zip"),
        ]
        tag, prg, sums = install.pick_release(rels)
        self.assertEqual(tag, "x5-remote-v1.1.10")
        self.assertEqual(prg["name"], "insta360-x5-remote-1.1.10-descentmk351mm.prg")
        self.assertEqual(sums["name"], "SHA256SUMS")

    def test_skips_drafts_and_releases_without_the_files(self):
        rels = [
            release("x5-remote-v2.0.0", "insta360-x5-remote-2.0.0-descentmk351mm.prg", "SHA256SUMS", draft=True),
            release("x5-remote-v1.9.0", "insta360-x5-remote-1.9.0-descentmk351mm.prg"),          # no sums
            release("x5-remote-v1.8.0", "insta360-x5-remote-1.8.0-epix2pro51mm.prg", "SHA256SUMS"),
            release("x5-remote-v1.1.4", "insta360-x5-remote-1.1.4-descentmk351mm.prg", "SHA256SUMS"),
        ]
        self.assertEqual(install.pick_release(rels)[0], "x5-remote-v1.1.4")

    def test_none_when_nothing_fits(self):
        self.assertIsNone(install.pick_release([release("v1.0", "a.prg", "SHA256SUMS")]))
        self.assertIsNone(install.pick_release([]))

    def test_version_key(self):
        self.assertEqual(install.version_key("x5-remote-v1.1.4"), (1, 1, 4))
        self.assertEqual(install.version_key("x5-remote-v1.1.4-rc1"), ())
        self.assertEqual(install.version_key("v1.1.4"), ())


class Checksums(unittest.TestCase):
    data = b"prg bytes"
    name = "insta360-x5-remote-1.1.4-descentmk351mm.prg"

    def sums(self, digest=None):
        return f"{digest or hashlib.sha256(self.data).hexdigest()}  {self.name}\n"

    def test_parse_both_formats(self):
        d = hashlib.sha256(b"x").hexdigest()
        self.assertEqual(install.parse_sums(f"{d}  a.prg\n{d.upper()} *b.prg\nnoise\n"), {"a.prg": d, "b.prg": d})

    def test_match(self):
        install.verify(self.data, self.name, install.parse_sums(self.sums()))

    def test_mismatch_and_missing(self):
        with self.assertRaises(install.InstallError):
            install.verify(self.data, self.name, install.parse_sums(self.sums("0" * 64)))
        with self.assertRaises(install.InstallError):
            install.verify(self.data, "other.prg", install.parse_sums(self.sums()))

    def test_local_prg_checked_against_sums_next_to_it(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / self.name
            p.write_bytes(self.data)
            self.assertEqual(install.local_prg(Path(d)), p)
            with mock.patch.object(install, "say"):
                install.check_local(p)                         # no SHA256SUMS: used, unchecked
                (Path(d) / "SHA256SUMS").write_text(self.sums())
                install.check_local(p)
                (Path(d) / "SHA256SUMS").write_text(self.sums("1" * 64))
                with self.assertRaises(install.InstallError):
                    install.check_local(p)


class AppsFolder(unittest.TestCase):
    R = install.ROOT

    def test_found_under_garmin(self):
        entries = [(1, self.R, "Music", True), (2, self.R, "GARMIN", True), (3, 2, "Activity", True),
                   (4, 2, "Apps", True), (5, 1, "Apps", True), (6, 2, "Apps.txt", False)]
        self.assertEqual(install.find_apps(entries), 4)

    def test_case_insensitive_and_root_zero(self):
        self.assertEqual(install.find_apps([(9, 0, "Garmin", True), (10, 9, "APPS", True)]), 10)

    def test_missing(self):
        self.assertIsNone(install.find_apps([(2, self.R, "GARMIN", True), (3, 2, "Activity", True)]))
        self.assertIsNone(install.find_apps([(5, 7, "Apps", True)]))        # Apps not under GARMIN

    def test_stale_copies(self):
        names = ["INSTAREM.PRG", "instarem.prg", "insta360-x5-remote-1.1.2-descentmk351mm.prg",
                 "OTHER.PRG", "INSTAREM.TXT", "LOGS"]
        self.assertEqual(install.stale_names(names), names[:3])


class Dispatch(unittest.TestCase):
    def test_methods(self):
        self.assertEqual(install.methods_for("win32"), ["windows"])
        self.assertEqual(install.methods_for("darwin"), ["libmtp"])
        self.assertEqual(install.methods_for("linux"), ["gio", "libmtp"])

    def test_libmtp_paths(self):
        self.assertIn("/opt/homebrew/lib/libmtp.dylib", install.libmtp_paths("darwin"))
        self.assertIn("libmtp.so.9", install.libmtp_paths("linux"))

    def test_gio_roots(self):
        out = ("Drive(0): Descent\n  Volume(0): Descent Mk3i\n    activation_root=mtp://Garmin_Descent_Mk3i_0000/\n"
               "Mount(0): Descent Mk3i -> mtp://Garmin_Descent_Mk3i_0000/\n")
        self.assertEqual(install.gio_roots(out), ["mtp://Garmin_Descent_Mk3i_0000/"])

    def test_windows_script(self):
        s = install.windows_script("C:\\Temp\\it's\\INSTAREM.PRG", 1234, 300)
        self.assertIn("$src = 'C:\\Temp\\it''s\\INSTAREM.PRG'", s)
        self.assertIn("$size = 1234", s)
        self.assertIn("Child $g 'Apps'", s)
        self.assertIn("CopyHere", s)

    def test_check_only_never_touches_the_watch(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "insta360-x5-remote-1.1.4-descentmk351mm.prg"
            p.write_bytes(b"x")
            with mock.patch.object(install, "copy_to_watch") as copy, mock.patch.object(install, "say"):
                self.assertEqual(install.main(["--prg", str(p), "--check"]), 0)
                copy.assert_not_called()
                self.assertEqual(install.main(["--prg", str(Path(d) / "missing.prg")]), 1)

    def test_main_downloads_when_no_local_file(self):
        with mock.patch.object(install, "local_prg", return_value=None), \
                mock.patch.object(install, "download_latest", side_effect=install.InstallError("offline")) as dl, \
                mock.patch.object(install, "copy_to_watch") as copy, mock.patch.object(install, "say"):
            self.assertEqual(install.main([]), 1)
            dl.assert_called_once()
            copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
