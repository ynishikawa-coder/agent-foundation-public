#!/usr/bin/env python3
"""開いている他の PR と、同じ file の同じ行の辺りを書き換えていないかを知らせる（止めない・見た時は exit 0）。

なぜ在るか: 並ぶ PR が 細目.md・核.md・CONTRIBUTING.md・各 SKILL.md の同じ節を書き換えると（追記でなく本当の重なり）、
後に入る方が合流の時に初めて衝突に気づき、見直しをやり直していた。同じ節を同時に直すのは中身の食い違いなので
構造で消す物でなく早く知る物＝PR を出した時に重なる PR を名指しし、書いた窓どうし（と親の窓）が先に順を決める。
重なり: 同じ file で、main の側の行の範囲（差分の塊の @@ -a,b の範囲）が CONTEXT 行の内で触れ合う物。
物差し: PR ごとの差分の行番号は、その PR の分かれ目（merge base）の main の行番号で、違う時期に切った PR どうしでは
  物差しが違う。なので各 PR の範囲を、分かれ目から base の枝の今の先端までの差分で今の先端の行番号へ写してから比べる
  （写す所が書き換えられた行は、書き換えた後の範囲の全部へ広げる＝見落とす側に倒さない）。比べる PR は同じ base の枝の物だけ。

  python3 scripts/pr_overlap.py --repo <owner/name> --pr <番号>      # CI（GITHUB_TOKEN で読むだけ）
  python3 scripts/pr_overlap.py --self <patch の JSON> --others <JSON>  # 試験（{pr: {file: patch}} の形）

exit: 0=見た（重なりの有無は文で知らせる・止めない）/ 3=見ていない（材料が無い・他の PR を読めない）。
  見ていない時を 0 で終えると、知らせを出せなかった job が「重なりは無い」と同じ緑の印に見える。なので 3 で終え、
  GitHub の上では ::warning:: の注記も出す（job は止めない＝ci.yml の job overlap は step を continue-on-error で回す）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

CONTEXT = 3
UNSEEN = 3  # 見ていない（緑に数えない）
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def ranges(patch: str) -> list[tuple[int, int]]:
    out = []
    for m in HUNK.finditer(patch or ""):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        out.append((start, start + max(n, 1) - 1))
    return out


def _hunks(patch: str) -> list[tuple[int, int, int, int]]:
    """[(古い側の始め, 行数, 新しい側の始め, 行数)]。行数 0 の塊（足しただけ・消しただけ）の始めは、その次の行に直す。"""
    out = []
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", patch or "", re.M):
        os_, ol = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        ns, nl = int(m.group(3)), int(m.group(4) if m.group(4) is not None else 1)
        out.append((os_ if ol else os_ + 1, ol, ns if nl else ns + 1, nl))
    return out


def carry(span: tuple[int, int], patch: str | None) -> tuple[int, int]:
    """分かれ目の行番号の範囲 span を、分かれ目→今の先端の差分 patch で今の先端の行番号へ写す（patch が無ければそのまま）。
    書き換えられた行に掛かる所は、書き換えた後の範囲の全部へ広げる。"""
    if not patch:
        return span
    hunks = _hunks(patch)

    def one(x: int) -> tuple[int, int]:
        delta = 0
        for os_, ol, ns, nl in hunks:
            if x < os_:
                break
            if x < os_ + ol:
                return ns, ns + max(nl, 1) - 1
            delta = (ns + nl) - (os_ + ol)
        return x + delta, x + delta

    a, b = one(span[0]), one(span[1])
    return min(a[0], b[0]), max(a[1], b[1])


def overlaps_ranges(mine: dict[str, list[tuple[int, int]]],
                    others: dict[str, dict[str, list[tuple[int, int]]]]) -> list[tuple[str, str, tuple[int, int]]]:
    """同じ物差しの行の範囲どうしで [(他の PR, file, 自分の行の範囲)]。"""
    hits = []
    for pr, files in sorted(others.items()):
        for f, theirs in files.items():
            if f not in mine:
                continue
            for a, b in mine[f]:
                if any(a - CONTEXT <= d and c - CONTEXT <= b for c, d in theirs):
                    hits.append((pr, f, (a, b)))
                    break
    return hits


def overlaps(mine: dict[str, str], others: dict[str, dict[str, str]]) -> list[tuple[str, str, tuple[int, int]]]:
    """同じ分かれ目から切った PR どうし（{file: patch}）で [(他の PR, file, 自分の行の範囲)]（試験の口）。"""
    return overlaps_ranges({f: ranges(p) for f, p in mine.items()},
                           {pr: {f: ranges(p) for f, p in fs.items()} for pr, fs in others.items()})


def on_tip(files: dict[str, str], to_tip: dict[str, str]) -> dict[str, list[tuple[int, int]]]:
    """PR の {file: patch（分かれ目から）} を、今の先端の行番号の {file: [範囲]} へ写す。"""
    return {f: [carry(r, to_tip.get(f)) for r in ranges(p)] for f, p in files.items()}


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "Authorization": f"Bearer {token}", "User-Agent": "af-pr-overlap"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def compare(repo: str, base: str, head: str, token: str) -> tuple[str, dict[str, str]]:
    """(分かれ目の commit, {file: patch（分かれ目から head まで）})。"""
    c = _get(f"https://api.github.com/repos/{repo}/compare/{base}...{head}", token)
    return c["merge_base_commit"]["sha"], {r["filename"]: r.get("patch") or "" for r in c.get("files") or []}


def on_base_tip(repo: str, base_tip: str, head: str, token: str, cache: dict) -> dict[str, list[tuple[int, int]]]:
    """PR（先端 head）の範囲を、base の枝の今の先端 base_tip の行番号で。"""
    mb, files = compare(repo, base_tip, head, token)
    if mb != base_tip and mb not in cache:
        cache[mb] = compare(repo, mb, base_tip, token)[1]
    return on_tip(files, cache.get(mb) or {})


def unseen(why: str) -> int:
    """見ていない事を名指して exit 3（緑の印にしない）。GitHub の上では注記 ::warning:: も出す。"""
    print(f"pr_overlap: 見ていない — {why}（重なる PR が無いとは言えない）")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=pr_overlap 見ていない::{why}（重なる PR が無いとは言えない）")
    return UNSEEN


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--self", dest="self_json")
    ap.add_argument("--others")
    a = ap.parse_args(argv)
    try:
        if a.self_json:
            mine = json.loads(open(a.self_json, encoding="utf-8").read())
            others = json.loads(open(a.others, encoding="utf-8").read())
        else:
            token = os.environ.get("GITHUB_TOKEN") or ""
            if not (a.repo and a.pr and token):
                return unseen("照らす材料（--repo・--pr・GITHUB_TOKEN）が無い")
            me = _get(f"https://api.github.com/repos/{a.repo}/pulls/{a.pr}", token)
            base = me["base"]["ref"]
            tip = _get(f"https://api.github.com/repos/{a.repo}/branches/{base}", token)["commit"]["sha"]
            cache: dict = {}
            mine_r = on_base_tip(a.repo, tip, me["head"]["sha"], token, cache)
            opened = _get(f"https://api.github.com/repos/{a.repo}/pulls?state=open&per_page=100", token)
            others_r = {f"#{p['number']}": on_base_tip(a.repo, tip, p["head"]["sha"], token, cache)
                        for p in opened if p["number"] != a.pr and (p.get("base") or {}).get("ref") == base}
    except Exception as e:  # noqa: BLE001  知らせる道具が壊れても PR は止めない（見ていない事を exit 3 で名指す）
        return unseen(f"他の PR を読めない（{e}）")
    hits = overlaps(mine, others) if a.self_json else overlaps_ranges(mine_r, others_r)
    for pr, f, (s, e) in hits:
        print(f"⚠ {pr} も {f} の {s}〜{e} 行の辺りを書き換えている（同じ節の本当の重なり）")
    if hits:
        print("pr_overlap: 知らせ — 重なる PR の書いた窓と親の窓で、どちらを先に入れて後の方が取り込み直すかを今決める"
              "（合流の時に初めて衝突に気づかない）。止めはしない")
    else:
        print("pr_overlap: 重なる PR は無い")
    return 0


if __name__ == "__main__":
    sys.exit(main())
