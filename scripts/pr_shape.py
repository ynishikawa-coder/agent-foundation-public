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
  2. 試験の file の末尾への追記: 元から在る tests/**/test_*.py の試験を増やさない（書き換え・型の変化・名の変更の全部で、
     class の中の試験も ast で数える。在る parametrize の行を足すのはよく、parametrize の軸を足すのは試験を増やす物と見る）。
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
import ast
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = re.compile(r"^claude/(\d{8}-[0-9A-Za-z][0-9A-Za-z._-]*)$")
ROOT_CAUSE = "直し: 足す所を動かして通すだけで済ませず、意図（並ぶ PR が互いに衝突しない）とのずれから入り、同じ所へ足す形になった原因を細目 §3「まず構造を疑う」で探して直す"


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
    errs += grown_test_files(root, mb, rows)
    return errs


# ── 元から在る試験の file の試験を増やしていないか ──
# 照らす変更: 書き換え（M）・型の変化（T＝file と symlink の入れ替え）・名の変更（git が見つける R と、見つけない
# D+A＝消した試験の file と同じ名の試験を持つ足した file）。試験は ast で数える（字下げした class の中の試験・
# test_ の名に代入した物も）。parametrize は、在る軸の行（argvalues）を足すのは許し、軸（decorator）を足すのを照らす。
TEST_PATH = re.compile(r"^tests/(?:.*/)?test_[^/]*\.py$")
GROW = "新しい試験は守る約束の名の新しい file（tests/test_<約束>.py）に置く（並ぶ PR が同じ file の末尾へ足して衝突しない形）"


def _is_parametrize(dec: ast.expr) -> bool:
    f = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(f, ast.Attribute) and f.attr == "parametrize"


