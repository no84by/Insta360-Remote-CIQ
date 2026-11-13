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
            release("x5-remote-v1.1.10", "insta360-x5-remote-1.1.10-descentmk351mm.prg", "SHA256SUMS"),
            release("x5-remote-v1.2.0", "insta360-x5-remote-1.2.0-descentmk351mm.prg", "SHA256SUMS",
                    prerelease=True),
            release("x5-remote-v1.1.4", "insta360-x5-remote-1.1.4-descentmk351mm.prg", "SHA256SUMS",
                    "x5-remote-installer.zip"),
        ]
        tag, prg, sums = install.pick_release(rels)
        self.assertEqual(tag, "x5-remote-v1.1.10")
        self.assertEqual(prg["name"], "insta360-x5-remote-1.1.10-descentmk351mm.prg")
        self.assertEqual(sums["name"], "SHA256SUMS")
        self.assertEqual(install.pick_release(rels, pre=True)[0], "x5-remote-v1.2.0")

    def test_pre_release_only_with_pre(self):
        rels = [release("x5-remote-v1.2.0", "insta360-x5-remote-1.2.0-descentmk351mm.prg", "SHA256SUMS",
                        prerelease=True)]
        self.assertIsNone(install.pick_release(rels))
        self.assertEqual(install.pick_release(rels, pre=True)[0], "x5-remote-v1.2.0")

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
            with mock.patch.object(install, "say") as say:
                install.check_local(p)                         # no SHA256SUMS: used, with a warning
                self.assertIn("Warning", say.call_args[0][0])
                (Path(d) / "SHA256SUMS").write_text(self.sums())
                install.check_local(p)
                (Path(d) / "SHA256SUMS").write_text(self.sums("1" * 64))
                with self.assertRaises(install.InstallError):
                    install.check_local(p)

    def test_local_prg_newest_version_for_this_watch_only(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("insta360-x5-remote-1.1.10-descentmk351mm.prg", "insta360-x5-remote-1.1.9-descentmk351mm.prg",
                      "insta360-x5-remote-2.0.0-epix2pro51mm.prg", "zzz.prg"):
                (Path(d) / n).write_bytes(b"x")
            self.assertEqual(install.local_prg(Path(d)).name, "insta360-x5-remote-1.1.10-descentmk351mm.prg")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "other.prg").write_bytes(b"x")
            self.assertIsNone(install.local_prg(Path(d)))


SAMPLE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
  <Model>
    <PartNumber>006-B4223-00</PartNumber>
    <SoftwareVersion>1625</SoftwareVersion>
    <Description>Descent Mk3i - 51mm</Description>
  </Model>
  <Id>DEVICE-ID</Id>
