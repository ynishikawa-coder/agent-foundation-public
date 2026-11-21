#!/usr/bin/env python3
"""PR を書いた窓の組（PR の commit の `Claude-Session:` の窓の全部）を `,` で並べて出す。

  python3 plugins/checker/scripts/pr_writer.py --writers --head <PR の先端の SHA> [--base <比べる元の ref>] [--repo <PR の repo>]
  --base を省くと、比べる元は出所（origin）の今の main（出所へ直に聞き、手元に無ければ取って来る）。手元の origin/main は
  fetch から時間が空くと古く、main の commit を書いた窓に数える（レビューの窓を誤って弾く）ので、手で渡さない。

書いた窓の正本は commit の `Claude-Session:`（窓が commit の度に自動で付ける行）だけ。PR 本文に書いた窓を手で写す欄は
置かない（前の形は本文の頭の `書いた窓:` を写しとして持ち、直しの往復で別の窓が commit すると写しがずれて CI が赤になった）。
書いた窓の組: PR の commit（比べる元に無い commit 全部。merge の向こうの commit も含む）の `Claude-Session:` の窓の全部。
途中の commit を別の窓が書いても書いた側に入る（先端の 1 窓だけを書いた窓と見ない）。判定の形の道具 verdict_form.py の
`--writer` に渡す材料。guard の pr_text も同じ記録（GitHub の PR の commit）から組を作り、本文を読まない。
exit: 0=出した / 2=出せない（比べる元を聞けない・commit に記録が無い）。
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


def live_main(root: Path) -> str:
    """出所（origin）の今の main の commit。出所へ直に聞き、その commit が手元に無ければ取って来る（手元の origin/main は
    動かさない）。聞けない・取れない時は OSError（古い手元の main で書いた窓を数えない）。"""
    out = git(root, "ls-remote", "origin", "refs/heads/main").split()
    tip = out[0] if out else ""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tip):
        raise OSError("出所（origin）の main を聞けない（出所に出られる所で回す）")
    has = lambda: subprocess.run(["git", "cat-file", "-e", f"{tip}^{{commit}}"], cwd=root,  # noqa: E731
                                 capture_output=True).returncode == 0
    if not has():
        subprocess.run(["git", "fetch", "--quiet", "--no-tags", "origin", "+refs/heads/main:refs/af/fresh/main"], cwd=root,
                       capture_output=True)
    if not has():
        raise OSError(f"出所の main の先端 {tip[:12]} を手元へ取って来られない")
    return tip


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
    ap.add_argument("--writers", action="store_true", required=True, help="書いた窓の組を `,` で並べて出す")
    ap.add_argument("--head", required=True)
    ap.add_argument("--base", default="", help="比べる元（省くと出所の今の main）")
    ap.add_argument("--repo", type=Path, default=Path.cwd())   # 照らす PR の repo（使う側の repo でも回せるよう plugin の中に置く）
    a = ap.parse_args(argv)
    try:
        ws = writer_sessions(a.repo, a.head, a.base or live_main(a.repo))
    except OSError as e:
        print(f"pr_writer: 出せない — {e}")
        return 2
    if not ws:
        print("pr_writer: PR の commit に `Claude-Session:` の行が無く、書いた窓が決まらない", file=sys.stderr)
        return 2
    print(",".join(ws))
    return 0


if __name__ == "__main__":
    sys.exit(main())
