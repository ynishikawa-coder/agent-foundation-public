#!/usr/bin/env python3
"""CHANGELOG.md の版の見出しと git の履歴から、版の印（git の tag）の先を決める。

決め方: 版 vX.Y.Z の印の先は「main の一本道（first-parent）で、CHANGELOG の
その版の節（見出しの行と中身）が最後に変わった commit」。
  - 版の節が入った時（[Unreleased] を版の見出しに替えた merge）にその commit を指す。
  - 印を打つ前に同じ節へ足されたら、足した commit へ進む。
  - 印を打った後は動かさない（既にある tag は飛ばす・消さない）。
  - [Unreleased] の節だけを足す commit では、どの版の先も動かない。

使い方:
  python3 scripts/release/tags_from_changelog.py            # まだ無い印を「版 SHA」の行で出す
  python3 scripts/release/tags_from_changelog.py --all      # 全部の版（既にある印も）を出す
  python3 scripts/release/tags_from_changelog.py --json     # 機械向け
  python3 scripts/release/tags_from_changelog.py --version v0.1.0 --sha <40 桁> --ref origin/main
      # 手で打つ口: 版の節を持たない過去の版を、形・祖先を照らして「版 SHA」の 1 行で出す
引数: --repo（既定 .）・--ref（既定 HEAD・手で打つ口では祖先を照らす先）・--changelog（既定 CHANGELOG.md）
"""
import argparse
import json
import re
import subprocess
import sys

HEAD_RE = re.compile(r"^## \[(v\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}\s*$")
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ManualError(ValueError):
    """手で打つ口の入力の誤り。"""


def manual(repo, version, sha, ref="HEAD"):
    """手で打つ口: 形と祖先を照らし、打つなら {version, sha}、既にある印なら None。"""
    if not VERSION_RE.match(version or ""):
        raise ManualError(f"版の形が違う（vX.Y.Z）: {version!r}")
    if not SHA_RE.match(sha or ""):
        raise ManualError(f"sha の形が違う（小文字 40 桁）: {sha!r}")
    if git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
        raise ManualError(f"commit が無い: {sha}")
    if git(repo, "merge-base", "--is-ancestor", sha, ref, check=False).returncode != 0:
        raise ManualError(f"{ref} の祖先でない: {sha}")
    if version in existing_tags(repo):
        return None
    return {"version": version, "sha": sha}


def git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def sections(text):
    """版 → その節の文（見出しの行を含む・前後の空白を落とす）。[Unreleased] は入れない。"""
    out = {}
    cur = None
    buf = []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                out[cur] = "\n".join(buf).strip()
            m = HEAD_RE.match(line)
            cur = m.group(1) if m else None
            buf = [line.rstrip()]
        elif cur:
            buf.append(line.rstrip())
    if cur:
        out[cur] = "\n".join(buf).strip()
    return out


def version_commits(repo=".", ref="HEAD", changelog="CHANGELOG.md"):
    """版 → 印の先の commit（SHA）。古い版から順の dict。"""
    shas = git(repo, "rev-list", "--first-parent", "--reverse", ref).stdout.split()
    last = {}
    prev = {}
    for sha in shas:
        r = git(repo, "show", f"{sha}:{changelog}", check=False)
        now = sections(r.stdout) if r.returncode == 0 else {}
        for ver, body in now.items():
            if prev.get(ver) != body:
                last[ver] = sha
        prev = now
    # 今の CHANGELOG に残る版だけ（消された版は打たない）
    return {v: last[v] for v in sorted(prev, key=_key) if v in last}


def _key(ver):
    return tuple(int(x) for x in ver[1:].split("."))


def existing_tags(repo="."):
    return set(git(repo, "tag", "--list").stdout.split())


def plan(repo=".", ref="HEAD", changelog="CHANGELOG.md"):
    """[{version, sha, exists}] を古い版から。"""
    tags = existing_tags(repo)
    return [
        {"version": v, "sha": s, "exists": v in tags}
        for v, s in version_commits(repo, ref, changelog).items()
    ]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=".")
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--changelog", default="CHANGELOG.md")
    p.add_argument("--all", action="store_true", help="既にある印も出す")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", help="手で打つ口: 版の名（--sha と組で）")
    p.add_argument("--sha", help="手で打つ口: 印の先の commit（40 桁）")
    a = p.parse_args(argv)
    if git(a.repo, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        print("履歴が浅い（shallow clone）。fetch-depth: 0 で取り直す。", file=sys.stderr)
        return 2
    if a.version or a.sha:
        try:
            row = manual(a.repo, a.version, a.sha, a.ref)
        except ManualError as e:
            print(f"手で打つ口: {e}", file=sys.stderr)
            return 1
        if row is None:
            print(f"手で打つ口: {a.version} は既にある（動かさない）", file=sys.stderr)
        rows = [row] if row else []
        if a.json:
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['version']} {r['sha']}")
        return 0
    rows = plan(a.repo, a.ref, a.changelog)
    if not a.all:
        rows = [r for r in rows if not r["exists"]]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['version']} {r['sha']}" + (" (既にある)" if r["exists"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
