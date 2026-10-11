#!/bin/bash
# Inner Frequency — adds "onset mode" to MRT2 for SuperCollider, then rebuilds and reinstalls it.
#
# Why: out of the box, the SuperCollider version of MRT2 tells the model which notes are held,
# and the model decides by itself where to place the attacks. With onset mode on, every attack
# lands exactly where the page sends it, so the tempo set by I is followed precisely.
# The engine already supports this (RealtimeRunner::set_onset_mode); the SuperCollider
# plugin just does not expose it. This script adds one command, "onsetmode".
#
# Usage: in Terminal type  bash  (with a space), drag this file in, press Return.
# Safe to run more than once.

set -e
ok()   { printf "\n\033[32m✔ %s\033[0m\n" "$1"; }
step() { printf "\n\033[1m▶ %s\033[0m\n" "$1"; }
stop() { printf "\n\033[31m✘ %s\033[0m\n" "$1"; exit 1; }

REPO="$HOME/magenta-realtime"
[ -d "$REPO/examples/sc" ] || stop "Magenta RealTime not found in $REPO. Run install_mrt2.sh first."
cd "$REPO"
source .venv/bin/activate

step "1/3 Patching the SuperCollider plugin"
python3 - <<'EOF'
import sys
mm = 'examples/sc/MRT2.mm'
s = open(mm).read()
if 'MRT2_cmd_onsetmode' not in s:
    a = 'void MRT2_cmd_drumless(Unit* u, sc_msg_iter* args) {'
    b = '    DefineUnitCmd("MRT2UGen", "drumless",     MRT2_cmd_drumless);'
    if a not in s or b not in s:
        sys.exit('MRT2.mm has changed upstream: anchor lines not found, patch not applied.')
    s = s.replace(a, 'void MRT2_cmd_onsetmode(Unit* u, sc_msg_iter* args) {\n'
                     '    auto* unit = reinterpret_cast<MRT2UGen*>(u);\n'
                     '    unit->engine->set_onset_mode(args->geti());\n'
                     '}\n' + a, 1)
    s = s.replace(b, b + '\n    DefineUnitCmd("MRT2UGen", "onsetmode",    MRT2_cmd_onsetmode);', 1)
    open(mm, 'w').write(s)
    print('MRT2.mm patched')
else:
    print('MRT2.mm already patched')

sc = 'examples/sc/MRT2.sc'
s = open(sc).read()
if 'onsetMode' not in s:
    a = '    drumless  { |on = 1|         this.sendCmd("drumless", on.asInteger) }'
    if a not in s:
        sys.exit('MRT2.sc has changed upstream: anchor line not found, patch not applied.')
    s = s.replace(a, a + '\n    onsetMode { |mode = 1|       this.sendCmd("onsetmode", mode.asInteger) }', 1)
    open(sc, 'w').write(s)
    print('MRT2.sc patched')
else:
    print('MRT2.sc already patched')
EOF
ok "patched"

step "2/3 Rebuilding the SuperCollider plugin"
if [ -f build/CMakeCache.txt ]; then
  cd build
else
  mkdir -p build && cd build && cmake ..
fi
make mrt2_sc -j8
cd ..
ok "built"

step "3/3 Installing into SuperCollider's Extensions folder"
EXT="$HOME/Library/Application Support/SuperCollider/Extensions/MRT2"
mkdir -p "$EXT"
ditto build/examples/sc "$EXT"
cp examples/sc/MRT2.sc examples/sc/example.scd "$EXT/"
grep -q onsetMode "$EXT/MRT2.sc" || stop "The installed MRT2.sc does not contain onsetMode."
ok "installed in $EXT"

printf "\nDone. In SuperCollider: Cmd+Period, Language → Recompile Class Library, then run inner_frequency.scd.\n"
printf "The Post window should print: Onset mode: precise attacks\n\n"
