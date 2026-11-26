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
  同じ先端の判定がまだ無い。
  無料のプランの非公開 repo（GitHub が必須の検査を作らせず rules を 403「Upgrade to GitHub Pro」で返す）だけは、必須の検査の代わりに
  先端で走った検査が全部終わって緑（1 つも無ければ mergeable_state clean だけ）で通す（オーナーの答え 2026-11-22）。
  走った検査には、先端の workflow の走り（actions/runs?head_sha=）も入れる（遅い job の check run がまだ作られていない間に、
  先に終わった速い検査だけで通らないように）。
  それ以外の 403 は通さない。必須の検査が空の repo も既定では通さない。
  CI を合流後に回すと決めた repo のレビューに限り --ci-after-merge を使う。GitHub が返した必須の検査が空の時だけ
  走った検査を確認する。これはレビューを始める条件であり、合流の許可や検査が緑だった証拠ではない。どれかが外れたら「まだ」（同じレビュー対象の判定が在れば「済み」）。
exit: 0=入ってよい / 1=まだ・済み（訳を 1 行ずつ）/ 2=読めない（入ってよいと言わない＝まだと同じに扱う）。
材料を file で受ける口は置かない（窓が書いた材料で関所を通さない）。試験は decide を直に呼ぶ。
入口は main の先端の版でしか判定しない（ensure_tip）: skill は窓が立った時の版の dir を指すので、自分の中身が
main の先端の物と違えば先端の版を取り出してそちらで回し直し、先端を取れなければ exit 2 で止まる（古い決まり・古い不具合で判定しない）。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
OK = {"success", "neutral", "skipped"}
VERDICT = re.compile(r"^\s*レビューした窓\s*[:：]\s*(session_[A-Za-z0-9]+)\s+判定\s*[:：]\s*(green|red)\b", re.M)
SEEN = re.compile(r"^\s*見た先端\s*[:：]\s*([0-9a-f]{12})\s*$", re.M)
PLAN_NONE = None    # 無料のプランで必須の検査を持てない repo（rules が 403「Upgrade to GitHub Pro」）
PLAN_403 = "Upgrade to GitHub Pro"
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


def check_states(runs: list, statuses: list, wruns: list | None = None, pr: int | None = None) -> dict[str, str]:
    """{検査の名: 状態}。check run は終わっていれば conclusion・まだなら status。
    check run は (名, app, 束ね先) で束ね、その中の新しい 1 本を取る。束ね先は、check_suite が同じ先端の workflow の走り
    （wruns）のどれかなら (workflow, event)＝同じ workflow を同じ event で走らせ直した新しい suite が古い suite を上書きする
    （PR の本文を直した edited の走り直しの緑が、本文を直す前の赤を消す）。それ以外は check_suite（別の app・別の
    workflow の同名の run は別の検査として数え、どれかが緑でない・終わっていなければ、その名の状態は緑でない方にする。
    名だけで束ねると、別の suite の赤が同じ名の新しい緑で隠れ、関所が通った）。走り直しが飛ばした（skipped・neutral）
    run は前の赤を消さない（飛ばした job は照らしていない）。pr を渡すと、別の PR の走り（同じ先端を持つ base の違う PR）は
    束ねず別に数える。"""
    suite_of: dict = {}
    for w in wruns or []:
        others = [p.get("number") for p in (w.get("pull_requests") or [])]
        if pr is not None and others and pr not in others:
            continue
        if w.get("check_suite_id"):
            suite_of[w["check_suite_id"]] = (("wf", w.get("workflow_id") or w.get("name") or "", w.get("event") or ""),
                                             w.get("created_at") or "")
    items = []
    for r in runs or []:
        name = r.get("name") or ""
        if not name:
            continue
        when = r.get("completed_at") or r.get("started_at") or ""
        state = r.get("conclusion") if r.get("status") == "completed" else (r.get("status") or "queued")
        app, suite = r.get("app") or {}, r.get("check_suite") or {}
        where, born = suite_of.get(suite.get("id"), (suite.get("id") or "", ""))
        # 走り直した workflow は新しい suite の物（中の run の時刻より先に suite の生まれで比べる）
        items.append(((born, when), (name, app.get("id") or app.get("slug") or "", where), state or ""))
    items.sort(key=lambda it: it[0])   # API の返す並びに頼らず古い順に畳む（新しい物が先に来ても同じ答え）
    groups: dict[tuple, str] = {}
    for _order, key, state in items:
        if key in groups and state in ("skipped", "neutral") and groups[key] not in OK:
            continue   # 飛ばした走り直しで前の赤を消さない
        groups[key] = state
    out: dict[str, str] = {}
    for (name, _app, _where), state in groups.items():
        if name not in out or (out[name] in OK and state not in OK):
            out[name] = state
    for s in statuses or []:   # commit status（古い口）。check run が無い名だけ
        name = s.get("context") or ""
        if name and name not in out:
            out[name] = s.get("state") or ""
    return out


