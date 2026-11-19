#!/usr/bin/env python3
"""PR の書いた窓を、PR の commit の `Claude-Session:` の行（記録）だけから決める。

  python3 plugins/checker/scripts/pr_writer.py --branch <枝の名> --head <PR の先端の SHA> --base <比べる元の ref>
  python3 plugins/checker/scripts/pr_writer.py --writers --head <PR の先端の SHA> --base <比べる元の ref>

なぜ: 別の目の照らし（checker の判定の形・guard の pr_text）は書いた窓を読む。書いた窓の正本は commit の
`Claude-Session:`（窓が commit の度に付ける行・push の時点で決まる）だけで、PR 本文に手で書く写しは置かない。
前の形は本文の頭の `書いた窓:` を先端の commit の窓と照らした。本文は push の後でしか直せないので、別の窓が main を
取り込んで push する度に先端の窓が変わり、その push の CI が毎回 1 回赤になった（写しが正本を追いかける形の崩れ）。

書いた窓の組: PR の commit（比べる元に無い commit 全部。merge の向こうの commit も・取り込みの merge commit 自身も含む）の
`Claude-Session:` の窓の全部。途中の commit・取り込みの merge を書いた窓も書いた側（merge には衝突の解き方という中身が在る）。
`--writers` で組を `,` で並べて出す（判定の形の道具 verdict_form.py の `--writer` に渡す材料）。
照らし（CI）: AI の窓の枝（claude/ で始まる枝）の PR の commit に `Claude-Session:` が 1 つも無ければ赤（書いた窓が記録から
決まらず、別の目を照らせない）。組を出して緑。人の枝・PR の外は照らさず、照らしていない事をそのまま出す（緑と言わない）。
exit: 0=緑 / 1=赤 / 2=照らせない / 3=照らしていない（緑に数えない・check_all が名指す）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SESSION = re.compile(r"^Claude-Session:\s*\S*?(session_[A-Za-z0-9]+)\s*$", re.M)


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def writer_sessions(root: Path, head: str, base: str) -> list[str]:
    """PR の commit（base に無い commit 全部）の `Claude-Session:` の窓の組（出た順・重ねない）。"""
    out: list[str] = []
    for sha in git(root, "rev-list", head, "--not", base).split():
        for sid in SESSION.findall(git(root, "log", "-1", "--format=%B", sha)):
            if sid not in out:
                out.append(sid)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--writers", action="store_true", help="書いた窓の組を `,` で並べて出すだけ（照らさない）")
    ap.add_argument("--branch", default="")
    ap.add_argument("--head", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--repo", type=Path, default=Path.cwd())   # 照らす PR の repo（使う側の repo でも回せるよう plugin の中に置く）
    a = ap.parse_args(argv)
    if a.writers:
        try:
            ws = writer_sessions(a.repo, a.head, a.base)
        except OSError as e:
            print(f"pr_writer: 照らせない — {e}")
            return 2
        if not ws:
            print("pr_writer: PR の commit に `Claude-Session:` の行が無く、書いた窓が決まらない", file=sys.stderr)
            return 2
        print(",".join(ws))
        return 0
    if not a.branch.startswith("claude/"):
        print(f"pr_writer: 照らしていない（{a.branch or '枝の名なし'} は AI の窓の枝 claude/… でない）")
        return 3
    try:
        ws = writer_sessions(a.repo, a.head, a.base)
    except OSError as e:
        print(f"pr_writer: 照らせない — {e}")
        return 2
    if not ws:
        print(f"✗ PR の commit（{a.base} に無い commit・先端 {a.head[:12]}）に `Claude-Session:` の行が無く、書いた窓が記録から決まらない"
              "（別の目を照らせない）。commit の説明の末尾に窓の `Claude-Session:` の行を付けて commit し直す")
        print("pr_writer: 赤")
        print("直し: 行を付け直すだけで済ませず、記録の無い commit ができた原因を細目 §3「まず構造を疑う」で探して直す")
        return 1
    print(f"pr_writer: 緑（書いた窓の組: {','.join(ws)}）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
