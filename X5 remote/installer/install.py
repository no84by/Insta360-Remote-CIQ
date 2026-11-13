"""Insta360 X5 Remote - installer for the Garmin Descent Mk3i 51 mm.

Started by the double-click file for your system (or: python3 install.py). It
  1. downloads the newest X5 Remote release (.prg) from GitHub and checks it against the
     release's SHA256SUMS (or uses a .prg next to this file, or --prg FILE, for offline use);
  2. waits for the watch on USB;
  3. copies the app to the watch's GARMIN/Apps folder as INSTAREM.PRG, replacing an older copy,
     and checks the copy.
Then unplug the watch: the app appears in the widget loop.

Nothing is installed on this computer. On macOS the copy needs libmtp (Homebrew); on Linux GVfs
(gio) or libmtp. Windows needs nothing extra. No data is sent anywhere except the download from
GitHub.

Options: --prg FILE (install this file), --wait SECONDS (how long to wait for the watch, default
300), --check (only download and verify, do not touch the watch).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "no84by/Insta360-Remote-CIQ"
TAG_PREFIX = "x5-remote-v"
DEVICE = "descentmk351mm"
TARGET = "INSTAREM.PRG"          # file name on the watch
GARMIN_VID = 0x091E
ROOT = 0xFFFFFFFF                # libmtp: parent id of the storage root
# Files in GARMIN/Apps that are this app: an older INSTAREM.PRG, or a copy installed by hand under
# the release file name (two copies of one app confuse the watch). Used by every copy method,
# also as the PowerShell filter on Windows (.NET regex, same syntax).
STALE_RE = r"(?:INSTAREM\.PRG|insta360-x5-remote.*\.prg)"
PRG_RE = r"insta360-x5-remote-(\d+(?:\.\d+)*)-" + DEVICE + r"\.prg"
OPEN_FAILS = 3                   # failed opens of a present watch before "another program uses it"
UNPLUG_HINT = "If nothing happens, unplug the watch and plug it in again."
BUSY_MSG = ("The watch is connected but another program is using it. Quit Garmin Express and any "
            "other app that reads the watch (an MTP app or file manager window), unplug the watch, "
            "plug it in again and start this installer again.")


class InstallError(Exception):
    """A problem the user can act on; the message says what to do."""


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --- versions, release selection and verification ----------------------------------------------

def parse_version(text: str, pattern: str) -> tuple:
    """Version tuple from `text` when it matches `pattern` (one group: 1.2.3), else ()."""
    m = re.fullmatch(pattern, text or "", re.I)
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def version_key(tag: str) -> tuple:
    """x5-remote-v1.1.4 -> (1, 1, 4); anything else -> ()."""
    return parse_version(tag, re.escape(TAG_PREFIX) + r"(\d+(?:\.\d+)*)")


def prg_version(name: str) -> tuple:
    """insta360-x5-remote-1.1.4-descentmk351mm.prg -> (1, 1, 4); other files (other watches) -> ()."""
    return parse_version(name, PRG_RE)


def pick_release(releases: list) -> tuple[str, dict, dict] | None:
    """Newest x5-remote-v* release that has the watch's .prg and a SHA256SUMS file.

    The repository also carries upstream releases with other tags; drafts are skipped, and the
    order of the list does not matter (pre-releases count, /releases/latest is not used).
    """
    best = None
    for rel in releases:
        key = version_key(rel.get("tag_name", ""))
        if not key or rel.get("draft"):
            continue
        assets = rel.get("assets") or []
        prg = next((a for a in assets if prg_version(a.get("name", ""))), None)
        sums = next((a for a in assets if a.get("name") == "SHA256SUMS"), None)
        if prg and sums and (best is None or key > best[0]):
            best = (key, rel["tag_name"], prg, sums)
    return best[1:] if best else None


def parse_sums(text: str) -> dict:
    """SHA256SUMS lines `<hex>  <name>` (or `<hex> *<name>`) -> {name: hex}."""
    out = {}
    for line in text.splitlines():
        m = re.fullmatch(r"\s*([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def verify(data: bytes, name: str, sums: dict) -> None:
    want = sums.get(name)
    if not want:
        raise InstallError(f"{name} is not listed in SHA256SUMS; not installing it.")
    if hashlib.sha256(data).hexdigest() != want:
        raise InstallError(f"{name} does not match its checksum (download damaged?); not installing it.")


def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "x5-remote-installer",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:  # noqa: S310
            return r.read()
    except Exception as first:  # e.g. python.org's macOS Python without certificates: use curl
        curl = shutil.which("curl") or shutil.which("curl.exe")
        if not curl:
            raise first
        r = subprocess.run([curl, "-fsSL", "-A", "x5-remote-installer", url], capture_output=True, timeout=timeout * 4)
        if r.returncode != 0:
            raise first
        return r.stdout


def download_latest(dest: Path) -> Path:
    say("Looking for the newest X5 Remote release on GitHub...")
    try:
        pick = pick_release(json.loads(_fetch(f"https://api.github.com/repos/{REPO}/releases?per_page=50")))
        if not pick:
            raise InstallError("No X5 Remote release with a file for the Descent Mk3i 51 mm was found.")
        tag, prg, sums = pick
        say(f"Downloading {prg['name']} ({tag})...")
        data = _fetch(prg["browser_download_url"], timeout=60)
        verify(data, prg["name"], parse_sums(_fetch(sums["browser_download_url"]).decode("utf-8", "replace")))
        out = dest / prg["name"]
        out.write_bytes(data)
    except InstallError:
        raise
    except Exception as e:  # offline, timeout, rate limit, bad answer, disk full
        raise InstallError(f"Could not download the app from GitHub ({e.__class__.__name__}). Check the "
                           "internet connection and start again, or put the .prg and SHA256SUMS from the "
                           "release next to this installer.")
    say("Download checked (SHA-256 matches the release).")
    return out


def local_prg(here: Path) -> Path | None:
    """The newest release .prg for the Descent Mk3i 51 mm next to the installer (offline use)."""
    found = [p for p in here.glob("*.prg") if prg_version(p.name)]
    return max(found, key=lambda p: prg_version(p.name)) if found else None


def check_local(prg: Path) -> None:
    """Verify a local .prg against a SHA256SUMS next to it; warn when there is none."""
    sums_file = prg.parent / "SHA256SUMS"
    if not sums_file.exists():
        say(f"Warning: no SHA256SUMS next to {prg.name}, so the file cannot be checked. Installing it anyway.")
        return
    verify(prg.read_bytes(), prg.name, parse_sums(sums_file.read_text("utf-8", "replace")))
    say(f"Using {prg.name} (SHA-256 matches SHA256SUMS).")


def parse_wait(text: str) -> int:
    try:
        v = int(text)
    except (TypeError, ValueError):
        v = 0
    if v <= 0:
        raise InstallError(f"--wait needs a number of seconds, for example --wait 300 (got {text!r}).")
    return v


# --- the watch's folders -----------------------------------------------------------------------

def find_apps(entries: list) -> int | None:
    """Id of GARMIN/Apps from (id, parent_id, name, is_folder) entries; root entries have parent ROOT."""
    garmin = [e[0] for e in entries if e[3] and e[1] in (ROOT, 0) and e[2].upper() == "GARMIN"]
    for e in entries:
        if e[3] and e[1] in garmin and e[2].upper() == "APPS":
            return e[0]
    return None


def stale_names(names: list) -> list:
    return [n for n in names if re.fullmatch(STALE_RE, n, re.I)]


def check_copies(sizes: list, size: int) -> None:
    """Sizes of every INSTAREM.PRG in Apps after the copy: exactly one, of the right size."""
    if len(sizes) != 1:
        raise InstallError(f"Found {len(sizes)} copies of {TARGET} on the watch instead of one. "
                           "Unplug and plug in the watch, and start again.")
    if sizes[0] != size:
        raise InstallError("The copy on the watch does not have the right size. Start again.")


def methods_for(platform: str) -> list:
    """Copy methods to try, in order, for sys.platform."""
    if platform.startswith("win"):
        return ["windows"]
    if platform == "darwin":
        return ["libmtp"]
    return ["gio", "libmtp"]


def wait_for(probe, wait_s: int, hint: str, clock=time.monotonic, sleep=time.sleep):
    """Call probe() every 2 s until it returns something (returned) or wait_s passes (InstallError).
    probe may raise InstallError to stop early."""
    t0 = clock()
    shown = -1
    while True:
        got = probe()
        if got:
            return got
        waited = int(clock() - t0)
        if waited >= wait_s:
            raise InstallError(f"The watch did not show up. {hint}")
        if waited // 15 != shown:
            shown = waited // 15
            say(f"  Waiting for the watch... ({waited} s)")
        sleep(2)


def ask_plug(wait_s: int) -> None:
    say("Plug the watch into this computer with its USB cable now.")
    say(f"Waiting for the watch (up to {max(1, wait_s // 60)} minutes; after plugging in it can take a minute "
        f"or more before it is ready). {UNPLUG_HINT}")


# --- Windows: the Shell's view of the watch (no extra software) ---------------------------------

def ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


PS_FIND = r"""
$sh = New-Object -ComObject Shell.Application
function Child($f, $n) { foreach ($i in @($f.Items())) { if ($i.IsFolder -and $i.Name -ieq $n) { return $i.GetFolder } }; return $null }
function FindApps {
  foreach ($dev in @($sh.NameSpace(17).Items())) {
    if ($dev.IsFileSystem) { continue }
    $df = $null; try { $df = $dev.GetFolder } catch {}
    if ($df -eq $null) { continue }
    foreach ($st in @($df.Items())) {
      $sf = $null; try { $sf = $st.GetFolder } catch {}
      if ($sf -eq $null) { continue }
      $g = Child $sf 'GARMIN'; if ($g -eq $null) { continue }
      $a = Child $g 'Apps'; if ($a -ne $null) { return $a }
    }
  }
  return $null
}
# The Shell may hide the extension of a name: test the name with and without .prg.
function Is($n, $re) { return ($n -imatch $re) -or (($n + '.prg') -imatch $re) }
"""


def windows_probe_script() -> str:
    return PS_FIND + "if ((FindApps) -ne $null) { Write-Output 'FOUND'; exit 0 } else { exit 2 }\n"


def windows_script(src: str, size: int) -> str:
    """PowerShell, run once the watch is there: moves older copies out of Apps (into a backup folder:
    the Shell has no silent delete for a phone-like device), copies INSTAREM.PRG and waits until the
    copy is there. Lines starting with OK / ERR end it."""
    backup = os.path.join(tempfile.gettempdir(), "x5-remote-old-app")
    return PS_FIND + f"""
