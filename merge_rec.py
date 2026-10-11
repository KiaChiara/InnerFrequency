"""Join a recording made with the R key into one MP4.

Audio: SuperCollider saves it next to the .scd as  recordings/IF_<date-time>.wav

Video, two cases (the 'Recording' menu in the panel):
  screen      the macOS screen recording (Cmd+Shift+5). When the audio started, the page flashed a magenta
              square top left: the script finds it, starts the video right after it and lines the audio up.
  scene only  the page saved the video to Downloads as  IF_<date-time>_a<offset>.mp4/.webm
              <offset> is how many seconds after the video the audio started.

Run (on the Mac):
  ~/magenta-realtime/.venv/bin/python merge_rec.py                 (the newest audio and its video)
  ~/magenta-realtime/.venv/bin/python merge_rec.py VIDEO [AUDIO]   (specific files)
  add  --shift 0.03  to move the audio later (negative: earlier) if the steps and the music look off

The result goes to recordings/IF_<date-time>.mp4 (H.264 video, 320 kb/s AAC audio).
Needs ffmpeg: either installed on the system, or the imageio-ffmpeg package
  ~/.local/bin/uv pip install --python ~/magenta-realtime/.venv/bin/python imageio-ffmpeg
"""

import argparse
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
RECORDINGS = HERE / "recordings"
HOME = pathlib.Path.home()
DOWNLOADS = HOME / "Downloads"
SCREEN_DIRS = [HOME / "Desktop", HOME / "Movies", HOME / "Downloads", HOME / "Documents"]   # where macOS may save screen recordings
SCAN_SECONDS = 600   # look for the mark in the first 10 minutes of the screen recording


def ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found. Install it with:\n  ~/.local/bin/uv pip install --python ~/magenta-realtime/.venv/bin/python imageio-ffmpeg")


def newest(paths):
    paths = [p for p in paths if p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def find_mark(ff, video):
    """Times (s) of the first frame showing the magenta square and of the first frame after it."""
    # the top-left quarter of the screen, averaged down to a 32x20 grid: the square may sit lower than the corner
    # (on a MacBook with a notch, full-screen pages start below a black strip). One line of showinfo per frame gives its time.
    W, H = 32, 20
    cmd = [ff, "-hide_banner", "-nostats", "-t", str(SCAN_SECONDS), "-i", str(video),
           "-map", "0:v:0", "-vf", f"crop=iw/4:ih/4:0:0,scale={W}:{H}:flags=area,showinfo",
           "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    p = subprocess.run(cmd, capture_output=True)
    times = [float(x) for x in re.findall(rb"pts_time:\s*(-?[\d.]+)", p.stderr)]
    size = W * H * 3
    on = None
    for n, t in enumerate(times):
        px = p.stdout[n * size:(n + 1) * size]
        if len(px) < size:
            break
        cells = sum(1 for k in range(0, size, 3)
                    if px[k] > 150 and px[k + 2] > 150 and px[k + 1] < 110 and px[k] - px[k + 1] > 80)
        magenta = cells >= 20   # the square fills well over 20 cells; scenes have no such magenta
        if on is None and magenta:
            on = t
        elif on is not None and not magenta:
            return on, t
    return (on, None) if on is not None else (None, None)


def encode(ff, inputs, out):
    cmd = [ff, "-y", "-loglevel", "error", "-stats", *inputs,
           "-map", "0:v:0", "-map", "1:a:0",
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",              # H.264 needs even sizes
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
           "-fps_mode", "cfr", "-r", "60",                          # screen and browser recordings have a variable frame rate
           "-c:a", "aac", "-b:a", "320k",
           "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", help="the video (default: found automatically)")
    ap.add_argument("audio", nargs="?", help="the SuperCollider .wav (default: the newest in recordings/)")
    ap.add_argument("--shift", type=float, default=0.0, help="seconds to move the audio later (negative: earlier)")
    args = ap.parse_args()
    ff = ffmpeg()

    audio = pathlib.Path(args.audio).expanduser() if args.audio else newest(RECORDINGS.glob("IF_*.wav"))
    video = pathlib.Path(args.video).expanduser() if args.video else None

    if video is None:   # the scene-only video of this audio, if there is one; otherwise the newest screen recording
        if audio is None:
            sys.exit(f"No IF_….wav in {RECORDINGS}")
        video = newest(list(DOWNLOADS.glob(f"{audio.stem}_*.mp4")) + list(DOWNLOADS.glob(f"{audio.stem}_*.webm")))
        if video is None:
            video = newest([p for d in SCREEN_DIRS if d.is_dir() for ext in ("*.mov", "*.mp4") for p in d.glob(ext)
                            if not p.name.startswith("IF_")])
        if video is None:
            sys.exit("No video found. Pass it by hand: merge_rec.py VIDEO")

    m = re.match(r"(IF_\d{8}-\d{6})(?:_a(-?[\d.]+)|_noaudio)?$", video.stem)
    if m and video.stem.endswith("_noaudio"):
        sys.exit("This video was recorded without SuperCollider's audio (_noaudio).")
    if m and not args.audio:   # a scene-only video: its own audio, by name
        audio = RECORDINGS / f"{m.group(1)}.wav"
    if audio is None or not audio.exists():
        sys.exit(f"Audio not found: {audio}\n(was SuperCollider running when you pressed R?)")

    RECORDINGS.mkdir(exist_ok=True)
    out = RECORDINGS / f"{audio.stem}.mp4"

    if m and m.group(2) is not None:   # scene only: the offset is in the name
        offset = float(m.group(2)) + args.shift
        print(f"Video  {video}\nAudio  {audio}  (+{offset:.3f} s)\nOutput {out}")
        encode(ff, ["-i", str(video), "-itsoffset", f"{offset:.3f}", "-i", str(audio)], out)
    else:   # screen recording: find the mark
        print(f"Video  {video}\nAudio  {audio}\nLooking for the magenta mark ...")
        on, off = find_mark(ff, video)
        if on is None:
            sys.exit("The magenta mark was not found in the first 10 minutes.\n"
                     "Record the entire screen, and start the screen recording before pressing R.")
        if off is None:
            sys.exit(f"The mark appears at {on:.3f} s but never goes away: is this the right video?")
        skip = off - on - args.shift   # the video starts right after the mark; the audio began when the mark appeared
        print(f"Mark   {on:.3f} → {off:.3f} s\nOutput {out}")
        audio_in = ["-ss", f"{skip:.3f}", "-i", str(audio)] if skip >= 0 else ["-itsoffset", f"{-skip:.3f}", "-i", str(audio)]
        encode(ff, ["-ss", f"{off:.3f}", "-i", str(video), *audio_in], out)
    print("Done.")


if __name__ == "__main__":
    main()
