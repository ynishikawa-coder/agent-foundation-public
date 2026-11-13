#!/usr/bin/env python3
"""公開の repo の見回り。検査が付いていない・main の守りで検査が必須になっていない公開 repo を見つけて知らせる。

GitHub の設定そのものは AI には固定できない。なので「外れたら必ず見つけて知らせる」をこの 1 本で担う。
見る相手: patrol.json の owners の公開 repo（archive 済みは除く）。各 repo の既定の枝について:
  1. 呼び口: .github/workflows/ のどれかが土台の action `public-guard` を版の印（vX.Y.Z）で呼んでいる
     （土台そのものは `./public-guard`）
  2. 守り: 既定の枝の守り（ruleset か枝の保護）の必須の検査に `public-guard` が入っている

使い方: python3 patrol.py [--owner O ...] [--report-issue]
  --report-issue: Actions の中で、この repo の issue「公開の検査の見回り」を立てる・書き替える・0 件なら閉じる。
exit: 0=外れ 0 / 1=外れあり / 2=GitHub が読めない
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
FOUNDATION = "ynishikawa-coder/agent-foundation-public"
CHECK = "public-guard"
ISSUE_TITLE = "公開の検査の見回り"
CALL = re.compile(r"uses:\s*['\"]?" + re.escape(FOUNDATION) + r"/public-guard@([^\s'\"#]+)")
LOCAL_CALL = re.compile(r"uses:\s*['\"]?\./public-guard['\"]?\s*$", re.M)
TAG = re.compile(r"^v\d+\.\d+\.\d+$")


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


def inspect(gh: GitHub, repo: dict) -> list[str]:
    """1 つの公開 repo の外れ（無ければ空）。"""
    full, branch = repo["full_name"], repo.get("default_branch") or "main"
    problems = []
    texts = workflow_texts(gh, full, branch)
    refs = [m for t in texts for m in CALL.findall(t)]
    local = full == FOUNDATION and any(LOCAL_CALL.search(t) for t in texts)
    if not refs and not local:
        problems.append("公開の検査の呼び口が無い（public-guard/caller-template.yml を .github/workflows/ へ）")
    for ref in refs:
        if not TAG.match(ref):
            problems.append(f"公開の検査を版の印で固定していない（@{ref} → @vX.Y.Z）")
    if CHECK not in required_checks(gh, full, branch):
        problems.append(f"{branch} の守りの必須の検査に {CHECK} が無い（Settings → Rules → Rulesets）")
    return problems


def patrol(gh: GitHub, owners: list[str]) -> dict[str, list[str]]:
    found = {}
    for owner in owners:
        for repo in public_repos(gh, owner):
            p = inspect(gh, repo)
            if p:
                found[repo["full_name"]] = p
    return found


def render(found: dict[str, list[str]], owners: list[str]) -> str:
    if not found:
        return f"外れ 0（見た持ち主: {', '.join(owners)}）"
    lines = [f"外れ {len(found)} repo（見た持ち主: {', '.join(owners)}）。直し方は docs/公開の検査.md の「公開の repo を作る・直す」。", ""]
    for full, probs in sorted(found.items()):
        lines.append(f"- {full}")
        lines += [f"  - {p}" for p in probs]
    return "\n".join(lines)


def report_issue(gh: GitHub, here: str, found: dict, text: str) -> None:
    issues = [i for i in gh.pages(f"/repos/{here}/issues?state=open")
              if i.get("title") == ISSUE_TITLE and "pull_request" not in i]
    if found:
        if issues:
            gh.req(f"/repos/{here}/issues/{issues[0]['number']}", "PATCH", {"body": text})
        else:
            gh.req(f"/repos/{here}/issues", "POST", {"title": ISSUE_TITLE, "body": text})
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
    except (urllib.error.URLError, OSError) as e:
        print(f"✗ GitHub が読めない: {e}")
        return 2
    text = render(found, owners)
    print(("✗ " if found else "✅ ") + text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## 公開の検査の見回り\n\n" + text + "\n")
    if a.report_issue and os.environ.get("GITHUB_REPOSITORY"):
        report_issue(gh, os.environ["GITHUB_REPOSITORY"], found, text)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
