#!/usr/bin/env python3
"""レビューの頼み直しの文を作る（書いた窓が回す）。前回の red の止めるを 1 つずつ、直した commit と結ぶ。

  python3 rereview.py --previous <前回の判定のファイル> --fix <N>=<commit> [--fix …] [--head <ref>]

前回の判定の `## 所見` の `[止める｜…]` を上から 1, 2, … と数え、全部の N に --fix が要る。各 commit は
今の先端（--head・既定 HEAD）の祖先で、前回の `見た先端` の祖先でない（前回の後に足した commit）こと。
先端が前回の見た先端から動いていない・N が欠けた・commit が範囲の外なら頼み直しの文を出さない（exit 1）。
緑なら頼みの文（`前回の止める N 番 → <commit12>` の行）を出す。レビューの窓はこの行を見て、
verdict_form.py --previous で前回の止めるを全部番号で照らす。
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verdict_form as VF  # noqa: E402  判定の形の正本


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def ancestor(a, b):
    return git("merge-base", "--is-ancestor", a, b)[0] == 0


def plan(previous, fixes, head):
    """(誤りの並び, 頼みの文の行)。"""
    stops = VF.stops_of(previous)
    old = VF.seen_head(previous)
    errs, lines = [], []
    if not stops:
        errs.append("前回の判定に `[止める｜…]` が無い（頼み直しの前回でない）")
    rc, now = git("rev-parse", head)
    if rc != 0:
        return ["先端 %s が読めない" % head], []
    if old and now.startswith(old):
        errs.append("先端 %s が前回の見た先端と同じ（直した commit が無い）" % old)
    rc_old, old_full = git("rev-parse", old) if old else (1, "")
    for n in range(1, len(stops) + 1):
        sha = fixes.get(n)
        if not sha:
            errs.append("前回の止める %d 番（%s）に直した commit が無い（--fix %d=<commit>）" % (n, stops[n - 1][:30], n))
            continue
        rc, full = git("rev-parse", "--verify", sha + "^{commit}")
        if rc != 0:
            errs.append("止める %d 番の commit %s が無い" % (n, sha))
            continue
        if not ancestor(full, now):
            errs.append("止める %d 番の commit %s が今の先端に入っていない" % (n, sha))
        elif rc_old == 0 and ancestor(full, old_full):
            errs.append("止める %d 番の commit %s は前回の見た先端より前（前回の後に直していない）" % (n, sha))
        lines.append("前回の止める %d 番 → %s（%s）" % (n, full[:12], stops[n - 1][2:60]))
    for n in sorted(set(fixes) - set(range(1, len(stops) + 1))):
        errs.append("--fix %d は前回の止めるに無い（前回は %d 個）" % (n, len(stops)))
    return errs, lines


def main(argv):
    args, prev, head, fixes, i = argv[1:], None, "HEAD", {}, 0
    while i < len(args):
        a = args[i]
        v = args[i + 1] if i + 1 < len(args) else None
        if a == "--previous" and v and prev is None:
            prev = v
        elif a == "--head" and v:
            head = v
        elif a == "--fix" and v and re.fullmatch(r"\d+=[0-9A-Za-z._/-]+", v) and int(v.split("=")[0]) not in fixes:
            n, sha = v.split("=", 1)
            fixes[int(n)] = sha
        else:
            sys.stderr.write("知らない印か値の欠け・2 度書き: %s\n%s" % (a, __doc__))
            return 2
        i += 2
    if not prev:
        sys.stderr.write(__doc__)
        return 2
    errs, lines = plan(Path(prev).read_text(encoding="utf-8"), fixes, head)
    if errs:
        for e in errs:
            print(e)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
