#!/usr/bin/env python3
"""公開の repo の見回り。検査が付いていない・main の守りで検査が必須になっていない公開 repo を見つけて知らせる。

GitHub の設定そのものは AI には固定できない。なので「外れたら必ず見つけて知らせる」をこの 1 本で担う。
見る相手: patrol.json の owners の公開 repo（archive 済みは除く）。各 repo の既定の枝について:
  1. 呼び口: .github/workflows/ のどれかが土台の action `public-guard` を main の先端（@main）で呼んでいる
     （土台そのものは `./public-guard`）。版の印や SHA で止めた呼び口は、直した検査が届かないので外れ。
     workflow は YAML として読み（コメントは消える）、走る job の step の `uses:` の実物だけを数える
     （`if: false` の job・step と、PR にも push にも走らない workflow は数えない）。YAML として読めない workflow は外れ。
  2. 守り: 既定の枝の守り（ruleset か枝の保護）の必須の検査に、1 で呼び口を持つ job の検査の名（job の name、無ければ id）が入っている。
     同じ名を呼び口の無い job も名乗る時は、その job の緑で必須を満たせてしまうので外れ（名の字でなく、名を持つ job の中身で見る）。
     土台そのものは、使う側と同じ入れ方で plugin を入れて起動する試験（step が scripts/plugin_smoke.py を走らせる job）も。

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
ACTION = FOUNDATION + "/public-guard"
LOCAL_ACTION = "./public-guard"
# 土台は main の先端をそのまま配るので、合流の前に「使う側と同じ入れ方で入れて起動する」試験を必須にする（この道具を走らせる job）。
SMOKE_TOOL = "scripts/plugin_smoke.py"
REF = "main"
ISSUE_TITLE = "公開の検査の見回り"
# workflow が PR の検査として走る出来事（これの無い workflow の job は必須の検査を出さない）
RUN_EVENTS = {"pull_request", "pull_request_target", "push", "merge_group"}


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


def workflow_texts(gh: GitHub, full: str, branch: str) -> list[tuple[str, str]]:
    """(path, 中身) の並び。"""
    items = gh.get(f"/repos/{full}/contents/.github/workflows?ref={branch}") or []
    out = []
    for it in items if isinstance(items, list) else []:
        if it.get("type") == "file" and it["name"].endswith((".yml", ".yaml")):
            f = gh.get(f"/repos/{full}/contents/{it['path']}?ref={branch}") or {}
            out.append((it["path"], base64.b64decode(f.get("content", "")).decode("utf-8", "replace")))
    return out


def _off(cond) -> bool:
    """if: が決まって偽（false・"false"・"${{ false }}"）か。式は走るかもしれない物として数える。"""
    if cond is False:
        return True
    return isinstance(cond, str) and re.fullmatch(r"\s*(?:\$\{\{\s*)?false(?:\s*\}\})?\s*", cond) is not None


def _events(wf: dict) -> set[str]:
    on = wf.get("on", wf.get(True))      # YAML 1.1 では on: が真偽の True として読まれる
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {e for e in on if isinstance(e, str)}
    if isinstance(on, dict):
        return {e for e in on if isinstance(e, str)}
    return set()


def _uses_action(uses, local_ok: bool):
    """step の uses: が土台の action なら ref（土台の ./public-guard は "local"）、違えば None。"""
    if not isinstance(uses, str):
        return None
    u = uses.strip()
    if local_ok and u.rstrip("/") == LOCAL_ACTION:
        return "local"
    path, at, ref = u.partition("@")
    return ref if at and path.lower() == ACTION.lower() else None


def _runs_tool(run, tool: str) -> bool:
    if not isinstance(run, str):
        return False
    import shlex
    for line in run.splitlines():
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            words = line.split()
        if any(w == tool or w.endswith("/" + tool) for w in words):
            return True
    return False


def read_jobs(texts: list[tuple[str, str]], local_ok: bool):
    """workflow を YAML として読み、走る job を (検査の名, 呼んだ ref の並び, 煙の試験を走らせるか) で返す。
    読めない workflow は problems に名指しする。"""
    try:
        import yaml
    except ImportError:
        raise OSError("workflow を YAML として読む道具（PyYAML）が無い")
    jobs, problems = [], []
    for path, text in texts:
        try:
            wf = yaml.safe_load(text)
        except yaml.YAMLError:
            problems.append(f"workflow を YAML として読めない（{path}）＝呼び口を確かめられない")
            continue
        if not isinstance(wf, dict) or not isinstance(wf.get("jobs"), dict):
            continue
        runs = bool(_events(wf) & RUN_EVENTS)
        for jid, job in wf["jobs"].items():
            if not isinstance(job, dict):
                continue
            name = job.get("name") if isinstance(job.get("name"), str) else str(jid)
            live = runs and not _off(job.get("if"))
            steps = [st for st in job.get("steps") or [] if isinstance(st, dict) and not _off(st.get("if"))]
            refs = [r for st in steps for r in [_uses_action(st.get("uses"), local_ok)] if r]
            smoke = any(_runs_tool(st.get("run"), SMOKE_TOOL) for st in steps)
            jobs.append({"name": name, "live": live, "refs": refs if live else [], "smoke": smoke and live})
    return jobs, problems


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
    foundation = full.lower() == FOUNDATION.lower()
    jobs, problems = read_jobs(workflow_texts(gh, full, branch), foundation)
    callers = [j for j in jobs if j["refs"]]
    if not callers:
        problems.append("公開の検査の呼び口が無い（public-guard/caller-template.yml を .github/workflows/ へ）")
    for ref in sorted({r for j in callers for r in j["refs"]}):
        if ref not in (REF, "local"):
            problems.append(f"公開の検査を main の先端で呼んでいない（@{ref} → @{REF}）")
    have = required_checks(gh, full, branch)
    needs = [("公開の検査を呼ぶ job", lambda j: bool(j["refs"]), "public-guard")]
    if foundation:
        needs.append(("入れて起動する試験の job", lambda j: j["smoke"], "plugin-smoke"))
    for what, is_it, hint in needs:
        names = {j["name"] for j in jobs if is_it(j)}
        if not names & have:
            shown = "・".join(sorted(names)) or hint
            problems.append(f"{branch} の守りの必須の検査に{what}（{shown}）が無い（Settings → Rules → Rulesets）")
        for n in sorted(names & have):
            if any(j["name"] == n and not is_it(j) for j in jobs):
                problems.append(f"必須の検査 {n} を、{what}でない job も名乗る（その緑で必須が満ちてしまう。job の名を分ける）")
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