$ErrorActionPreference = 'Stop'
$src = {ps_quote(src)}; $size = {size}; $backup = {ps_quote(backup)}
$stale = {ps_quote('^' + STALE_RE + '$')}; $target = {ps_quote('^' + re.escape(TARGET) + '$')}
function Stale {{ @((FindApps).Items()) | Where-Object {{ Is $_.Name $stale }} }}
function Copies {{ @((FindApps).Items()) | Where-Object {{ Is $_.Name $target }} }}
function SizeOf($it) {{
  $s = $null; try {{ $s = $it.ExtendedProperty('System.Size') }} catch {{}}
  if ($s -eq $null) {{ try {{ $s = $it.Size }} catch {{}} }}
  return $s
}}
if ((FindApps) -eq $null) {{ Write-Output 'ERR: The watch is gone.'; exit 3 }}
$old = @(Stale)
if ($old.Count -gt 0) {{
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  $bf = $sh.NameSpace($backup)
  foreach ($o in $old) {{ Write-Output "STATUS: Moving the older copy $($o.Name) off the watch"; $bf.MoveHere($o, 4 + 16 + 1024) }}
  for ($i = 0; $i -lt 60 -and @(Stale).Count -gt 0; $i++) {{ Start-Sleep -Seconds 1 }}
  if (@(Stale).Count -gt 0) {{ Write-Output 'ERR: Could not remove the older copy from GARMIN\\Apps.'; exit 4 }}
}}
Write-Output 'STATUS: Copying the app to the watch...'
(FindApps).CopyHere($src, 4 + 16 + 1024)
$seen = $null
for ($i = 0; $i -lt 120; $i++) {{
  Start-Sleep -Seconds 1
  $c = @(Copies)
  if ($c.Count -gt 1) {{ Write-Output "ERR: $($c.Count) copies of the app on the watch."; exit 6 }}
  if ($c.Count -eq 1) {{
    $s = SizeOf $c[0]
    if ($s -ne $null -and [int64]$s -eq $size) {{ Write-Output "OK: $size bytes on the watch"; exit 0 }}
    if ($s -eq $null) {{
      if ($seen -eq $null) {{ $seen = $i }}
      if ($i - $seen -ge 10) {{ Write-Output 'OK: copied (size not reported by Windows)'; exit 0 }}
    }}
  }}
}}
Write-Output 'ERR: The copy did not complete.'; exit 5
"""


def run_ps(script: str, stream: bool = False) -> tuple[int, list]:
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc]
    if not stream:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout.splitlines()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines = []
    for line in p.stdout:
        line = line.strip()
        lines.append(line)
        if line.startswith(("STATUS: ", "OK: ", "ERR: ")):
            say("  " + line.split(": ", 1)[1])
    return p.wait(), lines


def copy_windows(prg: Path, wait_s: int) -> None:
    ask_plug(wait_s)
    wait_for(lambda: run_ps(windows_probe_script())[0] == 0, wait_s,
             f"Close Garmin Express if it is open. {UNPLUG_HINT}")
    say("  Watch found.")
    stage = Path(tempfile.mkdtemp(prefix="x5-remote-"))
    try:
        src = stage / TARGET                      # the Shell copies under the source file's name
        shutil.copyfile(prg, src)
        code, lines = run_ps(windows_script(str(src), src.stat().st_size), stream=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    if code != 0 or not any(x.startswith("OK: ") for x in lines):
        raise InstallError("Copying to the watch did not work. Close Garmin Express if it is open, "
                           "unplug and plug in the watch, and start again.")


# --- Linux: GVfs ----------------------------------------------------------------------------

def gio_roots(mount_list: str) -> list:
    """mtp:// roots from `gio mount -li` output (mounted or not yet)."""
    out = []
    for r in re.findall(r"(mtp://[^\s]+?/?)(?=\s|$)", mount_list):
        r = r if r.endswith("/") else r + "/"
        if r not in out:
            out.append(r)
    return out


