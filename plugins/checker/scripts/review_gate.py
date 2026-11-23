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
  それ以外の 403・必須の検査が空の repo は今までどおり通さない。どれかが外れたら「まだ」（同じ先端の判定が在れば「済み」）。
exit: 0=入ってよい / 1=まだ・済み（訳を 1 行ずつ）/ 2=読めない（入ってよいと言わない＝まだと同じに扱う）。
材料を file で受ける口は置かない（窓が書いた材料で関所を通さない）。試験は decide を直に呼ぶ。
入口は main の先端の版でしか判定しない（ensure_tip）: skill は窓が立った時の版の dir を指すので、自分の中身が
main の先端の物と違えば先端の版を取り出してそちらで回し直し、先端を取れなければ exit 2 で止まる（古い決まり・古い不具合で判定しない）。
"""
from __future__ import annotations

import argparse
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
    if required is PLAN_NONE:   # 必須の検査を持てない repo: 走った検査が全部緑
        required = []
        for name, st in states.items():
            if st not in OK:
                why.append("検査 %s が %s（必須の検査を持てない repo なので走った検査は全部緑を求める）" % (name, st))
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
        return required_contexts(_get("/repos/%s/rules/branches/%s" % (repo, branch), token))
    except urllib.error.HTTPError as e:
        if e.code == 403 and PLAN_403 in (e.read() or b"").decode("utf-8", "replace"):
            return PLAN_NONE
        raise


def read_facts(repo: str, number: int, token: str, wait=time.sleep):
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
    states = check_states(runs, statuses)
    if required is PLAN_NONE:   # 走った検査を全部照らす＝まだ check run を作っていない workflow の走りも入れる
        states.update(workflow_states(_pages("/repos/%s/actions/runs?head_sha=%s" % (repo, head), token, key="workflow_runs")))
    return pr, required, states, comments


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
        what = ("必須の検査 %s" % "・".join(required)) if required is not PLAN_NONE else \
            ("走った検査 %s" % ("・".join(states) or "なし（必須の検査を持てない repo）"))
        print("review_gate: 入ってよい — #%d@%s %s が緑・mergeable_state clean・この先端の判定はまだ無い" % (a.pr, head, what))
        return 0
    print("review_gate: %s — #%d@%s（判定に入らない。書いた窓へ「%s」と訳だけを返す）" % (kind, a.pr, head, kind))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from root_cause import root_cause  # noqa: E402  根治の 1 文の 1 本の口＝skill-values/root_cause.py の root_cause（plugin の lib/ の symlink）
    print(root_cause("レビューは中身だけを 1 回見る", cause="検査の赤・衝突の", shortcut="書いた窓が訳を 1 つずつ潰す") + "。直してからレビューを頼む")
    return 1


MARKET = "agent-foundation"     # 土台の marketplace の取り出し（~/.claude/plugins/marketplaces/<MARKET>）
TIP_ENV = "AF_REVIEW_GATE_TIP"  # 先端の版へ回し直した印（回し直した先でまだ違えば止まる＝回り続けない）
ME_IN_REPO = "plugins/checker/scripts/review_gate.py"


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
