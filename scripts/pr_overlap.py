#!/usr/bin/env python3
"""開いている他の PR と、同じ file の同じ行の辺りを書き換えていないかを知らせる（止めない・exit は常に 0）。

なぜ在るか: 並ぶ PR が 細目.md・核.md・CONTRIBUTING.md・各 SKILL.md の同じ節を書き換えると（追記でなく本当の重なり）、
後に入る方が合流の時に初めて衝突に気づき、見直しをやり直していた。同じ節を同時に直すのは中身の食い違いなので
構造で消す物でなく早く知る物＝PR を出した時に重なる PR を名指しし、書いた窓どうし（と親の窓）が先に順を決める。
重なり: 同じ file で、main の側の行の範囲（差分の塊の @@ -a,b の範囲）が CONTEXT 行の内で触れ合う物。

  python3 scripts/pr_overlap.py --repo <owner/name> --pr <番号>      # CI（GITHUB_TOKEN で読むだけ）
  python3 scripts/pr_overlap.py --self <patch の JSON> --others <JSON>  # 試験（{pr: {file: patch}} の形）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

CONTEXT = 3
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)


def ranges(patch: str) -> list[tuple[int, int]]:
    out = []
    for m in HUNK.finditer(patch or ""):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        out.append((start, start + max(n, 1) - 1))
    return out


def overlaps(mine: dict[str, str], others: dict[str, dict[str, str]]) -> list[tuple[str, str, tuple[int, int]]]:
    """[(他の PR, file, 自分の行の範囲)]。"""
    hits = []
    for pr, files in sorted(others.items()):
        for f, patch in files.items():
            if f not in mine:
                continue
            theirs = ranges(patch)
            for a, b in ranges(mine[f]):
                if any(a - CONTEXT <= d and c - CONTEXT <= b for c, d in theirs):
                    hits.append((pr, f, (a, b)))
                    break
    return hits


def _get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "Authorization": f"Bearer {token}", "User-Agent": "af-pr-overlap"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def pr_files(repo: str, pr: int, token: str) -> dict[str, str]:
    out, page = {}, 1
    while True:
        rows = _get(f"https://api.github.com/repos/{repo}/pulls/{pr}/files?per_page=100&page={page}", token)
        for r in rows:
            out[r["filename"]] = r.get("patch") or ""
        if len(rows) < 100:
            return out
        page += 1


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
                print("pr_overlap: 知らせ — 照らす材料（--repo・--pr・GITHUB_TOKEN）が無いので見ていない")
                return 0
            mine = pr_files(a.repo, a.pr, token)
            opened = _get(f"https://api.github.com/repos/{a.repo}/pulls?state=open&per_page=100", token)
            others = {f"#{p['number']}": pr_files(a.repo, p["number"], token) for p in opened if p["number"] != a.pr}
    except Exception as e:  # noqa: BLE001  知らせる道具が壊れても PR は止めない（壊れた事は名指しで出す）
        print(f"pr_overlap: 知らせ — 他の PR を読めず見ていない（{e}）")
        return 0
    hits = overlaps(mine, others)
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