def uri_child(uris: list, name: str) -> str | None:
    """From `gio list -u` URIs, the one whose last part is `name` (case-insensitive)."""
    for u in uris:
        if urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1]).upper() == name.upper():
            return u.rstrip("/") + "/"
    return None


def _gio(*args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["gio", *args], capture_output=True, text=True, timeout=timeout)


def _gio_uris(uri: str) -> list:
    r = _gio("list", "-u", uri)
    return [x.strip() for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []


def gio_apps() -> str | None:
    """URI of GARMIN/Apps on a GVfs MTP device, or None (no device, or no MTP backend)."""
    for root in gio_roots(_gio("mount", "-li").stdout):
        _gio("mount", root)                              # no-op when already mounted
        for storage in _gio_uris(root):                  # URIs: storage names are escaped
            garmin = uri_child(_gio_uris(storage), "GARMIN")
            apps = garmin and uri_child(_gio_uris(garmin), "Apps")
            if apps:
                return apps
    return None


def gio_has_mtp() -> bool:
    return bool(shutil.which("gio")) and bool(gio_roots(_gio("mount", "-li").stdout))


def copy_gio(apps: str, prg: Path) -> None:
    for u in _gio_uris(apps):
        name = urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1])
        if stale_names([name]):
            say(f"  Removing the older copy {name}")
            if _gio("remove", u).returncode != 0:
                raise InstallError(f"Could not remove the older copy {name} from the watch. Start again.")
    say("  Copying the app to the watch...")
    dest = apps + TARGET
    r = _gio("copy", str(prg), dest, timeout=300)
    if r.returncode != 0:
        raise InstallError("Copying to the watch did not work: " + (r.stderr.strip() or "gio copy failed"))
    sizes = []
    for u in _gio_uris(apps):
        if urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1]).upper() == TARGET:
            m = re.search(r"standard::size:\s*(\d+)", _gio("info", "-a", "standard::size", u).stdout)
            sizes.append(int(m.group(1)) if m else -1)
    check_copies(sizes, prg.stat().st_size)
    say(f"  {sizes[0]} bytes on the watch.")


