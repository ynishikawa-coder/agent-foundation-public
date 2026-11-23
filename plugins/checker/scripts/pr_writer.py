#!/usr/bin/env python3
"""PR の書いた窓を commit の `Claude-Session:` の行（記録）から出す（--writers）。本文の頭に `書いた窓:` の写しが残っていれば、
先端の commit を書いた窓と同じかを照らす。

  python3 plugins/checker/scripts/pr_writer.py --branch <枝の名> --head <PR の先端の SHA> [--base <比べる元の ref>] --body-file <本文の file>
  --base を省くと、比べる元は出所（origin）の今の main（出所へ直に聞き、手元に無ければ取って来る）。手元の origin/main は
  fetch から時間が空くと古く、main の commit を書いた窓に数える（レビューの窓を誤って弾く）ので、手で渡さない。

なぜ: 別の目の照らし（checker の判定の形・guard の pr_text）は本文の `書いた窓:` を書いた窓として読む。直しの往復で
別の窓が commit すると、本文は最初の窓のまま・先端は直した窓になり、直した窓が自分の PR に判定を付けても
「別の目」と通ってしまう。正本は commit の `Claude-Session:`（窓が commit の度に自動で付ける行）で、手で直す本文は写し。
写しが正本と違えば赤にし、直す行（`書いた窓: <先端の窓>`）をそのまま出す。
今の形（2026-11-22）: PR の型は `書いた窓:` を置かない（写しを置かなければ、直しの commit の後に書き直し忘れる誤りが入れない）。
本文に `書いた窓:` が無いのが正しい形＝緑。写しが残る本文（前の型で出した PR）だけを照らす。

先端の窓: 先端から first-parent で遡り（main を取り込む merge 等、`Claude-Session:` の無い commit は飛ばす）、
比べる元との分かれ目より後で最初に `Claude-Session:` を持つ commit の窓。
書いた窓の組: PR の commit（比べる元に無い commit 全部。merge の向こうの commit も含む）の `Claude-Session:` の窓の全部。
途中の commit を別の窓が書いても書いた側に入る（先端の 1 窓だけを書いた窓と見ない）。`--writers` で組を `,` で並べて出す
（判定の形の道具 verdict_form.py の `--writer` に渡す材料）。
照らすのは AI の窓の枝（claude/ で始まる枝）だけ。人の枝・main への push・本文が無い（手元）時は照らさず、
照らしていない事をそのまま出す（緑と言わない）。
exit: 0=緑 / 1=赤 / 2=照らせない / 3=照らしていない（緑に数えない・check_all が名指す）。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

WRITER = re.compile(r"^\s*書いた窓\s*[:：]\s*(\S+)", re.M)
SESSION = re.compile(r"^Claude-Session:\s*\S*?(session_[A-Za-z0-9]+)\s*$", re.M)
ID = re.compile(r"^session_[A-Za-z0-9]+$")


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def default_branch(root: Path) -> str:
    """出所（origin）の既定の枝の ref（例 refs/heads/main）。出所へ直に聞く（名を決め打ちしない＝既定の枝が main でない
    repo でも、その repo が今従う枝で比べる）。聞けない時は OSError。"""
    for ln in git(root, "ls-remote", "--symref", "origin", "HEAD").splitlines():
        part = ln.split()
        if len(part) == 3 and part[0] == "ref:" and part[2] == "HEAD" and part[1].startswith("refs/heads/"):
            return part[1]
    raise OSError("出所（origin）の既定の枝を聞けない（出所に出られる所で回す）")


def live_main(root: Path) -> str:
    """出所（origin）の今の既定の枝の commit。出所へ直に聞き、その commit が手元に無ければ取って来る（手元の origin/main は
    動かさない）。聞けない・取れない時は OSError（古い手元の main で書いた窓を数えない）。"""
    ref = default_branch(root)
    out = git(root, "ls-remote", "origin", ref).split()
    tip = out[0] if out else ""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tip):
        raise OSError(f"出所（origin）の {ref} を聞けない（出所に出られる所で回す）")
    has = lambda: subprocess.run(["git", "cat-file", "-e", f"{tip}^{{commit}}"], cwd=root,  # noqa: E731
                                 capture_output=True).returncode == 0
    if not has():
        subprocess.run(["git", "fetch", "--quiet", "--no-tags", "origin", f"+{ref}:refs/af/fresh/default"], cwd=root,
                       capture_output=True)
    if not has():
        raise OSError(f"出所の {ref} の先端 {tip[:12]} を手元へ取って来られない")
    return tip


def tip_session(root: Path, head: str, base: str) -> tuple[str, str]:
    """(先端の窓の session id, その commit の SHA)。無ければ ("", "")。"""
    mb = git(root, "merge-base", base, head).strip()
    for sha in git(root, "rev-list", "--first-parent", f"{mb}..{head}").split():
        found = SESSION.findall(git(root, "log", "-1", "--format=%B", sha))
        if found:
            return found[-1], sha
    return "", ""


def writer_sessions(root: Path, head: str, base: str) -> list[str]:
    """PR の commit（base に無い commit 全部）の `Claude-Session:` の窓の組（出た順・重ねない）。"""
    out: list[str] = []
    for sha in git(root, "rev-list", head, "--not", base).split():
        for sid in SESSION.findall(git(root, "log", "-1", "--format=%B", sha)):
            if sid not in out:
                out.append(sid)
    return out


def check(root: Path, head: str, base: str, body: str) -> list[str]:
    tip, sha = tip_session(root, head, base)
    if not tip:
        return [f"PR の commit（{base} との分かれ目から {head[:12]} まで）に `Claude-Session:` の行が無く、書いた窓が決まらない"]
    m = WRITER.search(body)
    if not m:
        return []   # 写しを置かない今の型＝書いた窓は記録（commit の Claude-Session:）だけ
    if not ID.match(m.group(1)):
        return [f"PR 本文の `書いた窓: {m.group(1)}` が窓の id の形でない。`書いた窓: {tip}` に直す（先端の commit {sha[:12]} の窓）"]
    if m.group(1) != tip:
        return [f"PR 本文の `書いた窓: {m.group(1)}` が、先端の commit {sha[:12]} を書いた窓 {tip} と違う"
                f"（直しの往復で別の窓が commit した）。本文の頭を `書いた窓: {tip}` に直す"]
    return []


def unchecked(kind: str, why: str) -> int:
    """照らしていない訳を出し、検査の入口（check_all の AF_CHECK_UNCHECKED）へ同じ訳を渡して 3 を返す。
    kind は「対象外」（その場に照らす物が無い）か「照らせない」（照らす物は在るのに値が無い。CI では赤）。"""
    print(f"pr_writer: 照らしていない（{kind}: {why}）")
    if os.environ.get("AF_CHECK_UNCHECKED"):
        Path(os.environ["AF_CHECK_UNCHECKED"]).write_text(f"{kind}: {why}\n", encoding="utf-8")
    return 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--writers", action="store_true", help="書いた窓の組を `,` で並べて出すだけ（照らさない）")
    ap.add_argument("--branch", default="")
    ap.add_argument("--head", required=True)
    ap.add_argument("--base", default="", help="比べる元（省くと出所の今の main）")
    ap.add_argument("--body-file", type=Path)
    ap.add_argument("--repo", type=Path, default=Path.cwd())   # 照らす PR の repo（使う側の repo でも回せるよう plugin の中に置く）
    a = ap.parse_args(argv)
    if not a.base:
        try:
            a.base = live_main(a.repo)
        except OSError as e:
            print(f"pr_writer: 照らせない — {e}")
            return 2
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
        return unchecked("対象外", f"{a.branch or '枝の名なし'} は AI の窓の枝 claude/… でない＝人の PR は書いた窓を持たない")
    if a.body_file is None:
        return unchecked("照らせない", "PR 本文が無い（--body-file で本文を渡して照らす）")
    try:
        errs = check(a.repo, a.head, a.base, a.body_file.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"pr_writer: 照らせない — {e}")
        return 2
    for e in errs:
        print(f"✗ {e}")
    if errs:
        print("pr_writer: 赤")
        print("直し: 本文の頭を直すだけで済ませず、意図（書いた窓の名乗りが commit の記録と 1 つに合う）とのずれから入り、写しが正本からずれた原因を細目 §3「まず構造を疑う」で探して直す")
        return 1
    print("pr_writer: 緑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
