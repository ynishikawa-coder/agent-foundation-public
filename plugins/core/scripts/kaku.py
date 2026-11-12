#!/usr/bin/env python3
"""核を窓の起動時に差し込む口と、常に読まれる量の上限を照らす口（plugin core の道具はこの 1 本）。

使い方:
  python3 kaku.py inject              SessionStart の hook が呼ぶ。核（同じ plugin の 核.md）を窓の文脈へ差し込み、
                                      細目（細目.md）の在り処を知らせる。開いた repo の根の CLAUDE.md に
                                      写しの枠（AF-CORE:BEGIN）がまだ在る時は、核が二重に入らないよう何もしない。
  python3 kaku.py check [--claude P]  核が上限の内かを照らす。--claude を渡すと、その CLAUDE.md（写しの枠が在れば
                                      枠の外だけ）が各社固有の上限の内かも照らす。
exit: inject は何が起きても 0（窓の起動を止めない）。check は 0=緑 / 1=上限を越えた / 2=読めない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
KAKU = PLUGIN / "核.md"
SAIMOKU = PLUGIN / "細目.md"
FRAME_BEGIN = "<!-- AF-CORE:BEGIN"
FRAME_END = "<!-- AF-CORE:END -->"
# 常に読まれる量の上限（バイト・UTF-8）。数はここの 1 か所だけに置く。
LIMITS = {"核": 4800, "各社固有": 3000}


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def has_frame(claude_md: Path) -> bool:
    try:
        return FRAME_BEGIN in claude_md.read_text(encoding="utf-8")
    except OSError:
        return False


def outside_frame(text: str) -> str:
    """写しの枠が在れば枠の外だけを返す（移る間の repo の各社固有を測るため）。"""
    if FRAME_BEGIN not in text or FRAME_END not in text:
        return text
    head, rest = text.split(FRAME_BEGIN, 1)
    return head + rest.split(FRAME_END, 1)[1]


def inject_text() -> str:
    kaku = KAKU.read_text(encoding="utf-8").rstrip("\n")
    return (kaku + "\n\n"
            + f"（この核は土台の plugin core が起動時に差し込んだ。細目は {SAIMOKU} の同じ番号の節。形に迷った時に Read する）\n")


def inject() -> int:
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if has_frame(project / "CLAUDE.md"):
        return 0  # 写しの枠が在る repo は CLAUDE.md が核を持つ＝差し込まない（二重を避ける）
    try:
        text = inject_text()
    except OSError as e:
        print(f"plugin core: 核.md が読めない（{e}）＝核は差し込まれていない", file=sys.stderr)
        return 0
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def check(claude: Path | None) -> int:
    bad = []
    try:
        n = size(KAKU.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"✗ 核.md が読めない: {e}")
        return 2
    if n > LIMITS["核"]:
        bad.append(f"核（{KAKU.name}）が上限を越えた: {n} > {LIMITS['核']} バイト（細目へ移す）")
    if claude is not None:
        try:
            m = size(outside_frame(claude.read_text(encoding="utf-8")))
        except OSError as e:
            print(f"✗ {claude} が読めない: {e}")
            return 2
        if m > LIMITS["各社固有"]:
            bad.append(f"各社固有（{claude}）が上限を越えた: {m} > {LIMITS['各社固有']} バイト（その repo の文書へ移す）")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        return 1
    print("✅ 量の上限 緑")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="核の差し込みと量の上限の照らし")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inject", help="SessionStart の hook から呼ぶ")
    c = sub.add_parser("check", help="量の上限を照らす")
    c.add_argument("--claude", type=Path, help="照らす repo の根の CLAUDE.md")
    a = ap.parse_args(argv)
    if a.cmd == "inject":
        return inject()
    return check(a.claude)


if __name__ == "__main__":
    sys.exit(main())
