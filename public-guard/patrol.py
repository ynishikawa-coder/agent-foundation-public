#!/usr/bin/env python3
"""公開の repo の見回り。検査が付いていない・main の守りで検査が必須になっていない公開 repo を見つけて知らせる。

GitHub の設定そのものは AI には固定できない。なので「外れたら必ず見つけて知らせる」をこの 1 本で担う。
見る相手: patrol.json の owners の公開 repo（archive 済みは除く）。各 repo の既定の枝について:
  1. 呼び口: .github/workflows/public-guard.yml が雛形 caller-template.yml と同じ（注釈の行と行末の空白の外は一字も
     違わない＝on・permissions・with の入力名・@main まで）。雛形は見回りがこの checkout の物を直に読む（写さない）。
     ほかの workflow で土台の action を main の先端（@main）以外で呼んでいても外れ。
     土台そのものは ci.yml の job が `./public-guard` を呼び、on・permissions と with の雛形の行を全部持つ。
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
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
FOUNDATION = "ynishikawa-coder/agent-foundation-public"
CHECK = "public-guard"
# 土台は main の先端をそのまま配るので、合流の前に「使う側と同じ入れ方で入れて起動する」試験を必須にする。
FOUNDATION_CHECKS = (CHECK, "plugin-smoke")
REF = "main"
ISSUE_TITLE = "公開の検査の見回り"
CALL = re.compile(r"uses:\s*['\"]?" + re.escape(FOUNDATION) + r"/public-guard@([^\s'\"#]+)")
LOCAL_CALL = re.compile(r"uses:\s*['\"]?\./public-guard['\"]?\s*$", re.M)
CALLER_PATH = ".github/workflows/public-guard.yml"
TEMPLATE = Path(__file__).resolve().parent / "caller-template.yml"


def body_lines(text: str) -> list[str]:
    """比べる行（注釈だけの行・空の行を除き、行末の空白を落とす）。"""
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")
            if ln.strip() and not ln.lstrip().startswith("#")]


def caller_drift(text: str, template: str) -> str | None:
    """呼び口が雛形と違えば最初に違う所の説明（同じなら None）。"""
    have, want = body_lines(text), body_lines(template)
    for i, (h, w) in enumerate(zip(have, want), 1):
        if h != w:
            return f"雛形の {i} 行目（注釈を除く）が違う: 雛形は `{w.strip()}`・ここは `{h.strip()}`"
    if len(have) != len(want):
        return f"行の数が違う（雛形 {len(want)} 行・ここ {len(have)} 行・注釈を除く）"
    return None


def top_block(text: str, key: str) -> list[str]:
    """一番外の `key:` の塊の行（注釈を除く）。"""
    out, inside = [], False
    for ln in body_lines(text):
        if not ln.startswith(" "):
            inside = ln.startswith(key + ":")
        if inside:
            out.append(ln)
    return out


def local_step(text: str) -> set[str]:
    """`uses: ./public-guard` の step の中の行（字下げが step の `-` より深い間）。"""
    lines, out = body_lines(text), set()
    for i, ln in enumerate(lines):
        if LOCAL_CALL.search(ln):
            dash = len(ln) - len(ln.lstrip(" -"))  # uses の字の位置
            for nxt in lines[i + 1:]:
                if len(nxt) - len(nxt.lstrip(" ")) < dash:
                    break
                out.add(nxt.strip())
    return out


def foundation_drift(ci_text: str, template: str) -> list[str]:
    """土台の ci.yml が雛形の on・permissions と with の行を全部持つか（土台は自分の枝の action を呼ぶので全文は比べない）。"""
    probs = [f"{k}: が雛形と違う" for k in ("on", "permissions") if top_block(ci_text, k) != top_block(template, k)]
    tl = body_lines(template)
    withs = [ln.strip() for ln in tl[tl.index(next(x for x in tl if x.strip() == "with:")) + 1:]]
    step = local_step(ci_text)
    missing = [w for w in withs if w not in step]
    if missing:
        probs.append("job public-guard に雛形の with の行が無い: " + "・".join(f"`{m.split(':')[0]}`" for m in missing))
    return probs


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
ROOT_CAUSE = "直し: 外れた repo を 1 つずつ直すだけで済ませず、外れる形になった原因を細目 §3「まず構造を疑う」で探して直す"

def public_repos(gh: GitHub, owner: str) -> list[dict]:
    return [r for r in gh.pages(f"/users/{owner}/repos?type=owner")
            if not r.get("private") and not r.get("archived")]


def workflow_texts(gh: GitHub, full: str, branch: str) -> dict[str, str]:
    """{path: 中身}。"""
    items = gh.get(f"/repos/{full}/contents/.github/workflows?ref={branch}") or []
    out = {}
    for it in items if isinstance(items, list) else []:
        if it.get("type") == "file" and it["name"].endswith((".yml", ".yaml")):
            f = gh.get(f"/repos/{full}/contents/{it['path']}?ref={branch}") or {}
            out[it["path"]] = base64.b64decode(f.get("content", "")).decode("utf-8", "replace")
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
    files = workflow_texts(gh, full, branch)
    template = TEMPLATE.read_text(encoding="utf-8")
    refs = [m for t in files.values() for m in CALL.findall(t)]
    for ref in refs:
        if ref != REF:
            problems.append(f"公開の検査を main の先端で呼んでいない（@{ref} → @{REF}）")
    if full == FOUNDATION:
        local = {p: t for p, t in files.items() if LOCAL_CALL.search(t)}
        if not local:
            problems.append("公開の検査の呼び口が無い（ci.yml の job public-guard が ./public-guard を呼ぶ）")
        for path, text in local.items():
            problems += [f"{path}: {d}" for d in foundation_drift(text, template)]
    elif CALLER_PATH not in files:
        problems.append(f"公開の検査の呼び口 {CALLER_PATH} が無い（public-guard/caller-template.yml をそのまま写す）")
    else:
        drift = caller_drift(files[CALLER_PATH], template)
        if drift:
            problems.append(f"呼び口 {CALLER_PATH} が雛形と違う（雛形 public-guard/caller-template.yml をそのまま写し直す）: {drift}")
    have = required_checks(gh, full, branch)
    for check in (FOUNDATION_CHECKS if full == FOUNDATION else (CHECK,)):
        if check not in have:
            problems.append(f"{branch} の守りの必須の検査に {check} が無い（Settings → Rules → Rulesets）")
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
    except (urllib.error.URLError, OSError) as e:
        print(f"✗ GitHub が読めない: {e}")
        return 2
    text = render(found, owners)
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