def workflow_states(wruns: list) -> dict[str, str]:
    """{"workflow <名> (<event>)": 状態}。先端の workflow の走り。同じ (名, event) は新しい物を取る（走り直し・終わって
    いれば conclusion・まだなら status）。名が同じでも event が違う走り（pull_request と push）は別の検査として両方照らす
    （名だけで新しい物を取ると、check run を作る前に赤で終わった古い方が見えず、新しい方の緑だけで通った）。"""
    out: dict[str, tuple[str, str]] = {}
    for r in wruns or []:
        name = "workflow " + (r.get("name") or str(r.get("workflow_id") or ""))
        if r.get("event"):
            name += " (%s)" % r["event"]
        when = r.get("created_at") or ""
        state = r.get("conclusion") if r.get("status") == "completed" else (r.get("status") or "queued")
        if name not in out or when >= out[name][0]:
            out[name] = (when, state or "")
    return {k: v[1] for k, v in out.items()}


def read_verdict(body: str):
    """正式な先頭2行を読む。対象外は None、崩れた判定は (先端, None, None)。"""
    lines = body.strip().splitlines()
    if len(lines) < 2:
        return None
    seen = SEEN.match(lines[1].strip())
    if not seen:
        return None
    # 旧来の窓 ID の別表記もここで同じ窓に寄せる。
    first = re.sub(r"(?<=[:：])\s*cse_", " session_", lines[0].strip(), count=1)
    match = VERDICT.match(first)
    return (seen.group(1), *match.groups()) if match else (seen.group(1), None, None)


def verdict_for_head(body: str, head: str):
    """今の先端の判定だけを読む。対象外は None、対象なのに判定が崩れていれば ValueError。"""
    read = read_verdict(body)
    if not read or read[0] != head.lower()[:12]:
        return None
    _, session, verdict = read
    if not session:
        raise ValueError("判定の形に合わない")
    return session, verdict


