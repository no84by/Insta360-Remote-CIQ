# Insta360 X5 Remote for Garmin watches

A Connect IQ widget that remote-controls the **Insta360 X5** from a **Garmin Descent Mk3i 51 mm**:
start and stop recordings, take photos, switch modes and change shooting settings from the wrist.

**[Download the latest release](https://github.com/no84by/Insta360-Remote-CIQ/releases/tag/x5-remote-v1.1.4)**
· [Full documentation](X5%20remote/README.md) · [X5 Bluetooth protocol notes](X5%20remote/docs/x5-protocol.md)

<img src="X5%20remote/docs/screenshots/overview.png" width="820" alt="Overview: Video, Photo Burst, Photo Interval, Timelapse, Settings page, recording, searching, camera not found">

## Why this fork

The official Insta360 Connect IQ app crashes at "Searching for device" on a Descent Mk3i with an X5,
and the original community widget in this repository predates the X5's newer protocol. This fork adds
an X5 widget, built on the original widget's Bluetooth code, tested on the real watch and camera.

It is not in the Connect IQ store: you install it yourself with the installer below. No Garmin account
is needed.

## Install

1. Download `x5-remote-installer.zip` from the [latest release](https://github.com/no84by/Insta360-Remote-CIQ/releases/tag/x5-remote-v1.1.4) and unzip it.
2. Double-click the file for your computer: `Install on Windows.bat`, `Install on Mac.command` or
   `Install on Linux.sh`. (Windows or macOS may warn about an unsigned file: `READ ME FIRST.txt` says
   how to allow it.)
3. When asked, plug the watch in with its USB cable and wait. It can take a minute or more before the
   watch is ready; if nothing happens, unplug it and plug it in again.
4. When the window says "Done", unplug the watch. The widget is in the widget loop: scroll up or down
   from the watch face.

The installer downloads the newest release, checks it against the release's `SHA256SUMS` and copies it
to `GARMIN/Apps`, replacing an older copy. To install by hand instead, copy the `.prg` from the release
into `GARMIN/Apps` over USB ([details](X5%20remote/README.md)).

Tested on a Descent Mk3i 51 mm with macOS, Windows 11 and Linux (libmtp); the Linux desktop (GVfs)
path is untested on hardware. On other Garmin watches it installs, but it is untested there and used at
your own risk.

**Before the first use:** close the Insta360 phone app (the X5 accepts one Bluetooth client at a time),
wake the camera, open the widget, and tap **Allow** on the camera's screen when it asks.

## What it does

- **All 13 X5 modes**, switched from the watch, and the watch follows mode changes made on the camera.
- **Capture:** video, PureVideo, photo, burst, interval, starlapse, timelapse. Recordings started or
  stopped on the camera are followed live, with an exact timer.
- **Per-mode settings** from the watch: resolution / frame rate, EV, lens (360° / front), self-timer,
  photo size, interval, burst, timelapse speed, loop length, starlapse duration.
- **Settings page** (last mode dot): camera sound on / off, power off the camera, exit.
- **Status:** charging / on battery, low battery, SD card state (no card / full / error).
- **Robust link:** reconnects after the camera's standby or a dropped link, recovers a stuck Bluetooth
  write queue, and keeps the recording timer across reconnects.

## How to use it

The screen has two columns: the mode icon on the left; on the right the mode name (the **title**) and
the settings of that mode (**rows**). One entry is **focused** at a time (amber pill).

| Button | Ready | Recording |
|---|---|---|
| START | Shoot: start video, take the photo, start interval / burst / timelapse | Stop |
| UP / DOWN | Change the focused entry: title = previous / next mode, row = previous / next value | Highlight / *Track That* |
| BACK | Move the focus: title → row 1 → row 2 → … → title | — |
| Hold UP | Mode list, **Exit app** | — |

| Touch | Does |
|---|---|
| Tap the title or a row | Focus it |
| Swipe up / down | Same as UP / DOWN on the focused entry (ignored while recording) |
| Tap anywhere else | Same as START |

Changes are sent to the camera about 0.8 s after the last press, so you can scroll quickly. A second
START press while the camera is still confirming a start or stop is ignored. Taps right after a button
press are ignored, so a palm on the screen does not start a recording.

## Limits (Connect IQ, not the camera)

Connect IQ delivers at most 20 bytes per Bluetooth notification, and the X5 never continues a cut
reply. So the watch cannot read:

- the battery **percentage** or free card **space** (it shows charging / battery and the card state);
- the current value of a setting changed on the camera's own screen (that row shows `–` until you set
  it from the watch);
- the elapsed time of a recording that was already running before the watch connected (it shows
  **REC** and "joined" instead of a timer).

Also: the watch cannot power the camera **on** (Connect IQ apps cannot send the wake advertisement);
power off works.

Details: [X5 protocol notes](X5%20remote/docs/x5-protocol.md) and
[how the app uses them](X5%20remote/docs/watch-app.md).

## Credits and license

Built on [ArsFabula's Insta360 Remote](https://github.com/arsfabula/Insta360-Remote-CIQ) (Bluetooth
code and the original widget for older Insta360 cameras). Mozilla Public License 2.0, the license of
the original project; provided "as is", without warranty.

## The original project (older cameras)

The rest of this repository is the original widget and data field for the Insta360 One R / RS / X /
X2 / X3 and related cameras: `BLE Barrel/`, `OneR Remote/` and `OneR remote DF/`. It is available in the
Connect IQ store as [Insta360 Remote](https://apps.garmin.com/apps/bb53f4bb-6c8c-4369-bca9-84cc09b25526);
see the [original repository](https://github.com/arsfabula/Insta360-Remote-CIQ) for its documentation.