# --- macOS and Linux: libmtp through ctypes -----------------------------------------------------

def libmtp_paths(platform: str) -> list:
    if platform == "darwin":
        return ["/opt/homebrew/lib/libmtp.dylib", "/opt/homebrew/lib/libmtp.9.dylib",
                "/usr/local/lib/libmtp.dylib", "/usr/local/lib/libmtp.9.dylib", "libmtp.dylib"]
    return ["libmtp.so.9", "libmtp.so"]


def load_libmtp(platform: str):
    import ctypes
    for p in libmtp_paths(platform):
        try:
            return ctypes.CDLL(p)
        except OSError:
            continue
    return None


def _mtp_types():
    import ctypes as C

    class DeviceEntry(C.Structure):
        _fields_ = [("vendor", C.c_char_p), ("vendor_id", C.c_uint16), ("product", C.c_char_p),
                    ("product_id", C.c_uint16), ("device_flags", C.c_uint32)]

    class RawDevice(C.Structure):
        _fields_ = [("device_entry", DeviceEntry), ("bus_location", C.c_uint32), ("devnum", C.c_uint8)]

    class Storage(C.Structure):
        pass
    Storage._fields_ = [("id", C.c_uint32), ("StorageType", C.c_uint16), ("FilesystemType", C.c_uint16),
                        ("AccessCapability", C.c_uint16), ("MaxCapacity", C.c_uint64),
                        ("FreeSpaceInBytes", C.c_uint64), ("FreeSpaceInObjects", C.c_uint64),
                        ("StorageDescription", C.c_char_p), ("VolumeIdentifier", C.c_char_p),
                        ("next", C.POINTER(Storage)), ("prev", C.POINTER(Storage))]

    class Device(C.Structure):   # only the leading fields that are read
        _fields_ = [("object_bitsize", C.c_uint8), ("params", C.c_void_p), ("usbinfo", C.c_void_p),
                    ("storage", C.POINTER(Storage))]

    class File(C.Structure):
        pass
    File._fields_ = [("item_id", C.c_uint32), ("parent_id", C.c_uint32), ("storage_id", C.c_uint32),
                     ("filename", C.c_char_p), ("filesize", C.c_uint64), ("modificationdate", C.c_long),
                     ("filetype", C.c_int), ("next", C.POINTER(File))]
    return C, RawDevice, Device, File


