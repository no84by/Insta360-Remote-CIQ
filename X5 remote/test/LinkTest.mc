using Toybox.Test;
using Toybox.Lang;
using BLEBarrel;

// A BLE stack that refuses every write, as on a wedged link.
class RefusingBle extends BLEBarrel.BleDevice {
	var writes = 0;
	var refuse = true;
	function initialize() { BleDevice.initialize(); }
	function writeChunk(chunk) {
		if (refuse) { throw new Lang.Exception(); }
		writes++;
		return true;
	}
}

function resetQueue() {
	BLEBarrel.queue = [];
	BLEBarrel.queueKind = [];
}

// Shared module state the tests change: put it back so the next test starts clean.
function resetTestState(d) {
	resetQueue();
	BLEBarrel.deviceName = "X5 1ABCDE"; BLEBarrel.menuLevel = 2;
	BLEBarrel.currentMode = "v0"; BLEBarrel.currentLabel = "Video"; BLEBarrel.videoMode = true;
	BLEBarrel.recState = BLEBarrel.stateStopRec; BLEBarrel.recAdopted = false;
	BLEBarrel.modeReq = null; BLEBarrel.modeHoldUntil = 0;
	BLEBarrel.photoSeq = -1; BLEBarrel.lapseSeq = -1;
	Settings.vals = {}; Settings.acked = {};
	if (d != null) {
		d.device = null; d.lastSetMs = null; d.lastModePushMs = null; d.optPending = null;
		if (d.scanning) {
			d.scanning = false;
			try { Toybox.BluetoothLowEnergy.setScanState(Toybox.BluetoothLowEnergy.SCAN_STATE_OFF); } catch (ex) { }
		}
	}
}

// A burst of refusals within one keep-alive tick (session start, settings) counts once; an
// accepted write clears the streak; refusals on the fourth tick in a row drop the link (device
// released, queue cleared, rescan). A START still waiting when the link drops is undone, so the
// UI does not wait for a confirmation that cannot come.
(:test)
function pumpRefusalsDropWedgedLink(logger) {
	var d = new RefusingBle();
	resetTestState(d);
	d.device = {};   // stand-in: only compared with null by pump()
	BLEBarrel.queueFrame(BLEBarrel.frameX5(0x05, []b));
	for (var i = 0; i < 6; i++) { d.pump(); }          // one tick, many refusals
	var burst = d.wedgeCount == 1 && d.device != null;
	d.refusedThisTick = false; d.pump();
	d.refusedThisTick = false; d.pump();
	var three = d.wedgeCount == 3 && d.device != null && BLEBarrel.queue.size() == 1;
	d.refuse = false;
	d.pump();
	var cleared = d.wedgeCount == 0 && d.writes == 1 && BLEBarrel.queue.size() == 0;
	d.writing = false; d.refuse = true;
	BLEBarrel.recState = BLEBarrel.stateStarting;      // user pressed START
	BLEBarrel.queueFrame(BLEBarrel.frameX5(0x04, [0x08, 0x01]b));
	for (var i = 0; i < 4; i++) { d.refusedThisTick = false; d.pump(); d.pump(); }
	logger.debug("burst=" + burst + " three=" + three + " cleared=" + cleared + " device=" + d.device
		+ " q=" + BLEBarrel.queue.size() + " scanning=" + d.scanning + " rec=" + BLEBarrel.recState);
	var dropped = d.device == null && BLEBarrel.queue.size() == 0 && d.wedgeCount == 0 && d.scanning
		&& BLEBarrel.recState == BLEBarrel.stateStopRec;
	// a STOP waiting when the link drops: back to recording until the connect sync says otherwise
	BLEBarrel.recState = BLEBarrel.stateStopping;
	d.linkLost();
	var stopUndone = BLEBarrel.recState == BLEBarrel.stateStartRec;
	resetTestState(d);
	return burst && three && cleared && dropped && stopUndone;
}

// A backed-up queue drops GPS telemetry and keep-alives, never a user command, and never the
// rest of a frame whose first chunk already left.
(:test)
function queueBoundKeepsUserCommands(logger) {
	resetTestState(null);
	var tele = new [71]b; tele[7] = 0x35; tele[8] = 0;   // legacy GPS telemetry: 4 chunks
	var stop = BLEBarrel.frameX5(0x05, []b);             // STOP_CAPTURE
	// head: the last two chunks of a telemetry frame already being sent
	BLEBarrel.enqueue(new [20]b, BLEBarrel.Q_DROP_CONT);
	BLEBarrel.enqueue(new [11]b, BLEBarrel.Q_DROP_CONT);
	BLEBarrel.queueFrame(stop);
	for (var i = 0; i < 10; i++) { BLEBarrel.queueFrame(tele); }
	BLEBarrel.queueFrame(BLEBarrel.frameX5(0x04, []b));  // START_CAPTURE
	var n = BLEBarrel.queue.size();
	var keep = 0;
	for (var i = 0; i < n; i++) { if (BLEBarrel.queueKind[i] == BLEBarrel.Q_KEEP) { keep++; } }
	var headKept = BLEBarrel.queueKind[0] == BLEBarrel.Q_DROP_CONT && BLEBarrel.queueKind[1] == BLEBarrel.Q_DROP_CONT;
	var stopAt2 = BLEBarrel.queue[2][7] == 0x05;
	var lastIsStart = BLEBarrel.queue[n - 1][7] == 0x04;
	// only whole telemetry frames were dropped: droppable chunks after the head come in fours
	var drops = 0;
	for (var i = 3; i < n; i++) { if (BLEBarrel.queueKind[i] != BLEBarrel.Q_KEEP) { drops++; } }
	logger.debug("size=" + n + " keep=" + keep + " drops=" + drops);
	// user commands only: the bound gives way rather than dropping them
	resetQueue();
	for (var i = 0; i < 20; i++) { BLEBarrel.queueFrame(stop); }
	var allKept = BLEBarrel.queue.size() == 20;
	resetTestState(null);
	return n <= BLEBarrel.QUEUE_CAP && keep == 2 && headKept && stopAt2 && lastIsStart && drops % 4 == 0 && allKept;
}

// The model comes from the connected camera's name: older cameras' names get the legacy protocol,
// any other name the X5 protocol; a different camera gets its own verdict.
(:test)
function modeFollowsConnectedName(logger) {
	var d = new BLEBarrel.BleDevice();
	d.adoptName("X5 1ABCDE");
	var x5 = BLEBarrel.isX5() && BLEBarrel.menuLevel == 2;
	d.adoptName("X3 ABCDEF");
	var x3 = !BLEBarrel.isX5() && BLEBarrel.menuLevel == 1;
	d.adoptName("Insta360 cam");
	var other = BLEBarrel.isX5() && BLEBarrel.menuLevel == 2;
	d.adoptName("X4 ABCDEF");
	var x4 = !BLEBarrel.isX5() && BLEBarrel.menuLevel == 2;
	BLEBarrel.deviceName = "n/a";
	var none = !BLEBarrel.isX5();
	logger.debug("x5=" + x5 + " x3=" + x3 + " other=" + other + " x4=" + x4 + " none=" + none);
	resetTestState(d);
	return x5 && x3 && other && x4 && none;
}
