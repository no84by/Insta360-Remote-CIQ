# Watch app: how it uses the protocol, and how to extend it

Connect IQ watch app for the Garmin Descent Mk3i 51 mm (other round Connect IQ ≥ 3.1 devices should
work). It is a fork of ArsFabula's Insta360 Remote (MPL-2.0) with a new UI and X5 support.

## What it does

| Feature | Protocol ([`x5-protocol.md`](x5-protocol.md)) | Code |
|---|---|---|
| Connect, notifications, sync, keep-alive | §2.1 | `BLEBarrel.mc` `enableNotifications`, `onDescriptorWrite`, `keepAlive` |
| One write at a time, chunks never interleaved | §2.4 | `BLEBarrel.mc` `pump`, `onCharacteristicWrite` |
| Write recovery: a lost write callback is resumed after two keep-alive ticks; refused writes on four keep-alive ticks in a row with none accepted (6–8 s) drop the link and reconnect through the disconnect path (a wedged link sends no disconnect event); above 16 queued chunks GPS telemetry and keep-alives are dropped (whole frames), commands never | §2.4 | `BLEBarrel.mc` `pump`, `linkLost`, `queueFrame`, `trimQueue` |
| Model: from the advertised name of the camera being connected. Names of the older cameras the upstream app supports (ONE, X3, X4, GO, Ace) get the legacy protocol; any other name gets the X5 protocol, since the X5 sends no notification before its session start (§2.2) and no identity reply fits in 20 bytes | §2.2, §10 | `BLEBarrel.isX5`, `LEGACY_MODELS`, `adoptName` |
| Mode list and switching | §3.1 | `RemoteDelegate.mc` `modeListX5`, `sendCurrentMode`; `BLEBarrel.setSubModeX5` |
| Follow mode changes made on the camera | §3.2 `0x2053` | `BLEBarrel.onFrameX5` |
| Sync on connect: adopt a running capture, otherwise push the watch's mode. The timer of an adopted capture shows a leading `+` (`+00:12`): it counts from when the watch joined (a reconnect during a recording the watch already showed keeps its timer), because the camera's elapsed time cannot be read on a watch (below) | §4.1 | `BLEBarrel.queryCaptureX5`, `syncOnConnect`, `recAdopted`, `timerText` |
| Video, photo, burst, interval, starlapse | §4 | `RemoteDelegate.onSelect`; `BLEBarrel.shutterX5`, `lapseX5` |
| Every action waits for the camera (state poll every 2 s, 60 s safety net) | §4.1 | `RemoteView.onTick` |
| Charging / on-battery, low-battery alarm, SD card state (no card / full / error) on the top arcs, with toasts. No battery level or card space on the X5 (see below) | §6 `GET_STORAGE`, §8 `0x2003` `0x2004` `0x2006` | `BLEBarrel.onFrameX5`, `queryStorageX5`; `RemoteView.drawWidgets` |
| Identify as a Garmin watch; "Allow on camera" / "Camera allowed" toasts | §2.2 | `BLEBarrel.checkAuthX5` |
| Settings page (last entry of the mode list, gear icon): SOUND, Power off camera, Exit app. BACK moves the focus, START (or a second tap on the focused row) runs Power off / Exit | — | `Settings.rows("set")`, `RemoteDelegate.onSelect` |
| SOUND On / Off = camera mute | §6 `MUTE` (14) | `Settings.frames` `:mute` |
| Power off camera, after a No / Yes menu with *No* focused (not `Ui.Confirmation`: on the Mk3i it shows Cancel / Confirm without a visible focus, and a second START press confirms). Power-on is not possible from the watch: it needs the wake beacon (§6), and Connect IQ apps cannot advertise. `tools/wake.swift` sends it from a Mac | §6 `SET_SHUTDOWN` (219) | `confirmPowerOff`, `PowerOffDelegate`; `BLEBarrel.shutdownX5` |
| Per-mode settings: resolution / frame rate, EV (stops at ±4.0), lens, self-timer, photo size, interval, burst, loop length, TimeShift speed, Starlapse duration | §3.3, §5, §5.1 | `Settings.rows`, `Settings.frames`; `RemoteDelegate.stepFocused` |
| Settings changed on the camera: the `0x2065` push names the option but is cut before the value, so every row carrying that option goes back to `–` until it is set from the watch. Pushes within 3 s of the watch's own write or mode change are its echoes and skipped; a cut push within 1.5 s of a `0x2053` (either order) belongs to that mode change and is skipped too | §5 | `BLEBarrel.onSettingPushX5`, `Settings.cameraChanged` |
| Highlight / *Track That* while recording (UP / DOWN) | §4 `0x3C` | `RemoteDelegate.onPreviousPage`, `onNextPage` |
| Touch: tap a row = focus it, tap elsewhere = START | — | `RemoteDelegate.onSelect`, `onTap`, `focusRowAt` |
| GPS overlay (hold-UP menu): older cameras only; hidden and GPS off with an X5 | — | `RemoteDelegate.onMenu`, `Main.gpsSync`, `photoWithGps` |
| Exit: Settings → Exit app, hold UP → Exit app, or BACK in a mode without settings. Long-press BACK belongs to the OS | — | `RemoteDelegate.onSelect`, `onMenu`, `onBack` |

Connect IQ quirks the app works around:

* **20-byte notifications:** parse each notification as one possibly truncated frame
  (`reassembleX5`, lenient `pbFields`).
* **`onStart` also runs for the glance:** start BLE only from `getInitialView`, otherwise the glance
  steals the BLE delegate.
* **A missing GATT service right after connecting is normal:** never unpair or rescan on it
  (the original code did, which left the camera needing a power cycle).
* **A tap arrives as `onSelect` first:** `BehaviorDelegate` maps a screen tap to the SELECT
  behaviour and calls `onTap` only when `onSelect` returns false. A START press reaches
  `onKeyPressed(KEY_ENTER)` before `onSelect`, a tap does not, so `onSelect` without that key
  declines and `onTap` focuses the tapped row (a 150 ms fallback runs START if no `onTap` follows).
* **The native toast (`WatchUi.showToast`) swallows the next button press** (it only dismisses
  itself). The app draws its own toast instead (`RemoteView.drawToast`), which takes no input.

## Not possible on Connect IQ today

Battery **level**, card **space**, remaining time and footage settings come back in replies longer
than 20 bytes (§10), so the watch only sees their first bytes. What does cross is shown instead:
USB / BAT / LOW and the card state. The settings can still be **written** from the watch
(writes are small): see the per-mode settings above.

**Elapsed time of a capture the watch did not start.** Checked carriers: the
`GET_CURRENT_CAPTURE_STATUS` reply (24 B, only the state crosses), the `0x2010` push (state plus a
field 2 of unknown meaning, sent on state changes only), `MEDIA_TIME` and remaining time (cut). None
gives the time already recorded, so the app does not show one: the `+` timer is the time since the
watch joined the recording.

## Open items

The earlier ideas (lens toggle, self-timer, interval, resolution / frame rate, EV) are built; see
the table above.

| Item | Status |
|---|---|
| Highlight / *Track That* marker | The watch sends `0x3C` with the key-time body of the original app; whether the X5 stores the marker in the file is not verified (an empty body is rejected, see the capture section of the protocol notes) |