class Mtp:
    """The few libmtp calls the installer needs. Lists libmtp returns are freed after reading."""

    def __init__(self, lib):
        C, RawDevice, Device, File = _mtp_types()
        self.C, self.RawDevice, self.Device, self.File, self.lib = C, RawDevice, Device, File, lib
        lib.LIBMTP_Detect_Raw_Devices.argtypes = [C.POINTER(C.POINTER(RawDevice)), C.POINTER(C.c_int)]
        lib.LIBMTP_Open_Raw_Device_Uncached.argtypes = [C.POINTER(RawDevice)]
        lib.LIBMTP_Open_Raw_Device_Uncached.restype = C.POINTER(Device)
        lib.LIBMTP_Get_Storage.argtypes = [C.POINTER(Device), C.c_int]
        lib.LIBMTP_Get_Files_And_Folders.argtypes = [C.POINTER(Device), C.c_uint32, C.c_uint32]
        lib.LIBMTP_Get_Files_And_Folders.restype = C.POINTER(File)
        lib.LIBMTP_destroy_file_t.argtypes = [C.POINTER(File)]
        lib.LIBMTP_Delete_Object.argtypes = [C.POINTER(Device), C.c_uint32]
        lib.LIBMTP_Send_File_From_File.argtypes = [C.POINTER(Device), C.c_char_p, C.POINTER(File), C.c_void_p, C.c_void_p]
        lib.LIBMTP_Release_Device.argtypes = [C.POINTER(Device)]
        lib.LIBMTP_FreeMemory.argtypes = [C.c_void_p]
        lib.LIBMTP_Init()
        self.open_fails = 0

    def open_watch(self):
        """The watch's device handle, or None while it is not there. Raises InstallError when the
        watch is on USB but cannot be opened several times in a row (another program has it)."""
        C, lib = self.C, self.lib
        raw = C.POINTER(self.RawDevice)()
        n = C.c_int(0)
        if lib.LIBMTP_Detect_Raw_Devices(C.byref(raw), C.byref(n)) != 0:
            return None
        try:
            for i in range(n.value):
                if raw[i].device_entry.vendor_id == GARMIN_VID:
                    dev = lib.LIBMTP_Open_Raw_Device_Uncached(C.byref(raw[i]))
                    if dev:
                        self.open_fails = 0
                        return dev
                    self.open_fails += 1
                    if self.open_fails >= OPEN_FAILS:
                        raise InstallError(BUSY_MSG)
        finally:
            lib.LIBMTP_FreeMemory(raw)
        return None

    def entries(self, dev, sid, parent) -> list:
        """(id, parent, name, is_folder, size) of a folder's children."""
        out = []
        # Read the whole list before freeing anything: a ctypes pointer field read from a struct
        # still points into that struct's memory, so freeing an item first loses the rest of the list.
        items = []
        f = self.lib.LIBMTP_Get_Files_And_Folders(dev, sid, parent)
        while f:
            e = f.contents
            out.append((e.item_id, e.parent_id, (e.filename or b"").decode("utf-8", "replace"),
                        e.filetype == 0, e.filesize))
            items.append(f)
            f = e.next
        for f in items:
            self.lib.LIBMTP_destroy_file_t(f)
        return out


