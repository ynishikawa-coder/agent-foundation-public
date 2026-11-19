#!/usr/bin/env python3
"""PR 本文の頭の `書いた窓:` が、PR の枝の先端の commit を書いた窓（commit の `Claude-Session:` の行）と同じかを照らす。

  python3 scripts/pr_writer.py --branch <枝の名> --head <PR の先端の SHA> --base <比べる元の ref> --body-file <本文の file>

なぜ: 別の目の照らし（checker の判定の形・guard の pr_text）は本文の `書いた窓:` を書いた窓として読む。直しの往復で
別の窓が commit すると、本文は最初の窓のまま・先端は直した窓になり、直した窓が自分の PR に判定を付けても
「別の目」と通ってしまう。正本は commit の `Claude-Session:`（窓が commit の度に自動で付ける行）で、手で直す本文は写し。
写しが正本と違えば赤にし、直す行（`書いた窓: <先端の窓>`）をそのまま出す。

先端の窓: 先端から first-parent で遡り（main を取り込む merge 等、`Claude-Session:` の無い commit は飛ばす）、
比べる元との分かれ目より後で最初に `Claude-Session:` を持つ commit の窓。
書いた窓の組: PR の commit（比べる元に無い commit 全部。merge の向こうの commit も含む）の `Claude-Session:` の窓の全部。
途中の commit を別の窓が書いても書いた側に入る（先端の 1 窓だけを書いた窓と見ない）。`--writers` で組を `,` で並べて出す
（判定の形の道具 verdict_form.py の `--writer` に渡す材料）。
照らすのは AI の窓の枝（claude/ で始まる枝）だけ。人の枝・main への push・本文が無い（手元）時は照らさず、
照らしていない事をそのまま出す（緑と言わない）。
exit: 0=緑（または照らしていない）/ 1=赤 / 2=照らせない。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "window-shape"))
import window_shape as W  # noqa: E402  窓の id と commit の書き手の行の形の正本（写さない）

WRITER = re.compile(r"^\s*書いた窓\s*[:：]\s*(\S+)", re.M)
SESSION = W.COMMIT_SESSION
ID = re.compile(r"^%s$" % W.SESSION_ID_PAT)


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


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
        return [f"PR 本文の頭に `書いた窓:` が無い。頭に `書いた窓: {tip}` を書く（先端の commit {sha[:12]} の窓）"]
    if not ID.match(m.group(1)):
        return [f"PR 本文の `書いた窓: {m.group(1)}` が窓の id の形でない。`書いた窓: {tip}` に直す（先端の commit {sha[:12]} の窓）"]
    if m.group(1) != tip:
        return [f"PR 本文の `書いた窓: {m.group(1)}` が、先端の commit {sha[:12]} を書いた窓 {tip} と違う"
                f"（直しの往復で別の窓が commit した）。本文の頭を `書いた窓: {tip}` に直す"]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--writers", action="store_true", help="書いた窓の組を `,` で並べて出すだけ（照らさない）")
    ap.add_argument("--branch", default="")
    ap.add_argument("--head", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--body-file", type=Path)
    ap.add_argument("--repo", type=Path, default=ROOT)
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
        return 0
    if a.body_file is None:
        print("pr_writer: 照らしていない（PR 本文が無い＝PR の外。CI の PR では本文を渡して照らす）")
        return 0
    try:
        errs = check(a.repo, a.head, a.base, a.body_file.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"pr_writer: 照らせない — {e}")
        return 2
    for e in errs:
        print(f"✗ {e}")
    if errs:
        print("pr_writer: 赤")
        print("直し: 本文の頭を直すだけで済ませず、写しが正本からずれた原因を細目 §3「まず構造を疑う」で探して直す")
        return 1
    print("pr_writer: 緑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
