#!/usr/bin/env python3
"""レビューの関所: PR の今の先端がレビューに入ってよい形かを、GitHub の記録から読んで決める（AI の申告で決めない）。

意図: レビューの窓が見るのは中身だけにし、機械で分かる事（CI の必須の検査・main との衝突・同じ先端の判定の重なり）で
レビューを回さない。レビューは 1 つの先端に 1 回・判定は 1 つ。
課題: レビューを 5 回回した PR で、中身の赤は 1 回目だけで、残りは機械で分かる事（検査の赤・main との衝突）だった。
同じ先端に 1 分違いで判定が 2 つ出た。
原因: レビューを頼む前と判定に入る前に、PR の状態を記録から読む関所が無く、頼む・入るを窓の判断に任せていた。

  python3 plugins/checker/scripts/review_gate.py --repo <owner/name> --pr <番号>

読む物（GitHub の REST・公開の repo は鍵なしで読める・GITHUB_TOKEN が在れば付ける）:
  PR（先端の SHA・開いているか・mergeable_state）／base の枝の必須の検査（rules/branches/<base> の required_status_checks。
  base の枝に無い＝積んだ PR は既定の枝の物）／
  先端の check run と commit status／PR のコメント（同じ先端の判定 `見た先端: <先端12>` が在るか）。
入ってよい: 開いている・mergeable_state が clean・必須の検査が全部、先端で終わって success（neutral・skipped も GitHub と同じく通す）・
  同じ先端の判定がまだ無い。どれかが外れたら「まだ」（同じ先端の判定が在れば「済み」）。
exit: 0=入ってよい / 1=まだ・済み（訳を 1 行ずつ）/ 2=読めない（入ってよいと言わない＝まだと同じに扱う）。
材料を file で受ける口は置かない（窓が書いた材料で関所を通さない）。試験は decide を直に呼ぶ。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
OK = {"success", "neutral", "skipped"}
VERDICT = re.compile(r"^\s*レビューした窓\s*[:：]\s*(session_[A-Za-z0-9]+)\s+判定\s*[:：]\s*(green|red)\b", re.M)
SEEN = re.compile(r"^\s*見た先端\s*[:：]\s*([0-9a-f]{12})\s*$", re.M)
UNKNOWN_TRIES = 4   # mergeable_state は GitHub が後で数える（unknown の間は少し待って読み直す）


def required_contexts(rules: list) -> list[str]:
    """rules/branches/<base> の返しから、必須の検査の名の並び。"""
    out: list[str] = []
    for r in rules or []:
        if r.get("type") == "required_status_checks":
            for c in (r.get("parameters") or {}).get("required_status_checks") or []:
                if c.get("context") and c["context"] not in out:
                    out.append(c["context"])
    return out


def check_states(runs: list, statuses: list) -> dict[str, str]:
    """{検査の名: 状態}。check run は終わっていれば conclusion・まだなら status。同じ名は新しい物を取る。"""
    out: dict[str, tuple[str, str]] = {}
    for r in runs or []:
        when = r.get("completed_at") or r.get("started_at") or ""
        state = r.get("conclusion") if r.get("status") == "completed" else (r.get("status") or "queued")
        name = r.get("name") or ""
        if name and (name not in out or when >= out[name][0]):
            out[name] = (when, state or "")
    for s in statuses or []:   # commit status（古い口）。check run が無い名だけ
        name = s.get("context") or ""
        if name and name not in out:
            out[name] = (s.get("updated_at") or "", s.get("state") or "")
    return {k: v[1] for k, v in out.items()}


def verdicts_on(comments: list, head: str) -> list[str]:
    """同じ先端に出た判定の 1 行目（`レビューした窓: … 判定: …`）の並び。"""
    out = []
    for c in comments or []:
        body = c.get("body") or ""
        m, s = VERDICT.search(body), SEEN.search(body)
        if m and s and head.startswith(s.group(1)):
            out.append(m.group(0).strip())
    return out


def decide(pr: dict, required: list[str], states: dict[str, str], comments: list) -> tuple[str, list[str]]:
    """("入ってよい"|"まだ"|"済み", 訳の並び)。材料は全部 GitHub の記録（呼ぶ側が読んで渡す）。"""
    head = ((pr.get("head") or {}).get("sha") or "")
    why: list[str] = []
    if pr.get("state") != "open" or pr.get("merged"):
        why.append("PR が開いていない（閉じた・合流済み）")
    ms = pr.get("mergeable_state") or "unknown"
    if ms != "clean":
        say = {"dirty": "main と衝突している（枝へ main を merge して衝突を解く）",
               "behind": "base の枝に遅れている", "blocked": "必須の検査か守りの決まりが満たされていない",
               "unstable": "必須でない検査に赤か走り中がある", "draft": "下書きの PR",
               "unknown": "GitHub がまだ数え終えていない（少し後で引き直す）"}.get(ms, "")
        why.append("mergeable_state が %s（clean でない）%s" % (ms, "＝" + say if say else ""))
    if not required:
        why.append("base の枝の必須の検査が読めない（必須の検査が無い所では関所を通さない）")
    for name in required:
        st = states.get(name)
        if st is None:
            why.append("必須の検査 %s が先端 %s に無い（まだ走っていない）" % (name, head[:12]))
        elif st not in OK:
            why.append("必須の検査 %s が %s（緑でない）" % (name, st))
    if why:
        return "まだ", why
    done = verdicts_on(comments, head)
    if done:
        return "済み", ["先端 %s に判定が既に在る（%s）。同じ先端に 2 つ目の判定を出さない" % (head[:12], done[0])]
    return "入ってよい", []


def _get(path: str, token: str):
    url = path if path.startswith("http") else API + path
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "af-review-gate"}
    if token:
        hdr["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if token and e.code == 401:   # 窓の環境の鍵がこの repo に効かない時は、公開の repo を鍵なしで読む
            return _get(path, "")
        raise


def _pages(path: str, token: str, key: str = "") -> list:
    out: list = []
    for page in range(1, 11):
        sep = "&" if "?" in path else "?"
        got = _get("%s%sper_page=100&page=%d" % (path, sep, page), token)
        items = (got.get(key) or []) if key else got
        out.extend(items)
        if len(items) < 100:
            return out
    raise OSError("%s が 1000 件を越え、全部を読めない" % path)


def read_facts(repo: str, number: int, token: str, wait=time.sleep):
    pr = _get("/repos/%s/pulls/%d" % (repo, number), token)
    for i in range(UNKNOWN_TRIES):
        if (pr.get("mergeable_state") or "unknown") != "unknown" or i == UNKNOWN_TRIES - 1:
            break
        wait(3)
        pr = _get("/repos/%s/pulls/%d" % (repo, number), token)
    head = pr["head"]["sha"]
    required = required_contexts(_get("/repos/%s/rules/branches/%s" % (repo, pr["base"]["ref"]), token))
    if not required:   # 積んだ PR（base が別の枝）は最後に既定の枝へ入る＝既定の枝の必須の検査で見る
        default = _get("/repos/%s" % repo, token).get("default_branch") or ""
        if default and default != pr["base"]["ref"]:
            required = required_contexts(_get("/repos/%s/rules/branches/%s" % (repo, default), token))
    runs = _pages("/repos/%s/commits/%s/check-runs" % (repo, head), token, key="check_runs")
    statuses = _pages("/repos/%s/commits/%s/statuses" % (repo, head), token)
    comments = _pages("/repos/%s/issues/%d/comments" % (repo, number), token)
    return pr, required, check_states(runs, statuses), comments


def main(argv=None, read=read_facts) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", type=int, required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", a.repo):
        print("review_gate: 読めない — --repo は owner/name の形で渡す")
        return 2
    try:
        pr, required, states, comments = read(a.repo, a.pr, os.environ.get("GITHUB_TOKEN") or "")
    except Exception as e:  # noqa: BLE001  読めない時は入ってよいと言わない（exit 2＝まだと同じに扱う）
        print("review_gate: 読めない — GitHub の記録を引けない（%s）。判定に入らない" % e)
        return 2
    kind, why = decide(pr, required, states, comments)
    head = (pr.get("head") or {}).get("sha", "")[:12]
    for w in why:
        print("✗ " + w)
    if kind == "入ってよい":
        print("review_gate: 入ってよい — #%d@%s 必須の検査 %s が緑・mergeable_state clean・この先端の判定はまだ無い"
              % (a.pr, head, "・".join(required)))
        return 0
    print("review_gate: %s — #%d@%s（判定に入らない。書いた窓へ「%s」と訳だけを返す）" % (kind, a.pr, head, kind))
    print("直し: 書いた窓は訳を 1 つずつ潰さず、検査の赤・衝突は細目 §3「まず構造を疑う」で原因から直してからレビューを頼む")
    return 1


if __name__ == "__main__":
    sys.exit(main())
