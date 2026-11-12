#!/usr/bin/env python3
"""main に入った commit に打つ次の版の印（git の tag）を決める。

決め方: main に入るたびに、一番新しい版の印 vX.Y.Z の小の位を 1 上げた印を、その commit に打つ。
  - その commit に版の印が既にあれば打たない（同じ commit を 2 度数えない）。
  - 版の印が 1 つも無ければ v0.0.1。
  - 中・大の位を上げたい時だけ、手で回す口で版を渡す（docs/版の出し方.md）。

使い方:
  python3 scripts/release/next_tag.py                     # 打つ印を「版 SHA」の 1 行で出す（打たない時は何も出さない）
  python3 scripts/release/next_tag.py --version v0.5.0    # 手で回す口: 版を渡す（形・既にある印・今より新しいかを照らす）
引数: --repo（既定 .）・--ref（既定 HEAD）
"""
import argparse
import re
import subprocess
import sys

VERSION_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def parse(tag):
    m = VERSION_RE.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def latest(tags):
    vs = [v for v in (parse(t) for t in tags) if v]
    return max(vs) if vs else None


def next_version(tags):
    """版の印の並びから、次の印（小の位を 1 上げる）を返す。"""
    top = latest(tags)
    if top is None:
        return "v0.0.1"
    return "v%d.%d.%d" % (top[0], top[1], top[2] + 1)


def plan(tags, tags_at_ref, version=""):
    """打つ印の名か None。tags は全部の印、tags_at_ref はその commit に付いた印。"""
    if version:
        v = parse(version)
        if v is None:
            raise ValueError("版の形が違う（vX.Y.Z）: %r" % version)
        if version in tags:
            raise ValueError("その版の印は既にある: %s" % version)
        top = latest(tags)
        if top is not None and v <= top:
            raise ValueError("今の一番新しい版 v%d.%d.%d より新しくない: %s" % (top + (version,)))
        return version
    if any(parse(t) for t in tags_at_ref):
        return None
    return next_version(tags)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--version", default="")
    a = ap.parse_args(argv)
    tags = git(a.repo, "tag", "--list").split()
    sha = git(a.repo, "rev-parse", a.ref + "^{commit}").strip()
    at = git(a.repo, "tag", "--points-at", sha).split()
    try:
        name = plan(tags, at, a.version.strip())
    except ValueError as e:
        sys.stderr.write("止まる: %s\n" % e)
        return 2
    if name:
        print("%s %s" % (name, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
