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

// Refused writes are counted; an accepted write clears the streak; the fourth refusal in a row
// drops the link (device released, queue cleared, rescan) instead of retrying forever.
(:test)
function pumpRefusalsDropWedgedLink(logger) {
	resetQueue();
	var d = new RefusingBle();
	d.device = {};   // stand-in: only compared with null by pump()
	BLEBarrel.queueFrame(BLEBarrel.frameX5(0x05, []b));
	d.pump(); d.pump(); d.pump();
	var three = d.wedgeCount == 3 && d.device != null && BLEBarrel.queue.size() == 1;
	d.refuse = false;
	d.pump();
	var cleared = d.wedgeCount == 0 && d.writes == 1 && BLEBarrel.queue.size() == 0;
	d.writing = false; d.refuse = true;
	BLEBarrel.queueFrame(BLEBarrel.frameX5(0x05, []b));
	for (var i = 0; i < 4; i++) { d.pump(); }
	logger.debug("three=" + three + " cleared=" + cleared + " device=" + d.device + " q=" + BLEBarrel.queue.size() + " scanning=" + d.scanning);
	var dropped = d.device == null && BLEBarrel.queue.size() == 0 && d.wedgeCount == 0 && d.scanning;
	d.scanning = false;
	return three && cleared && dropped;
}

// A backed-up queue drops GPS telemetry and keep-alives, never a user command, and never the
// rest of a frame whose first chunk already left.
(:test)
function queueBoundKeepsUserCommands(logger) {
	resetQueue();
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
	resetQueue();
	return n <= BLEBarrel.QUEUE_CAP && keep == 2 && headKept && stopAt2 && lastIsStart && drops % 4 == 0 && allKept;
}

class StartCountingBle extends BLEBarrel.BleDevice {
	var starts = 0;
	function initialize() { BleDevice.initialize(); }
	function startX5() { starts++; linkReady = true; }
}

// The advertised name did not say X5 (missing / unexpected): a real 0x2053 push from the watch
// log switches the app to X5 handling, starts the X5 session that the connect path skipped, and
// the push itself is applied. A frame both generations send (0x2010) does not switch.
(:test)
function x5OnlyFramePromotes(logger) {
	var d = new StartCountingBle();
	BLEBarrel.x5Proto = false;
	BLEBarrel.deviceName = "Insta360 cam";
	d.device = {};   // connected; only compared with null here
	d.linkReady = false;
	BLEBarrel.recState = BLEBarrel.stateStopRec;
	BLEBarrel.modeReq = null; BLEBarrel.modeHoldUntil = 0;
	BLEBarrel.currentMode = "DefaultV"; BLEBarrel.currentLabel = "Default Video";
	d.onCharacteristicChanged(null, [0x14, 0, 0, 0, 0x04, 0, 0, 0x10, 0x20, 0x02, 0xff, 0, 0, 0x80, 0, 0, 0x08, 0x00, 0x10, 0x06]b);
	var notYet = !BLEBarrel.isX5() && d.starts == 0;
	d.onCharacteristicChanged(null, [0x16, 0, 0, 0, 0x04, 0, 0, 0x53, 0x20, 0x02, 0xff, 0x8a, 0x43, 0xf4, 0, 0, 0x08, 0x03, 0x10, 0x64]b);
	logger.debug("notYet=" + notYet + " x5=" + BLEBarrel.isX5() + " starts=" + d.starts + " mode=" + BLEBarrel.currentMode + " menu=" + BLEBarrel.menuLevel);
	var ok = notYet && BLEBarrel.isX5() && d.starts == 1 && BLEBarrel.currentMode.equals("p3") && BLEBarrel.menuLevel == 2;
	// a reconnect with an unrecognised name keeps the verdict; a known older camera resets it
	d.adoptName("Insta360 cam");
	var kept = BLEBarrel.isX5();
	d.adoptName("X3 ABCDEF");
	var reset = !BLEBarrel.isX5() && BLEBarrel.menuLevel == 1;
	d.adoptName("X5 1ABCDE");
	BLEBarrel.x5Proto = false;
	d.device = null;
	return ok && kept && reset;
}
