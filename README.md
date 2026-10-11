# Inner Frequency — screen prototype

A first-person walk through six scenes, one for each emotion: calm, joy, sadness, anger, fear, surprise. Two values drive it, the emotion on stage and its intensity, set by hand from a panel. From them the music is generated in real time and the scene walks to its beat, one step per beat.

Requires an Apple Silicon Mac: the music model runs locally.

Three parts running on the same Mac:

| File | What it does |
|---|---|
| `index.html` | Panel for E and I, the diagram's state machine (E every 3 s, I every 2 s, 2-bar fades), the note clock, and the first-person three.js video |
| `bridge.py` | Serves the page at `http://localhost:8000` and bridges WebSocket (browser) ↔ OSC (SuperCollider) |
| `inner_frequency.scd` | Runs MRT2 inside SuperCollider, executes the page's commands, reports the beats it hears back to the page |
| `install_mrt2.sh` | One-time install of Magenta RealTime, models, bridge libraries and the SuperCollider plugin |
| `patch_onset_mode.sh` | Adds precise note attacks ("onset mode") to the SuperCollider plugin and rebuilds it |
| `check_prompts.py` | Measures how far apart the emotion prompts are in MRT2's style space (prompts that land close together sound alike) |
| `merge_rec.py` | Joins a recording made with the R key (video from the macOS screen recording or from the page + audio from SuperCollider) into one MP4 |

```
panel (E, I) → state machine ─┬→ prompts and weights ─┐
                              ├→ notes on the BPM grid ┼→ bridge.py → SuperCollider → MRT2 → speakers
                              └→ video (one step per beat, delayed by the audio latency)
```

## How E and I drive the music

- **E** picks the prompt group (three per emotion, never the same twice in a row), the mode and a root:
  Calm major · Joy mixolydian · Sadness minor blues · Anger phrygian · Fear locrian · Surprise whole tone.
- **I** sets the **BPM directly** (60 → 150). The page sends MRT2 notes of the current scale on that tempo:
  a chord plus a bass note. Higher I means more frequent attacks, four-note chords, faster chord changes.
- The prompt text only describes genre, instruments and character: short and concrete works best, because MRT2 turns each prompt into a single point in a style space. No scale or tempo words: the notes carry those. (Slots 4–5 can add a tempo word, `tempoPrompt`, off by default.)
- The camera takes one step per beat of the same clock, delayed by the audio latency (the **Step delay** slider).

## Install (once)

1. **SuperCollider**: download from supercollider.github.io.
2. **Xcode** from the App Store (needed for the Metal compiler). Open it once, then in Terminal:
   ```
   sudo xcode-select -s /Applications/Xcode.app
   xcodebuild -downloadComponent MetalToolchain
   ```
3. In Terminal type `bash ` (with a space), drag `install_mrt2.sh` in, press Return.
   It installs everything, asks which model to download, and builds the SuperCollider plugin with onset mode.
4. In SuperCollider: *Language → Recompile Class Library*.
5. **48 kHz audio**: Audio MIDI Setup → output device → Format 48000 Hz.

Already installed before onset mode existed? Run only `patch_onset_mode.sh` (same way as above), then Recompile Class Library.

## Start (every time)

1. Open `inner_frequency.scd` in SuperCollider, cursor inside the block, **Cmd+Return**. Wait for "Inner Frequency ready." The Post window should also print "Onset mode: precise attacks".
2. In Terminal: type `~/magenta-realtime/.venv/bin/python ` (with a space), drag `bridge.py` in, press Return. The browser opens `http://localhost:8000`.
3. In the panel **Bridge** and **MRT2** turn green. The grey line under them shows the version number (e.g. 1.01), the graphics card and any graphics errors in red. **Heard** shows the tempo detected on MRT2's output after a few seconds: compare it with **Tempo**.

Without SuperCollider the page still runs: video only.

## Controls

- Keys **1–6**: emotion · **← →**: intensity ±5 · **H**: hide the panel · **R**: start/stop a recording · **S**: save a still of the scene
- **Automatic simulator**: I changes every 2 s, E every 20–40 s
- **Light graphics**: lower resolution and no bloom, leaves more GPU to MRT2
- **Step delay**: time between a note being sent and being heard. Adjust until steps land on the beats you hear

## Where to change things

All in `index.html`, in the `CONFIG` block at the top of the script:

