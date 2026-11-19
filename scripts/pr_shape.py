#!/usr/bin/env python3
"""PR の差分の形を照らす（並ぶ PR が同じ所へ足して互いに衝突する形を、入れる前に止める）。

  python3 scripts/pr_shape.py --branch <枝の名> --base <比べる元の ref>
  python3 scripts/pr_shape.py --print-main   出所の今の main の commit を出す（比べる元の正本。checks の入口が読む）
  python3 scripts/pr_shape.py --print-head   PR の先端の commit を出す（CI の PR は event の head.sha。PR の外・分からない時は exit 3）

比べる元の main は出所の今の main（fresh_main）。手元の origin/main は fetch しなければ古く、main で足された物を枝の物と
見て赤に倒れる。出所へ先端を聞き、その commit が手元に無ければ取って来て（手元の origin/main は動かさず、土台の専用の
ref refs/af/fresh/<枝> へ）、揃わない・聞けない時は比べずに「照らせない」で止める。
PR の先端（pr_head）は、CI の PR では HEAD（main と合わせた merge の commit）でなく event の head.sha。

見る事（どれも PR の枝の差分 <base>...HEAD で見る）:
  1. 変更の記録の断片: 足した CHANGELOG.d/ の file は、枝 claude/<日付>-<話題> から決まる <日付>-<話題>.txt の 1 つだけ。
     枝の名は GitHub の上で 1 つに決まる＝この名なら 2 本の PR が同じ名の断片を作れない（名の決まりを守るかに頼らない）。
  2. 試験の file の末尾への追記: 元から在る tests/**/test_*.py の試験（def test_）を増やさない。
     新しい試験は、守る約束の名の新しい file（tests/test_<約束>.py）に置く。並ぶ PR が同じ file の末尾へ足すと、
     1 本入るたびに残りが全部衝突するので、足す所を PR ごとに別の file にする（直す・消すのはよい）。
止めるのは AI の窓の枝（claude/ で始まる枝）だけ。claude/ で始まるのに claude/<8 桁の日付>-<話題> の形でない枝は
照らせない＝赤。claude/ で始まらない枝（人が GitHub の画面で直した patch-1 など）は止めず、照らさなかった事を 1 行知らせる
（新しく人の操作を止める物はオーナーの同意が要る＝核 §3）。main（PR でない push）・枝の名が分からない時（手元の
detached HEAD）も照らさず、照らしていない事をそのまま出す（緑と言わない）。
exit: 0=緑 / 1=赤 / 2=照らせない（比べる元が無い等）/ 3=照らしていない（緑に数えない・check_all が名指す）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = re.compile(r"^claude/(\d{8}-[0-9A-Za-z][0-9A-Za-z._-]*)$")
TEST_DEF = re.compile(r"^(?:async\s+)?def\s+test_", re.M)
ROOT_CAUSE = "直し: 足す所を動かして通すだけで済ませず、同じ所へ足す形になった原因を細目 §3「まず構造を疑う」で探して直す"


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def pr_head(env=None) -> str | None:
    """PR の先端の commit（CI の PR では event の head.sha＝PR_HEAD_SHA か GITHUB_EVENT_PATH の pull_request.head.sha）。
    HEAD は使わない（CI の PR の HEAD は main と合わせた merge の commit で、PR の先端でない）。PR の外・分からなければ None。"""
    import json
    import os
    env = os.environ if env is None else env
    sha = (env.get("PR_HEAD_SHA") or "").strip()
    if not sha and env.get("GITHUB_EVENT_PATH"):
        try:
            event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            sha = str(((event.get("pull_request") or {}).get("head") or {}).get("sha") or "")
        except (OSError, ValueError, AttributeError):
            sha = ""
    return sha if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) else None


def fresh_main(root: Path, ref: str = "main") -> str:
    """出所（origin）の今の枝 ref（既定 main）の commit。出所へ直に聞き、その commit が手元に無ければ取って来る
    （手元の origin/<枝> は書き換えない＝人が置いた ref を黙って動かさない。取って来る先は refs/af/fresh/<枝>）。
    聞けない・取れない時は OSError（古いかもしれない手元の origin/main で黙って比べない）。"""
    env = dict(__import__("os").environ, GIT_TERMINAL_PROMPT="0")

    def run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "時間切れ")

    r = run("ls-remote", "origin", f"refs/heads/{ref}", timeout=30)
    tip = r.stdout.split()[0] if r.returncode == 0 and r.stdout.split() else ""
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tip):
        raise OSError(f"出所（origin）の {ref} を聞けない（{r.stderr.strip() or '先端が無い'}）。手元の origin/{ref} が出所と同じか"
                      "分からないので比べない（出所に出られる所で回す）")
    have = lambda: run("cat-file", "-e", f"{tip}^{{commit}}").returncode == 0  # noqa: E731
    if not have():
        run("fetch", "--quiet", "--no-tags", "origin", f"+refs/heads/{ref}:refs/af/fresh/{ref}", timeout=120)
    if not have():
        raise OSError(f"出所の {ref} の先端 {tip[:12]} を手元へ取って来られない"
                      "（古い main と比べると main で足された物を枝の物と見る）")
    return tip


def show(root: Path, ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def check(root: Path, branch: str, base: str) -> list[str]:
    errs: list[str] = []
    m = BRANCH.match(branch)
    if not m:
        return [f"枝の名 {branch} が claude/<YYYYMMDD>-<話題> でない（変更の記録の断片の名が枝から決まらない）"]
    mb = git(root, "merge-base", base, "HEAD").strip()
    # main を取り込む merge の途中（commit 前）は、取り込む側との分かれ目の方が新しい＝そちらと比べる
    if subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=root, capture_output=True).returncode == 0:
        mm = git(root, "merge-base", base, "MERGE_HEAD").strip()
        if subprocess.run(["git", "merge-base", "--is-ancestor", mb, mm], cwd=root).returncode == 0:
            mb = mm
    # 作業の木と比べる（手元では commit 前の物・まだ git に載せていない新しい file も照らす。CI では HEAD と同じ）
    rows = [ln.split("\t") for ln in git(root, "diff", "--name-status", "--no-renames", mb).splitlines() if ln]
    rows += [["A", ln] for ln in git(root, "ls-files", "--others", "--exclude-standard").splitlines() if ln]
    want = f"CHANGELOG.d/{m.group(1)}.txt"
    for st, *paths in rows:
        path = paths[-1]
        if st == "A" and path.startswith("CHANGELOG.d/") and path != want:
            errs.append(f"{path}: 足す断片の名は枝から決まる {want} だけ（同じ名を 2 本の PR が作って衝突しない形）")
        if st == "M" and re.match(r"^tests/(?:.*/)?test_[^/]*\.py$", path):
            before = show(root, mb, path)
            after = (root / path).read_text(encoding="utf-8") if (root / path).is_file() else ""
            if before is not None and len(TEST_DEF.findall(after)) > len(TEST_DEF.findall(before)):
                n = len(TEST_DEF.findall(after)) - len(TEST_DEF.findall(before))
                errs.append(f"{path}: 元から在る試験の file に試験を {n} 本足した。新しい試験は守る約束の名の新しい file"
                            "（tests/test_<約束>.py）に置く（並ぶ PR が同じ file の末尾へ足して衝突しない形）")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--branch")
    ap.add_argument("--base")
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--print-main", action="store_true", help="出所の今の main の commit を出す（checks の入口が比べる元に使う）")
    ap.add_argument("--print-head", action="store_true", help="PR の先端の commit を出す（PR の外・分からなければ exit 3）")
    a = ap.parse_args(argv)
    if a.print_head:
        head = pr_head()
        if not head:
            print("✗ PR の先端が分からない（PR_HEAD_SHA も event の pull_request.head.sha も無い）", file=sys.stderr)
            return 3
        print(head)
        return 0
    if a.print_main:
        try:
            print(fresh_main(a.repo))
        except OSError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 2
        return 0
    if a.branch is None or a.base is None:
        ap.error("--branch と --base が要る")
    if a.branch == "main":
        print("pr_shape: 照らしていない（main への push＝PR の差分が無い）")
        return 3
    if a.branch in ("HEAD", ""):
        print("pr_shape: 照らしていない（枝の名が分からない＝detached HEAD。GITHUB_HEAD_REF に枝の名を渡すと照らす）")
        return 3
    if not a.branch.startswith("claude/"):
        print(f"pr_shape: 照らしていない（{a.branch} は AI の窓の枝 claude/… でない＝人の PR は止めない）")
        return 3
    try:
        errs = check(a.repo, a.branch, a.base)
    except OSError as e:
        print(f"pr_shape: 照らせない — {e}")
        return 2
    for e in errs:
        print(f"✗ {e}")
    if errs:
        print(f"pr_shape: 赤 ({len(errs)} 件)")
        print(ROOT_CAUSE)
        return 1
    print("pr_shape: 緑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