</Device>"""


class WatchModel(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(install.parse_model(SAMPLE_XML), ("006-B4223-00", "Descent Mk3i - 51mm"))
        self.assertIsNone(install.parse_model(b"not xml"))
        self.assertIsNone(install.parse_model(b"<Device><Id>1</Id></Device>"))

    def test_target_by_part_or_description(self):
        self.assertTrue(install.is_mk3i_51("006-B4223-00", ""))
        self.assertTrue(install.is_mk3i_51("", "Descent\u2122 Mk3i 51mm"))
        self.assertFalse(install.is_mk3i_51("006-B4222-00", "Descent Mk3i - 43mm"))
        self.assertFalse(install.is_mk3i_51("006-B4000-00", "fenix 8 - 51mm"))

    def test_other_watch_gets_one_line_and_is_not_blocked(self):
        other = SAMPLE_XML.replace(b"006-B4223-00", b"006-B1234-00").replace(b"Descent Mk3i - 51mm", b"Other Watch")
        with mock.patch.object(install, "say") as say, mock.patch("builtins.input") as ask:
            install.note_model(SAMPLE_XML)
            install.note_model(None)
            install.note_model(b"garbage")
            self.assertEqual(say.call_count, 0)
            install.note_model(other)
            self.assertEqual(say.call_count, 1)
            self.assertIn("untested and used at your own risk", say.call_args[0][0])
            ask.assert_not_called()


class Errors(unittest.TestCase):
    def test_download_problems_become_friendly_errors(self):
        import subprocess
        import urllib.error
        for exc in (urllib.error.URLError("down"), OSError("disk"), subprocess.TimeoutExpired("curl", 1),
                    ValueError("bad json")):
            with mock.patch.object(install, "_fetch", side_effect=exc), mock.patch.object(install, "say"):
                with self.assertRaises(install.InstallError) as cm:
                    install.download_latest(Path(tempfile.gettempdir()))
                self.assertIn("Could not download", str(cm.exception))

    def test_bad_json_answer(self):
        with mock.patch.object(install, "_fetch", return_value=b"not json"), mock.patch.object(install, "say"):
            with self.assertRaises(install.InstallError):
                install.download_latest(Path(tempfile.gettempdir()))

    def test_wait_option(self):
        self.assertEqual(install.parse_wait("120"), 120)
        for bad in ("", "abc", "0", "-5", "1.5", None):
            with self.assertRaises(install.InstallError):
                install.parse_wait(bad)
        with mock.patch.object(install, "say") as say:
            self.assertEqual(install.main(["--wait", "soon", "--check"]), 1)
            self.assertIn("--wait", " ".join(str(c[0][0]) for c in say.call_args_list if c[0]))

    def test_wait_for(self):
        t = [0]
        clock = lambda: t[0]
        def sleep(s):
            t[0] += s
        calls = []
        with mock.patch.object(install, "say"):
            self.assertEqual(install.wait_for(lambda: calls.append(1) or (len(calls) >= 3 and "dev"), 60, "hint",
                                              clock, sleep), "dev")
            with self.assertRaises(install.InstallError) as cm:
                install.wait_for(lambda: None, 10, "unplug", clock, sleep)
        self.assertIn("unplug", str(cm.exception))


class GarminExpress(unittest.TestCase):
    def test_matches_the_app_not_its_service(self):
        run = mock.Mock(return_value=mock.Mock(returncode=1))
        with mock.patch.object(install.sys, "platform", "darwin"):
            self.assertFalse(install.garmin_express_running(run))
        self.assertEqual(run.call_args[0][0], ["pgrep", "-x", "Garmin Express"])

    def test_asks_once_then_continues(self):
        with mock.patch.object(install.sys, "platform", "darwin"), \
                mock.patch.object(install, "garmin_express_running", return_value=True), \
                mock.patch("builtins.input", return_value="") as ask, \
                mock.patch.object(install, "ensure_libmtp_mac", side_effect=install.InstallError("stop")):
            with self.assertRaises(install.InstallError):
                install.copy_to_watch(Path("x.prg"), 10)
        self.assertEqual(ask.call_count, 1)

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

    NAMES = ["INSTAREM.PRG", "instarem.prg", "insta360-x5-remote-1.1.2-descentmk351mm.prg",
             "OTHER.PRG", "INSTAREM.TXT", "LOGS", "XINSTAREM.PRG"]

    def test_stale_copies(self):
        self.assertEqual(install.stale_names(self.NAMES), self.NAMES[:3])

    def test_windows_filter_is_the_same_rule(self):
        import re
        s = install.windows_script("C:\\t\\INSTAREM.PRG", 1)
        m = re.search(r"\$stale = '([^']*)'", s)
        pattern = m.group(1).replace("''", "'")
        self.assertEqual(pattern, "^" + install.STALE_RE + "$")
        # the .NET -imatch of that pattern picks the same names as the Python rule
        self.assertEqual([n for n in self.NAMES if re.search(pattern, n, re.I)], install.stale_names(self.NAMES))

    def test_one_copy_of_the_right_size(self):
        install.check_copies([100], 100)
        for sizes in ([], [100, 100], [99]):
            with self.assertRaises(install.InstallError):
                install.check_copies(sizes, 100)


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
        s = install.windows_script("C:\\Temp\\it's\\INSTAREM.PRG", 1234)
        self.assertIn("$src = 'C:\\Temp\\it''s\\INSTAREM.PRG'", s)
        self.assertIn("$size = 1234", s)
        self.assertIn("Child $g 'Apps'", s)
        self.assertIn("size not reported by Windows", s)
        self.assertIn("exit 0 } else { exit 2 }", install.windows_probe_script())

    def test_uri_child(self):
        uris = ["mtp://Garmin_Descent/Internal%20Storage/", "mtp://Garmin_Descent/Other/"]
        self.assertEqual(install.uri_child(uris, "internal storage"), "mtp://Garmin_Descent/Internal%20Storage/")
        self.assertEqual(install.uri_child(["mtp://x/s/Garmin"], "GARMIN"), "mtp://x/s/Garmin/")
        self.assertIsNone(install.uri_child(uris, "GARMIN"))

    def test_linux_uses_gio_only_with_an_mtp_device(self):
        mtp = mock.Mock()
        mtp.open_watch.return_value = "dev"
        with mock.patch.object(install, "gio_has_mtp", return_value=False):
            self.assertEqual(install.linux_probe(mtp, True)(), ("libmtp", "dev"))
            self.assertIsNone(install.linux_probe(None, True)())
        with mock.patch.object(install, "gio_has_mtp", return_value=True), \
                mock.patch.object(install, "gio_apps", return_value="mtp://x/s/GARMIN/Apps/"):
            self.assertEqual(install.linux_probe(mtp, True)(), ("gio", "mtp://x/s/GARMIN/Apps/"))
        mtp.open_watch.return_value = None
        with mock.patch.object(install, "gio_has_mtp", return_value=False):
            self.assertIsNone(install.linux_probe(mtp, True)())

    def test_linux_without_any_mtp_support_prints_the_hint(self):
        with mock.patch.object(install.sys, "platform", "linux"), \
                mock.patch.object(install, "load_libmtp", return_value=None), \
                mock.patch.object(install.shutil, "which", return_value=None):
            with self.assertRaises(install.InstallError) as cm:
                install.copy_to_watch(Path("x.prg"), 10)
        self.assertIn("MTP support", str(cm.exception))

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


class LibmtpCopy(unittest.TestCase):
    """copy_libmtp against a fake libmtp: delete failures stop the copy; the result is checked."""

    def fake(self, delete_rc=0, after=None):
        R = install.ROOT
        mtp = mock.Mock()
        mtp.C = mock.Mock()
        mtp.File = mock.Mock()
        lib = mtp.lib
        lib.LIBMTP_Delete_Object.return_value = delete_rc
        lib.LIBMTP_Send_File_From_File.return_value = 0
        storage = mock.Mock()
        storage.contents.id = 1
        storage.contents.next = None
        dev = mock.Mock()
        dev.contents.storage = storage
        listings = {R: [(2, R, "GARMIN", True, 0)], 2: [(4, 2, "Apps", True, 0), (5, 2, "GarminDevice.xml", False, 9)],
                    4: [(7, 4, "INSTAREM.PRG", False, 50)]}
        state = {"sent": False}

        def entries(_dev, _sid, parent):
            if parent == 4 and state["sent"]:
                return after
            return listings.get(parent, [])

        def send(*a):
            state["sent"] = True
            return 0
        def read(_dev, item, path, *_):
            Path(path.decode()).write_bytes(SAMPLE_XML if item == 5 else b"")
            return 0
        mtp.entries.side_effect = entries
        lib.LIBMTP_Send_File_From_File.side_effect = send
        lib.LIBMTP_Get_File_To_File.side_effect = read
        return mtp, dev

    def prg(self, d, size):
        p = Path(d) / "a.prg"
        p.write_bytes(b"x" * size)
        return p

    def test_delete_failure_aborts_before_sending(self):
        mtp, dev = self.fake(delete_rc=1)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(install, "say"):
            with self.assertRaises(install.InstallError) as cm:
                install.copy_libmtp(self.prg(d, 100), mtp, dev)
        self.assertIn("Could not remove", str(cm.exception))
        mtp.lib.LIBMTP_Send_File_From_File.assert_not_called()
        mtp.lib.LIBMTP_Release_Device.assert_called_once()

    def test_success_and_duplicate_check(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(install, "say"):
            mtp, dev = self.fake(after=[(8, 4, "INSTAREM.PRG", False, 100)])
            install.copy_libmtp(self.prg(d, 100), mtp, dev)
            mtp.lib.LIBMTP_Delete_Object.assert_called_once_with(dev, 7)
            self.assertEqual(mtp.lib.LIBMTP_Get_File_To_File.call_args[0][1], 5)   # model read
            mtp, dev = self.fake(after=[(8, 4, "INSTAREM.PRG", False, 100), (9, 4, "instarem.prg", False, 100)])
            with self.assertRaises(install.InstallError):
                install.copy_libmtp(self.prg(d, 100), mtp, dev)


class BusyWatch(unittest.TestCase):
    def test_present_but_unopenable_is_reported(self):
        lib = mock.Mock()
        mtp = install.Mtp.__new__(install.Mtp)
        C, RawDevice, Device, File = install._mtp_types()
        mtp.C, mtp.RawDevice, mtp.lib, mtp.open_fails = C, RawDevice, lib, 0
        raw = (RawDevice * 1)()
        raw[0].device_entry.vendor_id = install.GARMIN_VID

        def detect(pp, pn):
            C.cast(pp, C.POINTER(C.POINTER(RawDevice)))[0] = C.cast(raw, C.POINTER(RawDevice))
            C.cast(pn, C.POINTER(C.c_int))[0] = 1
            return 0
        lib.LIBMTP_Detect_Raw_Devices.side_effect = detect
        lib.LIBMTP_Open_Raw_Device_Uncached.return_value = None
        self.assertIsNone(mtp.open_watch())
        self.assertIsNone(mtp.open_watch())
        with self.assertRaises(install.InstallError) as cm:
            mtp.open_watch()
        self.assertIn("another program", str(cm.exception))
        self.assertEqual(lib.LIBMTP_FreeMemory.call_count, 3)
