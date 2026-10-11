// =====================================================================
// Inner Frequency — audio engine (MRT2) + beat detection
//
// Before running:
//   1. Audio MIDI Setup (macOS) → output device → Format 48000 Hz
//   2. MRT2 for SuperCollider installed in
//      ~/Library/Application Support/SuperCollider/Extensions/MRT2
//      (then Language → Recompile Class Library)
//   3. Models downloaded to ~/Documents/Magenta/magenta-rt-v2/
//
// Run: put the cursor inside the block between parentheses, press Cmd+Return.
// Stop everything: Cmd+Period.
// =====================================================================

(
~model = \base;            // \base (2.4B) or \small (230M) if the Mac cannot keep up in real time
~bridgePort = 57200;       // where bridge.py listens for messages coming from here
~bufferSize = 8192;        // samples at 48 kHz (8192 ≈ 170 ms). Raise it if you hear dropouts
~preciseOnsets = true;     // note attacks exactly where the page sends them (needs patch_onset_mode.sh)
~outDevice = nil;          // nil = the system output, or a device name as macOS shows it (e.g. "MacBook Pro Speakers").
                           // It must run at 48 kHz: Bluetooth headphones in a call (Zoom, Teams) drop to 16-24 kHz
                           // and the server cannot start on them

~recDir = (thisProcess.nowExecutingPath ? "~/Desktop/inner_frequency.scd".standardizePath).dirname +/+ "recordings";   // R in the page records here

s.options.sampleRate = 48000;
s.options.numOutputBusChannels = 2;
s.options.numInputBusChannels = 0;    // no input: avoids sample-rate clashes with the microphone
s.options.outDevice = ~outDevice;

if(\MRT2.asClass.isNil) {
    ("MRT2 is not installed in SuperCollider. Check that the folder\n  "
        ++ Platform.userExtensionDir +/+ "MRT2"
        ++ "\ncontains MRT2.sc, MRT2.scx and mlx.metallib, then Language → Recompile Class Library.").error;
} {
s.waitForBoot {
    var modelsDir = "~/Documents/Magenta/magenta-rt-v2/models/".standardizePath;

    // clean up if the block is run again
    ~heartbeat !? { ~heartbeat.stop };
    ~analysis !? { ~analysis.free };
    ~mrt !? { ~mrt.free };
    s.sync;

    ~bridge = NetAddr("127.0.0.1", ~bridgePort);

    s.sampleRate !? { |sr|
        if(sr.round != 48000) {
            ("WARNING: the server runs at " ++ sr.round ++ " Hz. MRT2 needs 48000 Hz: "
                ++ "set 48000 Hz in Audio MIDI Setup and reboot the server.").warn;
        };
    };

    // ---------- 1. MRT2 ----------
    // Loads the resources and the base model from ~/Documents/Magenta/magenta-rt-v2/ by itself
    ~mrt = \MRT2.asClass.new(s);
    while { ~mrt.synth.isNil } { 0.05.wait };   // the synth is created in an internal fork
    s.sync;

    if(~model == \small) {
        var path = modelsDir +/+ "mrt2_small/mrt2_small.mlxfn";
        if(File.exists(path)) {
            ~mrt.model(path);
            "Model: mrt2_small".postln;
        } {
            ("Small model not found at " ++ path ++ ". Keeping the base model.").warn;
        };
    } {
        "Model: mrt2_base".postln;
    };
    ~mrt.bufferSize(~bufferSize);   // without this the buffer stays at its initial size, too small
    ~mrt.midiGate(0);               // never silence the output when no notes are held

    if(~preciseOnsets) {
        if(~mrt.respondsTo(\onsetMode)) {
            ~mrt.onsetMode(1);
            "Onset mode: precise attacks".postln;
        } {
            ("onsetMode is not available: run patch_onset_mode.sh and recompile the class library. "
                ++ "Until then the model places the attacks itself.").warn;
        };
    };
    128.do { |n| ~mrt.noteOff(n) };

    // ---------- 2. Output analysis: beats and level (for checking only) ----------
    // Reads what MRT2 has just written to outputs 0-1 (this synth sits at the tail of the group).
    SynthDef(\ifAnalysis, {
        var sound = Mix(In.ar(0, 2)) * 0.5;
        var chain = FFT(LocalBuf(1024), sound);    // 1024 points: the size BeatTrack expects at 48 kHz
        var quarters, eighths, sixteenths, tempo;
        #quarters, eighths, sixteenths, tempo = BeatTrack.kr(chain);
        SendReply.kr(quarters, '/ifa/beat', tempo);
        SendReply.kr(Impulse.kr(20), '/ifa/level', Amplitude.kr(sound, 0.01, 0.25));
    }).add;
    s.sync;
    ~analysis = Synth.tail(s, \ifAnalysis);

    OSCdef(\ifaBeat,  { |msg| ~bridge.sendMsg('/if/beat',  msg[3]) }, '/ifa/beat');
    OSCdef(\ifaLevel, { |msg| ~bridge.sendMsg('/if/level', msg[3]) }, '/ifa/level');

    // ---------- 3. Commands from the page (through bridge.py) ----------
    OSCdef(\ifPrompt,      { |msg| ~mrt.prompt(msg[1], msg[2], msg[3]) }, '/if/prompt');
    OSCdef(\ifClear,       { |msg| ~mrt.clearPrompt(msg[1]) },          '/if/clear');
    OSCdef(\ifDrumless,    { |msg| ~mrt.drumless(msg[1]) },             '/if/drumless');
    OSCdef(\ifTemperature, { |msg| ~mrt.temperature(msg[1]) },          '/if/temperature');
    OSCdef(\ifVolume,      { |msg| ~mrt.volume(msg[1]) },               '/if/volume');
    OSCdef(\ifReset,       { |msg| ~mrt.reset },                        '/if/reset');
    OSCdef(\ifNoteOn,      { |msg| ~mrt.noteOn(msg[1]) },               '/if/noteon');
    OSCdef(\ifNoteOff,     { |msg| ~mrt.noteOff(msg[1]) },              '/if/noteoff');
    OSCdef(\ifAllOff,      { |msg| 128.do { |n| ~mrt.noteOff(n) } },    '/if/allnotesoff');
    OSCdef(\ifUnmask,      { |msg| ~mrt.unmaskWidth(msg[1]) },          '/if/unmaskwidth');
    OSCdef(\ifCfgNotes,    { |msg| ~mrt.cfgNotes(msg[1]) },             '/if/cfgnotes');
    OSCdef(\ifCfgStyle,    { |msg| ~mrt.cfgMusicCoCa(msg[1]) },         '/if/cfgmusiccoca');
    OSCdef(\ifRec, { |msg|   // the page's R key: record MRT2's output, the same moment as the video
        if(msg[1] == 1) {
            var path = ~recDir +/+ msg[2].asString ++ ".wav";
            File.mkdir(~recDir);
            fork {
                s.recHeaderFormat = "wav"; s.recSampleFormat = "int24"; s.recChannels = 2;
                s.prepareForRecord(path, 2);
                s.sync;
                s.record(path);
                s.sync;
                ~bridge.sendMsg('/if/recstarted', msg[2].asString);   // lets the page note the exact offset
                ("Recording audio to " ++ path).postln;
            };
        } {
            s.stopRecording;
        };
    }, '/if/rec');

    // ---------- 4. Heartbeat to the page (once a second) ----------
    ~heartbeat = Routine { loop { ~bridge.sendMsg('/if/status', 1); 1.wait } }.play;

    "".postln;
    "Inner Frequency ready.".postln;
    ("sclang receives commands on port " ++ NetAddr.langPort
        ++ (if(NetAddr.langPort != 57120) { "  →  start the bridge with: --sc-port " ++ NetAddr.langPort } { "" })).postln;
};
};
)

// ---------------------------------------------------------------------
// Handy commands (one at a time, Cmd+Return on the line)
// ---------------------------------------------------------------------
// ~mrt.bufferSize(16384);  // more headroom against dropouts, about 170 ms more delay
// ~mrt.volume(-6);         // dB
// ~mrt.reset;              // clears the model's memory
// ~mrt.unmaskWidth(127);   // the model plays only the notes we send (0 = it may add its own); the page sets this ('Scale lock')
// OSCdef.trace(true);      // print every incoming OSC message (false to stop)