def tests_shape(src: str) -> dict[str, int]:
    """試験の file の {試験の名（class の中は Class.名）: parametrize の軸の数}。名が重なれば後の物（pytest と同じ）。
    構文が読めなければ ValueError。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError(f"構文が読めない（{e.msg}・{e.lineno} 行）") from None
    out: dict[str, int] = {}

    def walk(body, prefix: str, axes: int) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                walk(node.body, f"{prefix}{node.name}.", axes + sum(map(_is_parametrize, node.decorator_list)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                out[prefix + node.name] = axes + sum(map(_is_parametrize, node.decorator_list))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(t, ast.Name) and t.id.startswith("test"):
                        out[prefix + t.id] = axes

    walk(tree.body, "", 0)
    return out


def _blob(root: Path, ref: str, path: str, hops: int = 8) -> str | None:
    """ref の path の中身（symlink は指す先を ref の木の中で辿った中身）。無ければ None。"""
    for _ in range(hops):
        r = subprocess.run(["git", "ls-tree", ref, "--", path], cwd=root, capture_output=True, text=True)
        meta = r.stdout.split("\t", 1)[0].split() if r.returncode == 0 else []
        if not meta:
            return None
        body = show(root, ref, path)
        if meta[0] != "120000" or body is None:
            return body
        path = posixpath.normpath(posixpath.join(posixpath.dirname(path), body.strip()))
    return None


def _now(root: Path, path: str) -> str:
    p = root / path
    return p.read_text(encoding="utf-8") if p.is_file() else ""  # symlink は指す先の中身


def grown_test_files(root: Path, mb: str, rows_nr: list[list[str]]) -> list[str]:
    """元から在る試験の file（名を変えた物・型を変えた物を含む）に試験・parametrize の軸を足した所の名指し。"""
    errs: list[str] = []
    pairs: list[tuple[list[str], str]] = []  # ([分かれ目の側の path], 今の path)
    renamed = [ln.split("\t") for ln in git(root, "diff", "--name-status", "-M", mb).splitlines() if ln]
    moved_from, moved_to = set(), set()
    for st, *paths in renamed:
        if st.startswith("R") and len(paths) == 2 and (TEST_PATH.match(paths[0]) or TEST_PATH.match(paths[1])):
            pairs.append(([paths[0]], paths[1]))
            moved_from.add(paths[0])
            moved_to.add(paths[1])
    for st, *paths in rows_nr:
        path = paths[-1]
        if st in ("M", "T") and TEST_PATH.match(path):
            pairs.append(([path], path))
    # git が名の変更と見なかった D+A: 足した試験の file が、消した試験の file と同じ名の試験を持てば、そこから移した物
    gone = {p[-1]: None for st, *p in rows_nr if st == "D" and TEST_PATH.match(p[-1]) and p[-1] not in moved_from}
    added = [p[-1] for st, *p in rows_nr if st == "A" and TEST_PATH.match(p[-1]) and p[-1] not in moved_to]
    for g in gone:
        try:
            gone[g] = tests_shape(_blob(root, mb, g) or "")
        except ValueError as e:  # 読めない所を「試験が無い」と読まない（足した試験の file が在れば、移した先を照らせない＝赤）
            if added:
                errs.append(f"{g}（消した側）: 試験の file を構文で読めず、移した試験かを照らせない（{e}）。直してから照らす")
            gone[g] = {}
    for path in added:
        try:
            names = set(tests_shape(_now(root, path)))
        except ValueError as e:  # 前は読み飛ばした＝移した試験を見落とした。PR では pytest が走らないので、ここで赤にする
            errs.append(f"{path}: 試験の file を構文で読めない（{e}）。直してから照らす")
            continue
        src = [g for g, shape in gone.items() if shape and names & set(shape)]
        if src:
            pairs.append((src, path))
    for before_paths, path in pairs:
        moved = before_paths != [path]
        label = f"{path}（元は {'・'.join(before_paths)}）" if moved else path
        try:
            shapes = [tests_shape(_blob(root, mb, b) or "") for b in before_paths]
            after = tests_shape(_now(root, path))
        except ValueError as e:
            errs.append(f"{label}: 試験の数を照らせない（{e}）。直してから照らす")
            continue
        before: dict[str, int] = {}
        for s in shapes:
            before.update(s)
        n = len(after) - sum(map(len, shapes))
        new = sorted(k for k in after if k not in before)
        # 名を変えた file では、元の file に無い名の試験も足した物と見る（数を揃えて入れ替える形を通さない）
        if n > 0 or (moved and new):
            errs.append(f"{label}: 元から在る試験の file に試験を {max(n, len(new))} 本足した"
                        f"（{'・'.join(new[:5]) or '数が増えた'}）。{GROW}")
        axes = sorted(k for k in after if k in before and after[k] > before[k])
        if axes:
            errs.append(f"{label}: 元から在る試験に parametrize の軸を足して試験を増やした（{'・'.join(axes[:5])}）。"
                        f"在る parametrize の行を足すのはよい。{GROW}")
    return errs


def unchecked(kind: str, why: str) -> int:
    """照らしていない訳を出し、検査の入口（check_all の AF_CHECK_UNCHECKED）へ同じ訳を渡して 3 を返す。
    kind は「対象外」（その場に照らす物が無い）か「照らせない」（照らす物は在るのに値が無い。CI では赤）。"""
    print(f"pr_shape: 照らしていない（{kind}: {why}）")
    if os.environ.get("AF_CHECK_UNCHECKED"):
        Path(os.environ["AF_CHECK_UNCHECKED"]).write_text(f"{kind}: {why}\n", encoding="utf-8")
    return 3


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
        return unchecked("対象外", "main への push＝PR の差分が無い（PR の時に照らした）")
    if a.branch in ("HEAD", ""):
        return unchecked("照らせない", "枝の名が分からない＝detached HEAD。GITHUB_HEAD_REF に枝の名を渡すと照らす")
    if not a.branch.startswith("claude/"):
        return unchecked("対象外", f"{a.branch} は AI の窓の枝 claude/… でない＝人の PR は止めない")
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