def copy_libmtp(prg: Path, mtp: Mtp, dev) -> None:
    lib, C = mtp.lib, mtp.C
    try:
        lib.LIBMTP_Get_Storage(dev, 0)
        st = dev.contents.storage
        apps = sid = None
        while st and apps is None:
            sid = st.contents.id
            root = mtp.entries(dev, sid, ROOT)
            garmin = [e for e in root if e[3] and e[2].upper() == "GARMIN"]
            found = root + (mtp.entries(dev, sid, garmin[0][0]) if garmin else [])
            apps = find_apps([e[:4] for e in found])
            st = st.contents.next
        if apps is None:
            raise InstallError("The watch has no GARMIN/Apps folder.")
        for e in mtp.entries(dev, sid, apps):
            if not e[3] and stale_names([e[2]]):
                say(f"  Removing the older copy {e[2]}")
                if lib.LIBMTP_Delete_Object(dev, e[0]) != 0:
                    raise InstallError(f"Could not remove the older copy {e[2]} from the watch, so the new one "
                                       "was not copied. Unplug and plug in the watch, and start again.")
        say("  Copying the app to the watch...")
        size = prg.stat().st_size
        f = mtp.File(item_id=0, parent_id=apps, storage_id=sid, filename=TARGET.encode(), filesize=size,
                     modificationdate=0, filetype=44)   # 44 = LIBMTP_FILETYPE_UNKNOWN
        if lib.LIBMTP_Send_File_From_File(dev, str(prg).encode(), C.byref(f), None, None) != 0:
            raise InstallError("Copying to the watch did not work. Unplug and plug in the watch, and start again.")
        check_copies([e[4] for e in mtp.entries(dev, sid, apps) if not e[3] and e[2].upper() == TARGET], size)
        say(f"  {size} bytes on the watch.")
    finally:
        lib.LIBMTP_Release_Device(dev)


def garmin_express_running(run=subprocess.run) -> bool:
    """The Garmin Express app itself (its always-on helper "Garmin Express Service" does not count)."""
    if sys.platform != "darwin":
        return False
    return run(["pgrep", "-x", "Garmin Express"], capture_output=True).returncode == 0


