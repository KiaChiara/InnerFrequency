"""Check how far apart the emotion prompts are in MRT2's style space.

MRT2 turns every prompt into one point (a 768-number MusicCoCa embedding).
Prompts that land close together will sound alike. This script reads the
prompts from index.html, embeds them exactly as the SuperCollider plugin does
(text -> MusicCoCa -> mapper, seed 0) and prints:

  1. a 6x6 table: average similarity between the prompts of two emotions
     (diagonal = how consistent one emotion is with itself)
  2. for every prompt, the closest prompt of a DIFFERENT emotion
  3. how much low and high intensity differ inside each prompt group

Similarity is cosine similarity: 1 = same direction, 0 = unrelated.
Only the comparisons matter, not the absolute numbers.

Run (on the Mac, after install_mrt2.sh):
  ~/magenta-realtime/.venv/bin/python check_prompts.py
  ~/magenta-realtime/.venv/bin/python check_prompts.py --try "dark ambient, cello drones"
  ~/magenta-realtime/.venv/bin/python check_prompts.py --list      (only prints the prompts)
"""

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def read_prompts(html_path):
    """Returns [(emotion, group, 'low'|'high', text)] from the CONFIG block of index.html."""
    src = html_path.read_text(encoding="utf-8")
    starts = [(m.start(), m.group(1)) for m in re.finditer(r"\{ id: '(\w+)', name: '[^']*'", src)]
    out = []
    for n, (pos, emo) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(src)
        block = src[pos:end]
        p0 = block.find("prompts: [")
        p1 = block.find("      ],", p0)
        if p0 < 0 or p1 < 0:
            continue
        groups = re.findall(r"low: '([^']*)',\s*high: '([^']*)'", block[p0:p1])
        for g, (low, high) in enumerate(groups):
            out.append((emo, g, "low", low))
            out.append((emo, g, "high", high))
    return out


def embed(texts):
    import numpy as np
    from magenta_rt.musiccoca import MusicCoCa
    model = MusicCoCa()
    # Same path as the plugin: text embedding mapped into audio space, noise seed 0.
    e = np.asarray(model.embed(list(texts), use_mapper=True, seed=0), dtype=np.float64)
    return e / np.linalg.norm(e, axis=1, keepdims=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", default=str(HERE / "index.html"), help="path to index.html")
    ap.add_argument("--try", dest="trial", action="append", default=[], help="a prompt to test against the emotions (repeatable)")
    ap.add_argument("--list", action="store_true", help="only list the prompts found")
    args = ap.parse_args()

    prompts = read_prompts(pathlib.Path(args.html))
    if not prompts:
        sys.exit("No prompts found in " + args.html)
    emotions = list(dict.fromkeys(p[0] for p in prompts))

    if args.list:
        for emo, g, lvl, text in prompts:
            print(f"{emo:9s} {g} {lvl:4s}  {text}")
        return

    import numpy as np
    texts = [p[3] for p in prompts] + args.trial
    print("Embedding", len(texts), "prompts with MusicCoCa ...")
    E = embed(texts)
    P, T = E[: len(prompts)], E[len(prompts):]
    S = P @ P.T
    idx = {e: [k for k, p in enumerate(prompts) if p[0] == e] for e in emotions}

    # 1. emotion x emotion
    print("\n1) Average similarity between emotions (diagonal: within the same emotion)\n")
    w = max(len(e) for e in emotions) + 1
    print(" " * w + "".join(f"{e[:8]:>9s}" for e in emotions))
    table = {}
    for a in emotions:
        row = []
        for b in emotions:
            block = S[np.ix_(idx[a], idx[b])]
            if a == b:
                n = len(idx[a])
                v = (block.sum() - n) / (n * n - n)   # leave out each prompt against itself
            else:
                v = block.mean()
            table[a, b] = v
            row.append(f"{v:9.3f}")
        print(f"{a:{w}s}" + "".join(row))

    print("\n   Pairs to watch (two emotions as close as, or closer than, one of them to itself):")
    flagged = False
    for i, a in enumerate(emotions):
        for b in emotions[i + 1:]:
            if table[a, b] >= min(table[a, a], table[b, b]) - 0.02:
                print(f"   - {a} / {b}: between {table[a, b]:.3f}, within {table[a, a]:.3f} / {table[b, b]:.3f}")
                flagged = True
    if not flagged:
        print("   none: every emotion is closer to itself than to the others")

    # 2. nearest prompt of another emotion
    print("\n2) For each prompt, the closest prompt of another emotion\n")
    for k, (emo, g, lvl, text) in enumerate(prompts):
        others = [j for j in range(len(prompts)) if prompts[j][0] != emo]
        j = max(others, key=lambda j: S[k, j])
        print(f"{emo:9s} {g} {lvl:4s} {S[k, j]:.3f}  {text!r}\n{'':19s}~ {prompts[j][0]} {prompts[j][1]} {prompts[j][2]}: {prompts[j][3]!r}")

    # 3. low vs high
    print("\n3) Low vs high intensity in each group (lower = intensity changes the style more)\n")
    for emo in emotions:
        groups = sorted({p[1] for p in prompts if p[0] == emo})
        vals = []
        for g in groups:
            lo = next(k for k, p in enumerate(prompts) if p[0] == emo and p[1] == g and p[2] == "low")
            hi = next(k for k, p in enumerate(prompts) if p[0] == emo and p[1] == g and p[2] == "high")
            vals.append(f"{S[lo, hi]:.3f}")
        print(f"{emo:9s} " + "  ".join(vals))

    # trial prompts
    if args.trial:
        print("\n4) Trial prompts: average similarity to each emotion\n")
        for t, v in zip(args.trial, T):
            sims = {e: float((P[idx[e]] @ v).mean()) for e in emotions}
            best = max(sims, key=sims.get)
            print(f"{t!r}\n   " + "  ".join(f"{e} {s:.3f}" for e, s in sims.items()) + f"   -> closest: {best}")


if __name__ == "__main__":
    main()
