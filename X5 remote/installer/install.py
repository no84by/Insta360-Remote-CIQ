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
import urllib.request
from pathlib import Path

REPO = "no84by/Insta360-Remote-CIQ"
TAG_PREFIX = "x5-remote-v"
DEVICE = "descentmk351mm"
TARGET = "INSTAREM.PRG"          # file name on the watch
GARMIN_VID = 0x091E
ROOT = 0xFFFFFFFF                # libmtp: parent id of the storage root
UNPLUG_HINT = "If nothing happens, unplug the watch and plug it in again."


class InstallError(Exception):
    """A problem the user can act on; the message says what to do."""


def say(msg: str = "") -> None:
    print(msg, flush=True)


# --- release selection and verification -------------------------------------------------------

def version_key(tag: str) -> tuple:
    """x5-remote-v1.1.4 -> (1, 1, 4); anything else sorts first."""
    m = re.fullmatch(re.escape(TAG_PREFIX) + r"(\d+(?:\.\d+)*)", tag or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


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
        prg = next((a for a in assets if a.get("name", "").endswith(f"-{DEVICE}.prg")), None)
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
    got = hashlib.sha256(data).hexdigest()
    if got != want:
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
        releases = json.loads(_fetch(f"https://api.github.com/repos/{REPO}/releases?per_page=50"))
    except Exception as e:
        raise InstallError(f"Could not reach GitHub ({e.__class__.__name__}). Check the internet connection, "
                           "or put the .prg file from the release next to this installer and start again.")
    pick = pick_release(releases)
    if not pick:
        raise InstallError("No X5 Remote release with a file for the Descent Mk3i 51 mm was found.")
    tag, prg, sums = pick
    say(f"Downloading {prg['name']} ({tag})...")
    data = _fetch(prg["browser_download_url"], timeout=60)
    verify(data, prg["name"], parse_sums(_fetch(sums["browser_download_url"]).decode("utf-8", "replace")))
    say("Download checked (SHA-256 matches the release).")
    out = dest / prg["name"]
    out.write_bytes(data)
    return out


def local_prg(here: Path) -> Path | None:
    """A .prg for the watch next to the installer (offline use); the newest name wins."""
    found = sorted(here.glob(f"*{DEVICE}*.prg")) or sorted(here.glob("*.prg"))
    return found[-1] if found else None


def check_local(prg: Path) -> None:
    """Verify a local .prg against a SHA256SUMS next to it, when there is one."""
    sums_file = prg.parent / "SHA256SUMS"
    if not sums_file.exists():
        say(f"Using {prg.name} (no SHA256SUMS next to it, so it is not checked).")
        return
    verify(prg.read_bytes(), prg.name, parse_sums(sums_file.read_text("utf-8", "replace")))
    say(f"Using {prg.name} (SHA-256 matches SHA256SUMS).")


# --- the watch's folders -----------------------------------------------------------------------

def find_apps(entries: list) -> int | None:
    """Id of GARMIN/Apps from (id, parent_id, name, is_folder) entries; root entries have parent ROOT."""
    garmin = [e[0] for e in entries if e[3] and e[1] in (ROOT, 0) and e[2].upper() == "GARMIN"]
    for e in entries:
        if e[3] and e[1] in garmin and e[2].upper() == "APPS":
            return e[0]
    return None


def stale_names(names: list) -> list:
    """Files in Apps to remove before copying: an older INSTAREM.PRG, and copies installed by hand
    under the release file name (two copies of one app confuse the watch)."""
    return [n for n in names if n.upper() == TARGET or re.fullmatch(r"insta360-x5-remote.*\.prg", n, re.I)]


def methods_for(platform: str) -> list:
    """Copy methods to try, in order, for sys.platform."""
    if platform.startswith("win"):
        return ["windows"]
    if platform == "darwin":
        return ["libmtp"]
    return ["gio", "libmtp"]


# --- Windows: the Shell's view of the watch (no extra software) ---------------------------------

def ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def windows_script(src: str, size: int, wait_s: int) -> str:
    """PowerShell that waits for the watch, moves older copies out of Apps (into a backup folder:
    the Shell has no silent delete for a phone-like device), copies INSTAREM.PRG and waits until
    the copy has the right size. Lines starting with OK / ERR end it."""
    backup = os.path.join(tempfile.gettempdir(), "x5-remote-old-app")
    return f"""
$ErrorActionPreference = 'Stop'
$src = {ps_quote(src)}; $name = {ps_quote(TARGET)}; $size = {size}; $wait = {wait_s}
$backup = {ps_quote(backup)}
$sh = New-Object -ComObject Shell.Application
function Child($f, $n) {{ foreach ($i in @($f.Items())) {{ if ($i.IsFolder -and $i.Name -ieq $n) {{ return $i.GetFolder }} }}; return $null }}
function FindApps {{
  foreach ($dev in @($sh.NameSpace(17).Items())) {{
    if ($dev.IsFileSystem) {{ continue }}
    $df = $null; try {{ $df = $dev.GetFolder }} catch {{}}
    if ($df -eq $null) {{ continue }}
    foreach ($st in @($df.Items())) {{
      $sf = $null; try {{ $sf = $st.GetFolder }} catch {{}}
      if ($sf -eq $null) {{ continue }}
      $g = Child $sf 'GARMIN'; if ($g -eq $null) {{ continue }}
      $a = Child $g 'Apps'; if ($a -ne $null) {{ return $a }}
    }}
  }}
  return $null
}}
function Stale($a) {{ @($a.Items()) | Where-Object {{ $_.Name -ieq $name -or $_.Name -ieq 'INSTAREM' -or $_.Name -like 'insta360-x5-remote*' }} }}
$t0 = Get-Date; $apps = $null; $last = -1
while ($apps -eq $null) {{
  $apps = FindApps
  if ($apps -ne $null) {{ break }}
  $s = [int]((Get-Date) - $t0).TotalSeconds
  if ($s -ge $wait) {{ Write-Output 'ERR: The watch did not show up.'; exit 3 }}
  if ([int]($s / 15) -ne $last) {{ $last = [int]($s / 15); Write-Output "STATUS: Waiting for the watch... ($s s)" }}
  Start-Sleep -Seconds 2
}}
Write-Output 'STATUS: Watch found.'
$old = @(Stale $apps)
if ($old.Count -gt 0) {{
  New-Item -ItemType Directory -Force -Path $backup | Out-Null
  $bf = $sh.NameSpace($backup)
  foreach ($o in $old) {{ Write-Output "STATUS: Moving the older copy $($o.Name) off the watch"; $bf.MoveHere($o, 4 + 16 + 1024) }}
  for ($i = 0; $i -lt 60 -and @(Stale (FindApps)).Count -gt 0; $i++) {{ Start-Sleep -Seconds 1 }}
  if (@(Stale (FindApps)).Count -gt 0) {{ Write-Output 'ERR: Could not remove the older copy from GARMIN\\Apps.'; exit 4 }}
}}
Write-Output 'STATUS: Copying the app to the watch...'
$apps.CopyHere($src, 4 + 16 + 1024)
for ($i = 0; $i -lt 120; $i++) {{
  Start-Sleep -Seconds 1
  $it = $null; try {{ $it = (FindApps).ParseName($name) }} catch {{}}
  if ($it -ne $null -and [int64]$it.ExtendedProperty('System.Size') -eq $size) {{ Write-Output "OK: $size bytes on the watch"; exit 0 }}
}}
Write-Output 'ERR: The copy did not complete.'; exit 5
"""


def copy_windows(prg: Path, wait_s: int) -> None:
    stage = Path(tempfile.mkdtemp(prefix="x5-remote-"))
    src = stage / TARGET                      # the Shell copies under the source file's name
    shutil.copyfile(prg, src)
    script = windows_script(str(src), src.stat().st_size, wait_s)
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    say("Plug the watch into this computer with its USB cable now.")
    say(f"Waiting for the watch (up to {wait_s // 60} minutes; this can take a while). {UNPLUG_HINT}")
    p = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-EncodedCommand", enc], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = None
    for line in p.stdout:
        line = line.strip()
        if line.startswith(("STATUS: ", "OK: ", "ERR: ")):
            say("  " + line.split(": ", 1)[1])
            if not line.startswith("STATUS"):
                result = line
    p.wait()
    shutil.rmtree(stage, ignore_errors=True)
    if p.returncode != 0 or not (result or "").startswith("OK"):
        raise InstallError("Copying to the watch did not work. Close Garmin Express if it is open, "
                           "unplug and plug in the watch, and start again.")


# --- Linux: GVfs ----------------------------------------------------------------------------

def gio_roots(mount_list: str) -> list:
    """mtp:// roots from `gio mount -li` output (mounted or not yet)."""
    roots = re.findall(r"(mtp://[^\s]+?/?)(?=\s|$)", mount_list)
    out = []
    for r in roots:
        r = r if r.endswith("/") else r + "/"
        if r not in out:
            out.append(r)
    return out


def _gio(*args, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["gio", *args], capture_output=True, text=True, timeout=timeout)


def copy_gio(prg: Path, wait_s: int) -> None:
    say("Plug the watch into this computer with its USB cable now.")
    say(f"Waiting for the watch (up to {wait_s // 60} minutes). {UNPLUG_HINT}")
    t0 = time.time()
    apps = None
    while apps is None:
        for root in gio_roots(_gio("mount", "-li").stdout):
            _gio("mount", root)                              # no-op when already mounted
            for storage in _gio("list", root).stdout.split("\n"):
                if not storage.strip():
                    continue
                garmin = f"{root}{storage.strip()}/GARMIN/"
                listing = _gio("list", garmin)
                if listing.returncode != 0:
                    continue
                for d in listing.stdout.split("\n"):
                    if d.strip().upper() == "APPS":
                        apps = f"{garmin}{d.strip()}/"
        if apps:
            break
        waited = int(time.time() - t0)
        if waited >= wait_s:
            raise InstallError(f"The watch did not show up. {UNPLUG_HINT}")
        if waited % 15 < 2:
            say(f"  Waiting for the watch... ({waited} s)")
        time.sleep(2)
    say("  Watch found.")
    for n in stale_names([x.strip() for x in _gio("list", apps).stdout.split("\n") if x.strip()]):
        say(f"  Removing the older copy {n}")
        _gio("remove", apps + n)
    say("  Copying the app to the watch...")
    r = _gio("copy", str(prg), apps + TARGET, timeout=300)
    size = _gio("info", "-a", "standard::size", apps + TARGET).stdout
    m = re.search(r"standard::size:\s*(\d+)", size)
    if r.returncode != 0 or not m or int(m.group(1)) != prg.stat().st_size:
        raise InstallError("Copying to the watch did not work: " + (r.stderr.strip() or "size check failed"))
    say(f"  {m.group(1)} bytes on the watch.")


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


def copy_libmtp(prg: Path, wait_s: int, lib) -> None:
    C, RawDevice, Device, File = _mtp_types()
    lib.LIBMTP_Detect_Raw_Devices.argtypes = [C.POINTER(C.POINTER(RawDevice)), C.POINTER(C.c_int)]
    lib.LIBMTP_Open_Raw_Device_Uncached.argtypes = [C.POINTER(RawDevice)]
    lib.LIBMTP_Open_Raw_Device_Uncached.restype = C.POINTER(Device)
    lib.LIBMTP_Get_Storage.argtypes = [C.POINTER(Device), C.c_int]
    lib.LIBMTP_Get_Files_And_Folders.argtypes = [C.POINTER(Device), C.c_uint32, C.c_uint32]
    lib.LIBMTP_Get_Files_And_Folders.restype = C.POINTER(File)
    lib.LIBMTP_Delete_Object.argtypes = [C.POINTER(Device), C.c_uint32]
    lib.LIBMTP_Send_File_From_File.argtypes = [C.POINTER(Device), C.c_char_p, C.POINTER(File), C.c_void_p, C.c_void_p]
    lib.LIBMTP_Release_Device.argtypes = [C.POINTER(Device)]
    lib.LIBMTP_Init()

    say("Plug the watch into this computer with its USB cable now.")
    say(f"Waiting for the watch (up to {wait_s // 60} minutes; after plugging in it can take a minute "
        f"or more before it is ready). {UNPLUG_HINT}")
    t0 = time.time()
    dev = None
    while not dev:
        raw = C.POINTER(RawDevice)()
        n = C.c_int(0)
        if lib.LIBMTP_Detect_Raw_Devices(C.byref(raw), C.byref(n)) == 0:
            for i in range(n.value):
                if raw[i].device_entry.vendor_id == GARMIN_VID:
                    dev = lib.LIBMTP_Open_Raw_Device_Uncached(C.byref(raw[i]))
                    break
        if dev:
            break
        waited = int(time.time() - t0)
        if waited >= wait_s:
            raise InstallError(f"The watch did not show up. Close Garmin Express if it is open. {UNPLUG_HINT}")
        if waited % 15 < 2:
            say(f"  Waiting for the watch... ({waited} s)")
        time.sleep(2)
    say("  Watch found.")

    def entries(sid, parent):
        out = []
        f = lib.LIBMTP_Get_Files_And_Folders(dev, sid, parent)
        while f:
            e = f.contents
            out.append((e.item_id, e.parent_id, (e.filename or b"").decode("utf-8", "replace"),
                        e.filetype == 0, e.filesize))
            f = e.next
        return out

    try:
        lib.LIBMTP_Get_Storage(dev, 0)
        st = dev.contents.storage
        apps = sid = None
        while st and apps is None:
            sid = st.contents.id
            root = entries(sid, ROOT)
            garmin = [e for e in root if e[3] and e[2].upper() == "GARMIN"]
            found = root + (entries(sid, garmin[0][0]) if garmin else [])
            apps = find_apps([e[:4] for e in found])
            st = st.contents.next
        if apps is None:
            raise InstallError("The watch has no GARMIN/Apps folder.")
        for e in entries(sid, apps):
            if not e[3] and e[2] in stale_names([e[2]]):
                say(f"  Removing the older copy {e[2]}")
                lib.LIBMTP_Delete_Object(dev, e[0])
        say("  Copying the app to the watch...")
        size = prg.stat().st_size
        f = File(item_id=0, parent_id=apps, storage_id=sid, filename=TARGET.encode(), filesize=size,
                 modificationdate=0, filetype=44)   # 44 = LIBMTP_FILETYPE_UNKNOWN
        if lib.LIBMTP_Send_File_From_File(dev, str(prg).encode(), C.byref(f), None, None) != 0:
            raise InstallError("Copying to the watch did not work. Unplug and plug in the watch, and start again.")
        got = [e for e in entries(sid, apps) if e[2].upper() == TARGET]
        if not got or got[0][4] != size:
            raise InstallError("The copy on the watch does not have the right size. Start again.")
        say(f"  {size} bytes on the watch.")
    finally:
        lib.LIBMTP_Release_Device(dev)


def garmin_express_running() -> bool:
    if sys.platform != "darwin":
        return False
    return subprocess.run(["pgrep", "-f", "Garmin Express"], capture_output=True).returncode == 0


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


def copy_to_watch(prg: Path, wait_s: int) -> None:
    for method in methods_for(sys.platform):
        if method == "windows":
            return copy_windows(prg, wait_s)
        if method == "gio" and shutil.which("gio") and _gio("mount", "-l").returncode == 0:
            return copy_gio(prg, wait_s)
        if method == "libmtp":
            if sys.platform == "darwin":
                while garmin_express_running():
                    input("Garmin Express is running and would hold the watch. Quit it "
                          "(menu bar icon > Quit), then press Enter. ")
                return copy_libmtp(prg, wait_s, ensure_libmtp_mac())
            lib = load_libmtp(sys.platform)
            if lib:
                return copy_libmtp(prg, wait_s, lib)
    raise InstallError("Copying to the watch needs MTP support. Install it with:\n  "
                       + linux_install_hint() + "\nthen start this installer again.")


def main(argv: list) -> int:
    say("Insta360 X5 Remote - installer for the Garmin Descent Mk3i 51 mm")
    say()
    args = list(argv)
    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            return args[i + 1] if i + 1 < len(args) else default
        return default
    wait_s = int(opt("--wait", "300"))
    here = Path(__file__).resolve().parent
    tmp = Path(tempfile.mkdtemp(prefix="x5-remote-dl-"))
    try:
        given = opt("--prg")
        prg = Path(given) if given else local_prg(here)
        if prg:
            if not prg.exists():
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
