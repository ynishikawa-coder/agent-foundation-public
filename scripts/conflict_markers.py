#!/usr/bin/env python3
"""衝突の印（git が衝突を解けなかった所に書く <<<<<<<・|||||||・=======・>>>>>>>）が残った file を拒む。

  python3 scripts/conflict_markers.py [--root <repo の根>]

なぜ在るか: main を取り込む merge で衝突を手で解いた窓が、印を残したまま commit・push できた（PR #51 の
qa-html の SKILL.md に印が残り、起動時に窓へ届く skill が 2 つの版と印のまま配られかけた）。レビューの窓も
remerge-diff を読んで見落とした。人や AI の目に頼らず、印の残った木は検査の入口（check_all・CI の check）で赤にする。

見る物: git に載った file と、まだ載せていない新しい file（.gitignore の外）の全部。飛ばす物を作らない:
  - symlink は指す先の道の字（git が blob に持つ中身）を照らす（指す先の file は自分の行で照らす）。
  - 手元で消した追跡中の file は、index に載った中身（次の commit に入る物）を照らす。
  - 頭に NUL がある file は、BOM で UTF-16・UTF-32 を読み分けて字で照らす。BOM の無い物は、そのままのバイトと
    UTF-16（LE・BE）の読みの全部で印の行を探す（印は ASCII の字なので、どの読みでも探せる）。
  - 読めない物（読む権限が無い・index に中身が無い等）は数えて名指し、exit 3（照らしていない）で終える＝緑に数えない。
印の形: 行の頭が <<<<<<<・|||||||・>>>>>>> の 7 字で、その後が空白か行の終わり／行がちょうど ======= の 7 字。
  （ちょうど 7 字の ======= は Markdown の見出しの下線にもなりうるが、この repo では使わない。使う時は 8 字以上にする）
exit: 0=緑 / 1=赤（file と行を名指し） / 2=照らせない（git が無い等） / 3=照らしていない file が在る（名指す・印は無い）。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

MARKER = re.compile(r"^(?:(?:<{7}|\|{7}|>{7})(?:[ \t].*)?|={7})\r?$")
ROOT_CAUSE = ("直し: 印を消すだけで済ませず、両方の版を読んで 1 つの文に合わせ、なぜ印のまま commit できたか"
              "（衝突を解いた後に check_all を回さず push した等）を細目 §3「まず構造を疑う」で探して直す")
BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def files(root: Path) -> list[str]:
    out: list[str] = []
    for args in (["ls-files", "-z"], ["ls-files", "-z", "--others", "--exclude-standard"]):
        r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True)
        if r.returncode != 0:
            raise OSError(r.stderr.decode("utf-8", "replace").strip())
        out += [p for p in r.stdout.decode("utf-8").split("\0") if p]
    return sorted(set(out))


def texts(data: bytes) -> list[str]:
    """中身を印を探せる字の読みの並びにする。頭に NUL の無い物は UTF-8。在る物は BOM で読み分け、BOM が無ければ
    そのままのバイト（latin-1）と UTF-16 の LE・BE（始めを 1 バイトずらした読みも）の全部（どれかで印の行が読めれば見つかる）。"""
    if b"\0" not in data[:8192]:
        return [data.decode("utf-8", "replace")]
    for bom, enc in BOMS:
        if data.startswith(bom):
            return [data[len(bom):].decode(enc, "replace")]
    out = [data.decode("latin-1")]
    for enc in ("utf-16-le", "utf-16-be"):
        for i in (0, 1):
            body = data[i:]
            out.append(body[:len(body) - len(body) % 2].decode(enc, "replace"))
    return out


def index_blob(root: Path, rel: str) -> bytes | None:
    """index に載った rel の中身（stage 0）。無ければ None。"""
    r = subprocess.run(["git", "cat-file", "blob", f":0:{rel}"], cwd=root, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def scan(root: Path) -> tuple[list[str], list[str]]:
    """(印の行の名指し, 照らしていない file の名指し)。"""
    found: list[str] = []
    unread: list[str] = []
    for rel in files(root):
        p = root / rel
        try:
            if p.is_symlink():
                data = os.fsencode(os.readlink(p))  # git が blob に持つ中身＝指す先の道の字
            elif p.is_file():
                data = p.read_bytes()
            elif p.is_dir():
                continue  # 中の repo（submodule）の印は、その repo の物
            else:
                data = index_blob(root, rel)  # 手元で消した追跡中の file＝次の commit に入る中身を照らす
                if data is None:
                    unread.append(f"{rel}（手元に無く、index にも中身が無い）")
                    continue
        except OSError as e:
            unread.append(f"{rel}（読めない: {e.strerror or e}）")
            continue
        seen: set[tuple[int, str]] = set()
        for text in texts(data):
            for n, line in enumerate(text.splitlines(), 1):
                if MARKER.match(line) and (n, line) not in seen:
                    seen.add((n, line))
                    found.append(f"{rel}:{n}: {line[:40]}")
    return found, unread


def hits(root: Path) -> list[str]:
    return scan(root)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    a = ap.parse_args(argv)
    try:
        found, unread = scan(Path(a.root))
    except OSError as e:
        print(f"衝突の印: 照らせない（{e}）")
        return 2
    if not found and unread:
        print(f"衝突の印: 照らしていない（読めない file {len(unread)} 個・読めた所の印 0）")
        for u in unread:
            print(f"  ? {u}")
        if os.environ.get("AF_CHECK_UNCHECKED"):   # 検査の入口 check_all へ訳を渡す（訳の無い 3 は赤）
            Path(os.environ["AF_CHECK_UNCHECKED"]).write_text(f"照らせない: 読めない file {len(unread)} 個\n",
                                                              encoding="utf-8")
        return 3
    if not found:
        print("衝突の印: 緑（残った印 0）")
        return 0
    print(f"衝突の印: 赤（{len(found)} 行）")
    for f in found:
        print(f"  ✗ {f}")
    for u in unread:
        print(f"  ? 照らしていない: {u}")
    print(ROOT_CAUSE)
    return 1


if __name__ == "__main__":
    sys.exit(main())