def ensure_libmtp_mac():
    lib = load_libmtp("darwin")
    if lib:
        return lib
    say("Copying to the watch on a Mac needs the free libmtp library, which is not installed.")
    brew = shutil.which("brew") or next((b for b in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew")
                                         if os.path.exists(b)), None)
    if not brew:
        raise InstallError("Install Homebrew from https://brew.sh, then start this installer again "
                           "(it then offers to install libmtp).\nOr copy the .prg to GARMIN/Apps by hand "
                           "with an MTP app such as OpenMTP (see the README).")
    if input("Install libmtp with Homebrew now? [y/N] ").strip().lower() not in ("y", "yes"):
        raise InstallError("Not installed. Run `brew install libmtp` and start this installer again.")
    if subprocess.run([brew, "install", "libmtp"]).returncode != 0:
        raise InstallError("Homebrew could not install libmtp (see the messages above).")
    lib = load_libmtp("darwin")
    if not lib:
        raise InstallError("libmtp is installed but could not be loaded. Start this installer again.")
    return lib


def linux_install_hint() -> str:
    if shutil.which("apt"):
        return "sudo apt install gvfs-backends libmtp9"
    if shutil.which("dnf"):
        return "sudo dnf install gvfs-mtp libmtp"
    if shutil.which("pacman"):
        return "sudo pacman -S gvfs-mtp libmtp"
    return "install gvfs-mtp (GVfs MTP support) or libmtp with your package manager"


def linux_probe(mtp: Mtp | None, use_gio: bool):
    """One look for the watch on Linux: ("gio", apps URI) or ("libmtp", device) or None. GVfs is
    asked first; while it shows the watch, libmtp could not open it anyway."""
    def probe():
        if use_gio and gio_has_mtp():
            apps = gio_apps()
            return ("gio", apps) if apps else None
        if mtp:
            dev = mtp.open_watch()
            return ("libmtp", dev) if dev else None
        return None
    return probe


def copy_to_watch(prg: Path, wait_s: int) -> None:
    methods = methods_for(sys.platform)
    if methods == ["windows"]:
        return copy_windows(prg, wait_s)
    if sys.platform == "darwin":
        if garmin_express_running():
            input("Garmin Express is running and may hold the watch. Quit it (menu bar icon > Quit), "
                  "then press Enter. ")
        mtp = Mtp(ensure_libmtp_mac())
        ask_plug(wait_s)
        dev = wait_for(mtp.open_watch, wait_s, f"Close Garmin Express if it is open. {UNPLUG_HINT}")
        say("  Watch found.")
        return copy_libmtp(prg, mtp, dev)
    lib = load_libmtp(sys.platform) if "libmtp" in methods else None
    use_gio = "gio" in methods and bool(shutil.which("gio"))
    if not lib and not use_gio:
        raise InstallError("Copying to the watch needs MTP support. Install it with:\n  "
                           + linux_install_hint() + "\nthen start this installer again.")
    ask_plug(wait_s)
    hint = f"{UNPLUG_HINT}\nIf it still does not show up, MTP support may be missing: {linux_install_hint()}"
    mtp = Mtp(lib) if lib else None
    how, where = wait_for(linux_probe(mtp, use_gio), wait_s, hint)
    say("  Watch found.")
    if how == "gio":
        return copy_gio(where, prg)
    return copy_libmtp(prg, mtp, where)


def main(argv: list) -> int:
    say("Insta360 X5 Remote - installer for the Garmin Descent Mk3i 51 mm")
    say()
    args = list(argv)

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            return args[i + 1] if i + 1 < len(args) else ""
        return default

    tmp = Path(tempfile.mkdtemp(prefix="x5-remote-dl-"))
    try:
        wait_s = parse_wait(opt("--wait", "300"))
        given = opt("--prg")
        prg = Path(given) if given else local_prg(Path(__file__).resolve().parent)
        if prg:
            if not prg.is_file():
                raise InstallError(f"{prg} does not exist.")
            check_local(prg)
        else:
            prg = download_latest(tmp)
        if "--check" in args:
            say("Checked; not copying (--check).")
            return 0
        say()
        copy_to_watch(prg, wait_s)
        say()
        say("Done. Unplug the watch; the app appears in the widget loop (scroll up or down from the watch face).")
        return 0
    except InstallError as e:
        say()
        say(str(e))
        return 1
    except KeyboardInterrupt:
        say()
        say("Stopped.")
        return 1
    except (OSError, subprocess.SubprocessError) as e:
        say()
        say(f"Something went wrong ({e.__class__.__name__}: {e}). Unplug and plug in the watch, and start again.")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