- `emotions[].prompts`: prompt groups; `low` weighs more at low I, `high` at high I
- `emotions[].mode`, `roots`, `degrees`, `skip`: scale, possible roots, chords used, chance of skipped attacks
- `emotions[].world`: sky, fog, light, ground, walls, camera behaviour, particles
- `emotions[].world.kit`: the elements of each world. Each entry names a recipe (a small structure built from primitives: a pier, an arcade, a dead tree, a block tower…), where it goes (`zone`), how often (`density` per metre or `spacing` in metres), its size and motion. Entries marked `always` appear in every scene; from the others each scene picks `pick` at random. Every recipe is built in five random variants at load
- `emotions[].world.groundPattern` and `skyline`: ground texture and horizon silhouette of each world
- The recipes themselves are in `RECIPES`, inside block 4
- World switches used by single worlds (0 = off): `rim`/`rimColor` (glowing outlines), `wallGlow`, `groundGlow` (faint self-light), `fogTorch`, `beam`, `motes` (mist, haze and dust visible only in the torch beam), `torchDim` (the torch fades down and back), `heartVig` (edges close in and beat with I)
- Kit entry extras: `shy: 'dissolve' | 'close'` (vanishes or shuts once the torch finds it), motions `lean`, `takeoff`, `pendulum`, `slam`, `grind`, `turn`
- `emotions[].I`: an emotion can replace any `I` curve with its own `[at I=0, at I=100]`. Sadness does: the higher I, the slower the tempo and the walk
- `styleGuidance`: during a change of emotion MRT2 follows the new prompt more strongly, so the previous instruments fade out sooner
- `notes.mode` (also in the panel, 'Notes to MRT2'): off · light (a short bass pulse per beat, one chord tone per bar, loosely followed) · full (held chords and bass, strictly followed)
- `I`: how intensity becomes BPM, temperature, drums, stride, bob, shake, density, bloom
- `notes.unmaskWidth`: 0 (default) lets the model add its own notes, 127 ('Scale lock') makes it play only ours · `notes.cfgNotes`: how strictly it follows them
- `sampleE`, `sampleI`, `fadeBars`: the diagram's timings

## Rules in the code

- A new E during a fade waits for the fade to end and starts at the next reading.
- MRT2 prompt slots are used in pairs: 0–1 for the current scene, 2–3 for the incoming one. A scene change is a weight crossfade.
- The new key starts on the next bar.
- Notes are sent only after SuperCollider has received the full state.

## Things to check on the first run

1. **Tempo vs Heard**: with onset mode on, the heard tempo should follow the Tempo chip. BeatTrack leans toward 100–120 bpm and needs about 6 s, so small differences are expected.
2. **Mode**: **Scale lock** in the panel (off by default) makes MRT2 play only the notes we send: it stays in the mode but just holds our chords. Off, the model adds its own notes, sometimes outside the scale. `notes.cfgNotes` sets how strictly it follows the notes.
3. **Dropouts**: raise `~bufferSize` in `inner_frequency.scd` or turn on Light graphics.

To see OSC traffic in SuperCollider: `OSCdef.trace(true);`. In the bridge: `--verbose`.

## Checking the prompts

`check_prompts.py` reads the prompts from `index.html`, turns each into MRT2's style point exactly as the plugin does, and prints how close the emotions are to each other. In Terminal:

```
~/magenta-realtime/.venv/bin/python check_prompts.py
~/magenta-realtime/.venv/bin/python check_prompts.py --try "dark ambient, cello drones"
```

Run it from the folder that holds `index.html` (or pass `--html path`). `--try` tells you which emotion a new prompt sits closest to, before you put it in.

## Recording and stills

The *Recording* menu in the panel chooses what R does.

**screen** (default): the video is made by macOS, so it has the full screen resolution and shows the panel and the pointer.
1. Put the browser in full screen. Press **Cmd+Shift+5**, choose *Record Entire Screen*, click *Record*.
2. Press **R**. SuperCollider starts recording its own output (48 kHz, 24 bit) to `recordings/IF_<date-time>.wav` next to the .scd, and a magenta square flashes top left for a moment: it marks when the audio started. Keep the pointer away from the top edge at that moment, so the browser bar does not cover the square.
3. Play. Press **R** again to stop the audio, then stop the screen recording (the stop button in the menu bar). macOS saves it to the Desktop unless you chose another place.
4. Join them: `~/magenta-realtime/.venv/bin/python merge_rec.py`. It takes the newest audio and the newest screen recording (Desktop, Movies, Downloads, Documents), finds the square, starts the video right after it and writes `recordings/IF_<date-time>.mp4`. Specific files: `merge_rec.py VIDEO AUDIO`.

**scene only**: the 3D view with the lens drops and the vignette, nothing else, recorded by the page. A small red dot shows while recording; it is not in the video. On stop the video lands in **Downloads** as `IF_<date-time>_a<offset>.mp4` (or `.webm`); `merge_rec.py` joins it with its audio in the same way.

- If steps and music look slightly off in the result: `merge_rec.py --shift 0.03` moves the audio 30 ms later (negative: earlier).
- `merge_rec.py` needs ffmpeg, once: `~/.local/bin/uv pip install --python ~/magenta-realtime/.venv/bin/python imageio-ffmpeg`
- **S** saves a PNG of the scene (no panel) to Downloads, named with the emotion and the intensity.

## Credits

- Music generated with [Magenta RealTime](https://github.com/magenta/magenta-realtime) (Google, Magenta project), run inside [SuperCollider](https://supercollider.github.io)
- Visuals built with [three.js](https://threejs.org)

Code: MIT license (see `LICENSE`). Magenta RealTime, its models and the other tools keep their own licenses.
