#!/usr/bin/env python3
"""核を窓の起動時に差し込む口と、常に読まれる量の上限を照らす口（plugin core の道具はこの 1 本）。

使い方:
  python3 kaku.py inject              SessionStart の hook が呼ぶ。核（同じ plugin の 核.md）と振る舞いの既定
                                      （振る舞い.md）を窓の文脈へ毎回差し込み、形の細目（細目.md）の在り処を知らせる。開いた repo の根の CLAUDE.md に
                                      写しの枠（AF-CORE:BEGIN）がまだ在る時は、核が二重に入らないよう何もしない。
  python3 kaku.py check [--claude P]  核と振る舞いの既定が在り、上限の内かを照らす。--claude を渡すと、その CLAUDE.md（写しの枠が在れば
                                      枠の外だけ）が各社固有の上限の内かも照らす。
  python3 kaku.py grow --base REF     毎回差し込む物（核・振る舞いの既定）が git の REF の時より増えていないかを照らす。
                                      足すなら同じ変更で同じだけ畳む（上限の内で足し続けて満杯にしない）。
exit: inject は何が起きても 0（窓の起動を止めない）。check・grow は 0=緑 / 1=越えた・増えた / 2=読めない。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
KAKU = PLUGIN / "核.md"
FURUMAI = PLUGIN / "振る舞い.md"
SAIMOKU = PLUGIN / "細目.md"
FRAME_BEGIN = "<!-- AF-CORE:BEGIN"
FRAME_END = "<!-- AF-CORE:END -->"
# 越えた時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 文を移して量を合わせるだけで済ませず、決まりが増えた原因を細目 §3「まず構造を疑う」で探して畳む"
# 常に読まれる量の上限（バイト・UTF-8）。数はここの 1 か所だけに置く。
LIMITS = {"核": 4800, "振る舞い": 2400, "各社固有": 3000}


# 読めない時の類（無い・権限・UTF-8 でない中身）を 1 か所で受ける。どの読みもこれで受け、欠けを名指しする。
UNREADABLE = (OSError, UnicodeDecodeError)


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def has_frame(claude_md: Path) -> bool:
    try:
        return FRAME_BEGIN in claude_md.read_text(encoding="utf-8")
    except UNREADABLE:
        return False


def outside_frame(text: str) -> str:
    """写しの枠が在れば枠の外だけを返す（移る間の repo の各社固有を測るため）。"""
    if FRAME_BEGIN not in text or FRAME_END not in text:
        return text
    head, rest = text.split(FRAME_BEGIN, 1)
    return head + rest.split(FRAME_END, 1)[1]


def inject_text() -> str:
    kaku = KAKU.read_text(encoding="utf-8").rstrip("\n")
    try:
        furumai = FURUMAI.read_text(encoding="utf-8").rstrip("\n")
    except UNREADABLE as e:
        # 欠けたまま黙って核だけにしない: 窓の起動は止めず、欠けた事を文脈に名指しで出す
        print(f"plugin core: 振る舞い.md が読めない（{e}）", file=sys.stderr)
        furumai = f"（振る舞いの既定 {FURUMAI} が読めず、差し込まれていない。最初にオーナーへ知らせる）"
    return (kaku + "\n\n" + furumai + "\n\n"
            + "（この核と振る舞いの既定は土台の plugin core が起動時に差し込んだ。"
            + f"返事・問い・手の窓などの形の細目は {SAIMOKU} の同じ番号の節。その形を書く時に Read する）\n")


def inject() -> int:
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if has_frame(project / "CLAUDE.md"):
        return 0  # 写しの枠が在る repo は CLAUDE.md が核を持つ＝差し込まない（二重を避ける）
    try:
        text = inject_text()
    except UNREADABLE as e:
        print(f"plugin core: 核.md が読めない（{e}）＝核は差し込まれていない", file=sys.stderr)
        return 0
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def check(claude: Path | None) -> int:
    bad = []
    try:
        n = size(KAKU.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 核.md が読めない: {e}")
        return 2
    if n > LIMITS["核"]:
        bad.append(f"核（{KAKU.name}）が上限を越えた: {n} > {LIMITS['核']} バイト（細目へ移す）")
    try:
        f = size(FURUMAI.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 振る舞い.md が読めない: {e}")
        return 2
    if f > LIMITS["振る舞い"]:
        bad.append(f"振る舞いの既定（{FURUMAI.name}）が上限を越えた: {f} > {LIMITS['振る舞い']} バイト（癖と逆を求めない物を細目へ移す）")
    if claude is not None:
        try:
            m = size(outside_frame(claude.read_text(encoding="utf-8")))
        except UNREADABLE as e:
            print(f"✗ {claude} が読めない: {e}")
            return 2
        if m > LIMITS["各社固有"]:
            bad.append(f"各社固有（{claude}）が上限を越えた: {m} > {LIMITS['各社固有']} バイト（その repo の文書へ移す）")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(ROOT_CAUSE)
        return 1
    print("✅ 量の上限 緑")
    return 0


# 毎回差し込む物＝増やさない物。足す時は同じ変更で同じだけ畳む（上限の内でも純増は赤）。
ALWAYS = (KAKU, FURUMAI)
GROW_FIX = "直し: 足すなら同じ変更で同じだけ畳む（重複を細目・skill の正本へ寄せる）。量を合わせるだけで済ませず、細目 §3「まず構造を疑う」で増えた原因から畳む"


def base_text(ref: str, path: Path) -> str:
    """git の ref の時の中身。読めない（ref が無い・その時に file が無い）時は OSError で止める。"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path.parent, capture_output=True, text=True)
    if top.returncode != 0:
        raise OSError(f"git の外: {top.stderr.strip()}")
    rel = path.resolve().relative_to(Path(top.stdout.strip()).resolve()).as_posix()
    r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=path.parent, capture_output=True)
    if r.returncode != 0:
        raise OSError(f"{ref}:{rel} が読めない: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout.decode("utf-8")


def grow(ref: str) -> int:
    bad = []
    for path in ALWAYS:
        try:
            now = size(path.read_text(encoding="utf-8"))
            before = size(base_text(ref, path))
        except UNREADABLE as e:
            # 比べる元が無い時に黙って緑にしない（既定で止める）
            print(f"✗ {path.name} の増え方を照らせない: {e}")
            return 2
        if now > before:
            bad.append(f"{path.name} が {ref} より増えた: {before} → {now} バイト（+{now - before}）")
        else:
            print(f"・{path.name}: {before} → {now} バイト")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(GROW_FIX)
        return 1
    print("✅ 毎回差し込む物は増えていない")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="核の差し込みと量の上限の照らし")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inject", help="SessionStart の hook から呼ぶ")
    c = sub.add_parser("check", help="量の上限を照らす")
    c.add_argument("--claude", type=Path, help="照らす repo の根の CLAUDE.md")
    g = sub.add_parser("grow", help="毎回差し込む物が REF より増えていないかを照らす")
    g.add_argument("--base", required=True, help="比べる元の git の ref（例: main との分かれ目）")
    a = ap.parse_args(argv)
    if a.cmd == "inject":
        return inject()
    if a.cmd == "grow":
        return grow(a.base)
    return check(a.claude)


if __name__ == "__main__":
    sys.exit(main())
