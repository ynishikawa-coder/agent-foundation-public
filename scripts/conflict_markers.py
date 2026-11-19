#!/usr/bin/env python3
"""衝突の印（git が衝突を解けなかった所に書く <<<<<<<・|||||||・=======・>>>>>>>）が残った file を拒む。

  python3 scripts/conflict_markers.py [--root <repo の根>]

なぜ在るか: main を取り込む merge で衝突を手で解いた窓が、印を残したまま commit・push できた（PR #51 の
qa-html の SKILL.md に印が残り、起動時に窓へ届く skill が 2 つの版と印のまま配られかけた）。レビューの窓も
remerge-diff を読んで見落とした。人や AI の目に頼らず、印の残った木は検査の入口（check_all・CI の check）で赤にする。

見る物: git に載った file と、まだ載せていない新しい file（.gitignore の外）の全部。中身が字で読めない file は飛ばす。
印の形: 行の頭が <<<<<<<・|||||||・>>>>>>> の 7 字で、その後が空白か行の終わり／行がちょうど ======= の 7 字。
  （ちょうど 7 字の ======= は Markdown の見出しの下線にもなりうるが、この repo では使わない。使う時は 8 字以上にする）
exit: 0=緑 / 1=赤（file と行を名指し） / 2=照らせない（git が無い等）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(r"^(?:(?:<{7}|\|{7}|>{7})(?:[ \t].*)?|={7})\r?$")
ROOT_CAUSE = ("直し: 印を消すだけで済ませず、両方の版を読んで 1 つの文に合わせ、なぜ印のまま commit できたか"
              "（衝突を解いた後に check_all を回さず push した等）を細目 §3「まず構造を疑う」で探して直す")


def files(root: Path) -> list[str]:
    out: list[str] = []
    for args in (["ls-files", "-z"], ["ls-files", "-z", "--others", "--exclude-standard"]):
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True)
        if r.returncode != 0:
            raise OSError(r.stderr.decode("utf-8", "replace").strip())
        out += [p for p in r.stdout.decode("utf-8").split("\0") if p]
    return sorted(set(out))


def hits(root: Path) -> list[str]:
    found: list[str] = []
    for rel in files(root):
        p = root / rel
        if not p.is_file() or p.is_symlink():
            continue
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue  # 字で読めない file（画像など）
        text = data.decode("utf-8", "replace")
        for n, line in enumerate(text.splitlines(), 1):
            if MARKER.match(line):
                found.append(f"{rel}:{n}: {line[:40]}")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    try:
        found = hits(Path(a.root))
    except OSError as e:
        print(f"衝突の印: 照らせない（{e}）")
        return 2
    if not found:
        print("衝突の印: 緑（残った印 0）")
        return 0
    print(f"衝突の印: 赤（{len(found)} 行）")
    for f in found:
        print(f"  ✗ {f}")
    print(ROOT_CAUSE)
    return 1


if __name__ == "__main__":
    sys.exit(main())
