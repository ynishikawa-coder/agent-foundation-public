#!/usr/bin/env python3
"""公開の repo の見回り。検査が付いていない・main の守りで検査が必須になっていない公開 repo を見つけて知らせる。

GitHub の設定そのものは AI には固定できない。なので「外れたら必ず見つけて知らせる」をこの 1 本で担う。
見る相手: patrol.json の owners の公開 repo（archive 済みは除く）。各 repo の既定の枝について:
  1. 呼び口: .github/workflows/ のどれかの、必須の検査の名 `public-guard` の job の step が、PR・push で走る形で
     土台の action `public-guard` を main の先端（@main）で呼んでいる（土台そのものは `./public-guard`）。
     版の印や SHA で止めた呼び口は、直した検査が届かないので外れ。呼び口の見分けは workflow の読み手
     （同じ dir の workflow_reader.py・守りの hook と手元の検査も同じ物を読む）が正本。コメントの行・job の外・
     workflow_dispatch 等だけで走る workflow・if: false の job は呼び口に数えない。
  2. 守り: 既定の枝の守り（ruleset か枝の保護）の必須の検査に `public-guard` が入っている
     （土台そのものは、使う側と同じ入れ方で plugin を入れて起動する `plugin-smoke` も）

使い方: python3 patrol.py [--owner O ...] [--report-issue]
  --report-issue: Actions の中で、この repo の issue「公開の検査の見回り」を立てる・書き替える・0 件なら閉じる。
exit: 0=外れ 0 / 1=外れあり / 2=GitHub が読めない
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import workflow_reader as W  # noqa: E402  呼び口の見分けの正本（同じ dir）

API = "https://api.github.com"
FOUNDATION = W.FOUNDATION
CHECK = W.CHECK
# 土台は main の先端をそのまま配るので、合流の前に「使う側と同じ入れ方で入れて起動する」試験を必須にする。
FOUNDATION_CHECKS = (CHECK, "plugin-smoke")
REF = "main"
ISSUE_TITLE = "公開の検査の見回り"


class GitHub:
    def __init__(self, token: str | None = None):
        self.token = token

    def req(self, path: str, method: str = "GET", body: dict | None = None):
        """(状態, JSON)。404 は (404, None)。"""
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header("Accept", "application/vnd.github+json")
        r.add_header("User-Agent", "public-guard-patrol")
        if self.token:
            r.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(r, timeout=30) as res:
                raw = res.read()
                return res.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            raise

    def get(self, path: str):
        return self.req(path)[1]

    def pages(self, path: str):
        page = 1
        while True:
            sep = "&" if "?" in path else "?"
            items = self.get(f"{path}{sep}per_page=100&page={page}") or []
            yield from items
            if len(items) < 100:
                return
            page += 1


# 外れが在る時の最後の行（中身は土台の細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 1 つずつ直すだけで済ませず、意図（公開の repo が全部、公開の検査を main で通す）とのずれから入り、外れる形になった原因を細目 §3「まず構造を疑う」で探して直す"

def public_repos(gh: GitHub, owner: str) -> list[dict]:
    return [r for r in gh.pages(f"/users/{owner}/repos?type=owner")
            if not r.get("private") and not r.get("archived")]


def workflow_texts(gh: GitHub, full: str, branch: str) -> list[str]:
    items = gh.get(f"/repos/{full}/contents/.github/workflows?ref={branch}") or []
    out = []
    for it in items if isinstance(items, list) else []:
        if it.get("type") == "file" and it["name"].endswith((".yml", ".yaml")):
            f = gh.get(f"/repos/{full}/contents/{it['path']}?ref={branch}") or {}
            out.append(base64.b64decode(f.get("content", "")).decode("utf-8", "replace"))
    return out


def required_checks(gh: GitHub, full: str, branch: str) -> set[str]:
    """既定の枝で必須の検査の名（枝の保護と ruleset の両方から）。"""
    names = set()
    b = gh.get(f"/repos/{full}/branches/{branch}") or {}
    rsc = (b.get("protection") or {}).get("required_status_checks") or {}
    names |= set(rsc.get("contexts") or [])
    names |= {c.get("context") for c in rsc.get("checks") or [] if c.get("context")}
    for rule in gh.get(f"/repos/{full}/rules/branches/{branch}") or []:
        if rule.get("type") == "required_status_checks":
            for c in (rule.get("parameters") or {}).get("required_status_checks") or []:
                if c.get("context"):
                    names.add(c["context"])
    return names


def call_problems(gh: GitHub, full: str, at: str) -> list[str]:
    """at（枝・commit）の workflow で見た呼び口の外れ（無ければ空）。"""
    problems = []
    texts = workflow_texts(gh, full, at)
    # 数える呼び口のうち、必須の検査 public-guard の job の物だけ（別の job の呼び口では、必須の検査が照らさない）。
    # ./public-guard（その repo の中の action）は土台そのものでだけ土台の action。
    calls = [c for t in texts for c in W.counted(t, FOUNDATION)
             if c.check == CHECK and (not c.local or full == FOUNDATION)]
    if not calls:
        problems.append("公開の検査の呼び口が無い（job %s の step で PR・push の時に呼ぶ。public-guard/caller-template.yml を"
                        " .github/workflows/ へ）" % CHECK)
    for ref in dict.fromkeys(c.ref for c in calls if not c.local):
        if ref != REF:
            problems.append(f"公開の検査を main の先端で呼んでいない（@{ref or '版なし'} → @{REF}）")
    return problems


def inspect(gh: GitHub, repo: dict) -> list[str]:
    """1 つの公開 repo の外れ（無ければ空）。"""
    full, branch = repo["full_name"], repo.get("default_branch") or "main"
    problems = call_problems(gh, full, branch)
    have = required_checks(gh, full, branch)
    for check in (FOUNDATION_CHECKS if full == FOUNDATION else (CHECK,)):
        if check not in have:
            problems.append(f"{branch} の守りの必須の検査に {check} が無い（Settings → Rules → Rulesets）")
    return problems


def fixing_prs(gh: GitHub, full: str) -> list[dict]:
    """合流すれば呼び口の外れが消える、その repo の開いた PR（呼び口の見分けは外れと同じ読み手で、PR の先端を読む）。

    外れを出すだけでは読む者がいない（直しの PR がレビューを通ったまま合流されず、見回りが赤のまま続いた）。
    見回りの赤と issue に「次の手＝この PR の合流」を名指して載せる。守りの外れ（必須の検査）は設定なので PR では消えない。
    """
    base = (gh.get(f"/repos/{full}") or {}).get("default_branch") or "main"
    if not call_problems(gh, full, base):
        return []
    return [pr for pr in gh.pages(f"/repos/{full}/pulls?state=open&base={base}")
            if (pr.get("head") or {}).get("sha") and not call_problems(gh, full, pr["head"]["sha"])]


def fixes(gh: GitHub, found: dict[str, list[str]]) -> dict[str, list[dict]]:
    return {full: prs for full in found if (prs := fixing_prs(gh, full))}


def patrol(gh: GitHub, owners: list[str]) -> dict[str, list[str]]:
    found = {}
    for owner in owners:
        for repo in public_repos(gh, owner):
            p = inspect(gh, repo)
            if p:
                found[repo["full_name"]] = p
    return found


def render(found: dict[str, list[str]], owners: list[str], prs: dict[str, list[dict]] | None = None) -> str:
    if not found:
        return f"外れ 0（見た持ち主: {', '.join(owners)}）"
    lines = [f"外れ {len(found)} repo（見た持ち主: {', '.join(owners)}）。直し方は docs/公開の検査.md の「公開の repo を作る・直す」。", ""]
    for full, probs in sorted(found.items()):
        lines.append(f"- {full}")
        lines += [f"  - {p}" for p in probs]
        for pr in (prs or {}).get(full, []):
            lines.append(f"  - 次の手: 開いている PR #{pr['number']}「{pr.get('title', '')}」を合流すれば呼び口の外れが消える"
                         f"（{pr.get('html_url', '')}）。合流の決まりはその repo の手順")
    return "\n".join(lines)


def report_issue(gh: GitHub, here: str, found: dict, text: str) -> None:
    issues = [i for i in gh.pages(f"/repos/{here}/issues?state=open")
              if i.get("title") == ISSUE_TITLE and "pull_request" not in i]
    if found:
        if not issues:
            gh.req(f"/repos/{here}/issues", "POST", {"title": ISSUE_TITLE, "body": text})
            return
        # 同じ題の issue が 2 つ以上開いていれば、いちばん古い 1 つを書き替え、残りは行き先を書いて閉じる
        # （1 つ目だけ直して残りを古い本文のまま開いておかない）
        keep, *dups = sorted(issues, key=lambda i: i["number"])
        gh.req(f"/repos/{here}/issues/{keep['number']}", "PATCH", {"body": text})
        for i in dups:
            gh.req(f"/repos/{here}/issues/{i['number']}/comments", "POST",
                   {"body": f"同じ題の issue が重なっていたので、#{keep['number']} へまとめて閉じます。"})
            gh.req(f"/repos/{here}/issues/{i['number']}", "PATCH", {"state": "closed", "state_reason": "not_planned"})
    else:
        for i in issues:
            gh.req(f"/repos/{here}/issues/{i['number']}/comments", "POST", {"body": text})
            gh.req(f"/repos/{here}/issues/{i['number']}", "PATCH", {"state": "closed", "state_reason": "completed"})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公開の repo の見回り")
    ap.add_argument("--owner", action="append")
    ap.add_argument("--report-issue", action="store_true")
    a = ap.parse_args(argv)
    owners = a.owner or json.loads((Path(__file__).parent / "patrol.json").read_text(encoding="utf-8"))["owners"]
    gh = GitHub(os.environ.get("GITHUB_TOKEN") or None)
    try:
        found = patrol(gh, owners)
        prs = fixes(gh, found)
    except (urllib.error.URLError, OSError) as e:
        print(f"✗ GitHub が読めない: {e}")
        return 2
    text = render(found, owners, prs)
    print(("✗ " if found else "✅ ") + text)
    if found:
        print(ROOT_CAUSE)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## 公開の検査の見回り\n\n" + text + "\n")
    if a.report_issue and os.environ.get("GITHUB_REPOSITORY"):
        report_issue(gh, os.environ["GITHUB_REPOSITORY"], found, text)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
