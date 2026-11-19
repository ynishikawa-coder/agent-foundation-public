#!/usr/bin/env python3
"""PR の差分の形を照らす（並ぶ PR が同じ所へ足して互いに衝突する形を、入れる前に止める）。

  python3 scripts/pr_shape.py --branch <枝の名> --base <比べる元の ref> [--event <PR の出来事の JSON>] [--ai]

見る事（どれも PR の枝の差分 <base>...HEAD で見る）:
  1. 変更の記録の断片: 足した CHANGELOG.d/ の file は、枝 claude/<日付>-<話題> から決まる <日付>-<話題>.txt の 1 つだけ。
     枝の名は GitHub の上で 1 つに決まる＝この名なら 2 本の PR が同じ名の断片を作れない（名の決まりを守るかに頼らない）。
  2. 試験の file の末尾への追記: 元から在る試験の file の試験を増やさない。試験の file は置き場の形でなく、pytest が集める
     物の決まり（repo の pytest の設定の python_files・無ければ pytest の既定 test_*.py と *_test.py。どの dir でも）で読む。
     新しい試験は、守る約束の名の新しい file（tests/test_<約束>.py）に置く。並ぶ PR が同じ file の末尾へ足すと、
     1 本入るたびに残りが全部衝突するので、足す所を PR ごとに別の file にする（直す・消すのはよい）。
止めるのは AI の窓の PR だけ。AI の窓かは枝の名の頭でなく PR の実物で読む: PR の出来事（--event＝CI の GITHUB_EVENT_PATH）の
本文の頭の欄の塊に `書いた窓:` の欄が在る（CONTRIBUTING §1 の PR の型＝AI の窓が書く）か、枝が claude/ で始まる。
出来事の無い手元では、AI の窓が回す時（--ai＝check の入口が窓の環境 CLAUDECODE を見て渡す）か枝が claude/ で始まる時。
AI の窓の PR で枝が claude/<8 桁の日付>-<話題> の形でない（fix/… など）物は照らせない＝赤。人の PR（人が GitHub の画面で
直した patch-1 など）は止めず、照らさなかった事を 1 行知らせる（新しく人の操作を止める物はオーナーの同意が要る＝核 §3）。
main（PR でない push）・枝の名が分からない時（手元の detached HEAD）も照らさず、照らしていない事をそのまま出す（緑と言わない）。
exit: 0=緑 / 1=赤 / 2=照らせない（比べる元が無い等）。
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = re.compile(r"^claude/(\d{8}-[0-9A-Za-z][0-9A-Za-z._-]*)$")
TEST_DEF = re.compile(r"^[ \t]*(?:async\s+)?def\s+test", re.M)


def count_tests(src: str) -> int:
    """試験の数を構文木で数える（pytest が集める形＝どの深さの関数・class の中の方法も、名が test で始まる物。
    名を test で始める代入〔test_x = 作る関数(...)〕も足す）。字の並び（行の頭の def test_）で
    数えると、class の中に字下げした試験・代入で作る試験が数えられなかった。構文が読めない file は字下げを含む def を数える。"""
    import ast
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return len(TEST_DEF.findall(src))
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            n += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            n += sum(1 for t in targets if isinstance(t, ast.Name) and t.id.startswith("test"))
    return n


# 試験の file の決まりの正本は plugin guard の paid_upstream.test_rules（pytest の設定の python_files を 1 か所で読む・写さない）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"))
import paid_upstream as _PU  # noqa: E402


def pytest_file_patterns(root: Path) -> tuple[str, ...]:
    """pytest が試験の file として集める名の形（python_files）。"""
    return tuple(_PU.test_rules(str(root))[1])


def is_test_file(path: str, patterns) -> bool:
    """pytest が集める名か（置き場の dir は問わない）。"""
    base = path.rsplit("/", 1)[-1]
    return base.endswith(".py") and any(fnmatch.fnmatch(base, p) for p in patterns)


WRITER_FIELD = re.compile(r"^\s*書いた窓\s*[:：]\s*\S")


def ai_pr(event: dict | None, branch: str, ai_env: bool) -> bool:
    """AI の窓の PR か。PR の実物（出来事の本文の頭の欄の塊の `書いた窓:`）・枝の頭・手元の AI の窓の印のどれかで読む。"""
    if branch.startswith("claude/"):
        return True
    pr = (event or {}).get("pull_request") if isinstance(event, dict) else None
    if isinstance(pr, dict):
        lines = str(pr.get("body") or "").replace("\r\n", "\n").split("\n")
        head = lines[:next((i for i, ln in enumerate(lines) if not ln.strip()), len(lines))]
        return any(WRITER_FIELD.match(ln) for ln in head)
    return ai_env


ROOT_CAUSE = "直し: 足す所を動かして通すだけで済ませず、同じ所へ足す形になった原因を細目 §3「まず構造を疑う」で探して直す"


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def show(root: Path, ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=root, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def check(root: Path, branch: str, base: str) -> list[str]:
    errs: list[str] = []
    m = BRANCH.match(branch)
    if not m:
        return [f"枝の名 {branch} が claude/<YYYYMMDD>-<話題> でない（AI の窓の PR は、変更の記録の断片の名が枝から決まる形で出す）"]
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
    patterns = pytest_file_patterns(root)
    for st, *paths in rows:
        path = paths[-1]
        if st == "A" and path.startswith("CHANGELOG.d/") and path != want:
            errs.append(f"{path}: 足す断片の名は枝から決まる {want} だけ（同じ名を 2 本の PR が作って衝突しない形）")
        if st == "M" and is_test_file(path, patterns):
            before = show(root, mb, path)
            after = (root / path).read_text(encoding="utf-8") if (root / path).is_file() else ""
            if before is not None and count_tests(after) > count_tests(before):
                n = count_tests(after) - count_tests(before)
                errs.append(f"{path}: 元から在る試験の file に試験を {n} 本足した。新しい試験は守る約束の名の新しい file"
                            "（tests/test_<約束>.py）に置く（並ぶ PR が同じ file の末尾へ足して衝突しない形）")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--branch", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--repo", type=Path, default=ROOT)
    ap.add_argument("--event", default="", help="PR の出来事の JSON（CI の GITHUB_EVENT_PATH）。本文の書いた窓で AI の PR かを読む")
    ap.add_argument("--ai", action="store_true", help="手元で AI の窓が回す（出来事が無い時の AI の窓の印）")
    a = ap.parse_args(argv)
    event = None
    if a.event:
        try:
            event = json.loads(Path(a.event).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"pr_shape: 照らせない — PR の出来事 {a.event} が読めない（AI の PR かを決められない）: {e}")
            return 2
    if a.branch == "main":
        print("pr_shape: 照らしていない（main への push＝PR の差分が無い）")
        return 0
    if a.branch in ("HEAD", ""):
        print("pr_shape: 照らしていない（枝の名が分からない＝detached HEAD。GITHUB_HEAD_REF に枝の名を渡すと照らす）")
        return 0
    if not ai_pr(event, a.branch, a.ai):
        print(f"pr_shape: 照らしていない（{a.branch} は人の PR＝本文に書いた窓の欄が無く枝も claude/… でない・人の PR は止めない）")
        return 0
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