def review_text_version(pr: dict) -> str | None:
    """Scalar snapshot of what point 1 reviews; no extra GitHub call."""
    if not isinstance(pr.get("title"), str) or "body" not in pr:
        return None
    data = json.dumps([pr["title"], pr["body"] or ""], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def review_results(comments, head: str, *, text_version=None, writers=(), strict=True):
    """Oldest first. Keep the last verdict per reviewer, for this code only.
    An older text green proves no current text; an older text red is still an
    open finding until that reviewer explicitly reverses it. Publishing an
    already-merged artifact checks code, not edits to the PR description.
    """
    latest = {}
    versioned = False
    for item in comments or ():
        body = item if isinstance(item, str) else (item.get("body") or "")
        try:
            result = verdict_for_head(body, head)
        except ValueError:
            if strict:
                raise
            continue
        if result is None or result[0] in writers:
            continue
        who, verdict = result
        lines = body.strip().splitlines()
        stamp = re.fullmatch(r"見た本文: ([0-9a-f]{16})", lines[2]) if len(lines) > 2 else None
        if stamp:
            versioned = True
        elif latest.get(who, (None, None))[1] is not None:
            continue  # A legacy-only note cannot reverse an already versioned verdict.
        latest[who] = (verdict, stamp[1] if stamp else None)
    # Legacy-only PRs retain their existing receipts. Once a real review on
    # this head uses the stamp, legacy greens cannot override the new scope.
    green = sorted(who for who, (v, stamp) in latest.items() if v == "green"
                   and (not text_version or stamp == text_version or not versioned))
    red = sorted(who for who, (v, _) in latest.items() if v == "red")
    current = any(stamp == text_version if text_version else True for _, stamp in latest.values())
    # An old head-only red can receive its first versioned re-review.
    if text_version and not versioned and green and not red:
        current = True
    return green, red, current


def require_green(comments, head: str, *, text_version=None, writers=()):
    green, red, _ = review_results(comments, head, text_version=text_version, writers=writers)
    if red:
        raise ValueError("窓 %s の最後の判定が red" % "・".join(red))
    if not green:
        raise ValueError(f"先端 {head.lower()[:12]} を見た今の判定: green が無い")
    return green


def decide(pr: dict, required: list[str] | None, states: dict[str, str], comments: list, *, ci_after_merge=False) -> tuple[str, list[str]]:
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
    if required is PLAN_NONE or (required == [] and ci_after_merge):
        required = []
        for name, st in states.items():
            if st not in OK:
                why.append("検査 %s が %s（走った検査は全部緑を求める）" % (name, st))
    elif not required:
        why.append("base の枝の必須の検査が読めない（必須の検査が無い所では関所を通さない）")
    for name in required:
        st = states.get(name)
        if st is None:
            why.append("必須の検査 %s が先端 %s に無い（まだ走っていない）" % (name, head[:12]))
        elif st not in OK:
            why.append("必須の検査 %s が %s（緑でない）" % (name, st))
    if why:
        return "まだ", why
    _, _, current = review_results(comments, head, text_version=review_text_version(pr), strict=False)
    if current:
        return "済み", ["先端 %s の同じレビュー対象に判定が既に在る" % head[:12]]
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
            try:
                return _get(path, "")
            except urllib.error.HTTPError:
                raise e from None     # 鍵なしの 404（非公開の repo）で、本当の訳（鍵が効かない 401）を隠さない
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


def _rules(repo: str, branch: str, token: str):
    """必須の検査の名の並び。無料のプランで rules を持てない repo は PLAN_NONE（他の 403 は読めないとして上げる）。"""
    try:
        rules = _get("/repos/%s/rules/branches/%s" % (repo, branch), token)
        if not isinstance(rules, list):
            raise ValueError("GitHub の必須検査の決まりが一覧でない")
        return required_contexts(rules)
    except urllib.error.HTTPError as e:
        if e.code == 403 and PLAN_403 in (e.read() or b"").decode("utf-8", "replace"):
            return PLAN_NONE
        raise


def read_facts(repo: str, number: int, token: str, wait=time.sleep, *, ci_after_merge=False):
    pr = _get("/repos/%s/pulls/%d" % (repo, number), token)
    for i in range(UNKNOWN_TRIES):
        if (pr.get("mergeable_state") or "unknown") != "unknown" or i == UNKNOWN_TRIES - 1:
            break
        wait(3)
        pr = _get("/repos/%s/pulls/%d" % (repo, number), token)
    head = pr["head"]["sha"]
    required = _rules(repo, pr["base"]["ref"], token)
    if required == []:   # 積んだ PR（base が別の枝）は最後に既定の枝へ入る＝既定の枝の必須の検査で見る
        default = _get("/repos/%s" % repo, token).get("default_branch") or ""
        if default and default != pr["base"]["ref"]:
            required = _rules(repo, default, token)
    runs = _pages("/repos/%s/commits/%s/check-runs" % (repo, head), token, key="check_runs")
    statuses = _pages("/repos/%s/commits/%s/statuses" % (repo, head), token)
    comments = _pages("/repos/%s/issues/%d/comments" % (repo, number), token)
    # 先端の workflow の走り: 同じ workflow を走らせ直した新しい suite で古い suite の結果を上書きするのに使う
    # 読めない鍵（Actions を読む権限が無い）の時、必須の検査が在れば走りを束ねず suite ごとに数える（赤を残す向き）。
    # PLAN_NONE は走りそのものを照らすので、読めない時は今までどおり上げる。
    all_runs = required is PLAN_NONE or (required == [] and ci_after_merge)
    try:
        wruns = _pages("/repos/%s/actions/runs?head_sha=%s" % (repo, head), token, key="workflow_runs")
    except urllib.error.HTTPError as e:
        if all_runs or e.code not in (403, 404):
            raise
        wruns = []
    states = check_states(runs, statuses, wruns, number)
    if all_runs:   # まだ check run を作っていない workflow の走りも入れる
        states.update(workflow_states(wruns))
    return pr, required, states, comments


def main(argv=None, read=read_facts) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--ci-after-merge", action="store_true",
                    help="PR では必須 CI がないと決めた repo のコードレビュー。合流の許可ではない")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", a.repo):
        print("review_gate: 読めない — --repo は owner/name の形で渡す")
        return 2
    try:
        args = (a.repo, a.pr, os.environ.get("GITHUB_TOKEN") or "")
        pr, required, states, comments = read(*args, ci_after_merge=True) if a.ci_after_merge else read(*args)
    except Exception as e:  # noqa: BLE001  読めない時は入ってよいと言わない（exit 2＝まだと同じに扱う）
        print("review_gate: 読めない — GitHub の記録を引けない（%s）。判定に入らない" % e)
        return 2
    kind, why = decide(pr, required, states, comments, ci_after_merge=a.ci_after_merge)
    head = (pr.get("head") or {}).get("sha", "")[:12]
    for w in why:
        print("✗ " + w)
    if kind == "入ってよい":
        if (stamp := review_text_version(pr)) is not None:
            print("見た本文: " + stamp)
        if a.ci_after_merge and required in ([], PLAN_NONE):
            what = "走った検査は緑" if states else "PR の検査なし（合流前の検証は別）"
            print("review_gate: 入ってよい — #%d@%s %s・mergeable_state clean・同じ対象の判定はまだ無い" % (a.pr, head, what))
            return 0
        what = ("必須の検査 %s" % "・".join(required)) if required is not PLAN_NONE else \
            ("走った検査 %s" % ("・".join(states) or "なし（必須の検査を持てない repo）"))
        print("review_gate: 入ってよい — #%d@%s %s が緑・mergeable_state clean・同じ対象の判定はまだ無い" % (a.pr, head, what))
        return 0
    print("review_gate: %s — #%d@%s（判定に入らない。書いた窓へ「%s」と訳だけを返す）" % (kind, a.pr, head, kind))
    print("直し: 書いた窓は訳を 1 つずつ潰さず、意図（レビューは中身だけを 1 回見る）とのずれから入り、検査の赤・衝突の原因を細目 §3「まず構造を疑う」で探して直してからレビューを頼む")
    return 1


