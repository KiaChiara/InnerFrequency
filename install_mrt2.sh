#!/bin/bash
# Inner Frequency — installs MRT2 for SuperCollider and the bridge dependencies.
# Usage: in Terminal type  bash  (with a space), drag this file in, press Return.
# Safe to run again: completed steps are skipped.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ok()   { printf "\n\033[32m✔ %s\033[0m\n" "$1"; }
step() { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }
stop() { printf "\n\033[31m✘ %s\033[0m\n" "$1"; exit 1; }

[ "$(uname -m)" = "arm64" ] || stop "An Apple Silicon Mac (M1 or later) is required."

step "1/6 Xcode tools and Metal compiler"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  stop "The Xcode command line tools installer has opened. Finish it, then run this script again."
fi
if ! xcrun -sdk macosx metal --version >/dev/null 2>&1; then
  stop "The Metal compiler is missing (MLX needs it).
  1. Install Xcode from the App Store and open it once (accept the licence).
  2. In Terminal:  sudo xcode-select -s /Applications/Xcode.app
  3. Then:         xcodebuild -downloadComponent MetalToolchain
  Then run this script again."
fi
ok "present"

step "2/6 uv (Python manager)"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "$(uv --version)"

step "3/6 Magenta RealTime source in ~/magenta-realtime"
cd "$HOME"
if [ ! -d magenta-realtime/.git ]; then
  git clone --recurse-submodules https://github.com/magenta/magenta-realtime.git
fi
cd magenta-realtime
git submodule update --init --recursive
ok "downloaded"

step "4/6 Python environment and libraries (a few minutes)"
[ -d .venv ] || uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[mlx]"
uv pip install "cmake<3.28" "websockets>=13" python-osc
ok "installed"

step "5/6 Resources and models (in ~/Documents/Magenta/magenta-rt-v2)"
mrt models init
echo "Now pick the model to download (base for M2 Max / M3 Max / M4 Pro / M5 Max, otherwise small)."
mrt models download
ok "models ready"

step "6/6 Building and installing the SuperCollider plugin, with onset mode (several minutes)"
rm -rf build
bash "$HERE/patch_onset_mode.sh"

printf "\nFor the bridge use:  ~/magenta-realtime/.venv/bin/python bridge.py\n\n"