MARKET = "agent-foundation"     # 土台の marketplace の取り出し（~/.claude/plugins/marketplaces/<MARKET>）
TIP_ENV = "AF_REVIEW_GATE_TIP"  # 先端の版へ回し直した印（回し直した先でまだ違えば止まる＝回り続けない）
ME_IN_REPO = "plugins/checker/scripts/review_gate.py"
TIP = ""                        # ensure_tip が読んだ main の先端（自分が先端の版の時。回し直した先は TIP_ENV で受ける）


def _git(market: Path, *args: str, binary: bool = False):
    r = subprocess.run(["git", "-C", str(market), *args], capture_output=True, timeout=60)
    if r.returncode:
        raise RuntimeError("git %s: %s" % (args[0], r.stderr.decode("utf-8", "replace").strip()[:200]))
    return r.stdout if binary else r.stdout.decode("utf-8", "replace").strip()


def ensure_tip(me: Path, argv: list[str], env=None) -> int | None:
    """自分が main の先端の版なら None（そのまま回す）。違えば先端の版へ exec し、取れなければ 2 を返す（止まる）。

    意図: レビューの関所はいつも main の先端の決まりで判定する（依頼に「先に fetch して」と書かせない）。
    課題: レビューの窓が立った時の版の関所が main の守りの決まりを読めず 403 で止まった（先端では直っていた）。
    原因: skill は窓が立った時の plugin の dir を指し、hook と違って先端の版へ寄せる入口が無かった。
    """
    env = dict(os.environ if env is None else env)
    market = Path(env.get("HOME") or Path.home()) / ".claude" / "plugins" / "marketplaces" / MARKET
    try:
        if not (market / ".git").exists():
            raise RuntimeError("土台の取り出し %s が無い" % market)
        line = _git(market, "ls-remote", "--quiet", "origin", "refs/heads/main")
        if not line:
            raise RuntimeError("origin に main が無い")
        tip = line.split()[0]
        if subprocess.run(["git", "-C", str(market), "cat-file", "-e", tip + "^{commit}"],
                          capture_output=True).returncode:
            _git(market, "fetch", "-q", "origin", "main")
        tip_blob = _git(market, "rev-parse", "%s:%s" % (tip, ME_IN_REPO))
        my_blob = _git(market, "hash-object", str(me))
        if my_blob == tip_blob:
            global TIP
            TIP = tip
            return None
        if env.get(TIP_ENV):
            raise RuntimeError("先端 %s の版へ回し直した後もまだ中身が違う" % env[TIP_ENV][:12])
        base = Path(env.get("HOME") or Path.home()) / ".claude" / "af-foundation" / "checker-tip"
        dest = base / tip[:12]
        if not ((dest / ME_IN_REPO).exists() and _git(market, "hash-object", str(dest / ME_IN_REPO)) == tip_blob):
            base.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(dir=base, prefix=".tmp-"))
            data = _git(market, "archive", "--format=tar", tip, "plugins/checker", binary=True)
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                t.extractall(tmp, filter="data")
            if _git(market, "hash-object", str(tmp / ME_IN_REPO)) != tip_blob:
                raise RuntimeError("取り出した先端の版の中身が先端と合わない")
            try:
                if dest.exists():
                    shutil.rmtree(dest)
                tmp.rename(dest)
            except OSError:   # 同時に別の窓が置いた・消せない時は今取り出した物で回す
                dest = tmp
    except Exception as e:  # noqa: BLE001  先端を取れない時は古い版で判定しない（exit 2＝まだと同じに扱う）
        print("review_gate: 読めない — main の先端の版を取れない（%s）。古い版で関所を通さない" % e)
        print("直し: 土台の取り出し（~/.claude/plugins/marketplaces/%s）が origin の main を読めるようにして回し直す" % MARKET)
        return 2
    print("review_gate: この版は main の先端 %s と違う — 先端の版で回す" % tip[:12], flush=True)
    env[TIP_ENV] = tip
    env["CLAUDE_PLUGIN_ROOT"] = str(dest / "plugins" / "checker")
    target = dest / ME_IN_REPO
    os.execve(sys.executable, [sys.executable, str(target), *argv], env)
    return 2  # 届かない


if __name__ == "__main__":
    _stop = ensure_tip(Path(__file__).resolve(), sys.argv[1:])
    if _stop is not None:
        sys.exit(_stop)
    sys.exit(main())
