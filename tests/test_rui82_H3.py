"""字の並びで照らしていた守り（pr_text・verdict_form・pr_shape・seal）を、構造と実物で読む形へ直した事の注入の試験（類 82・H3）。

どの試験も、台帳の行の「起きた問題」の形をわざと入れて、守りが拒む（拾う）かを見る。実の GitHub へは出ない（作り物の gh）。
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard" / "scripts" / "guard.py"
CHECKER = ROOT / "plugins" / "checker" / "scripts"
PR_SHAPE = ROOT / "scripts" / "pr_shape.py"
SEAL = ROOT / "plugins" / "dev-flow" / "skills" / "spec-doc" / "seal.py"

WRITER = "session_01AAAAAAAAAAAAAAAAAAAAAAAA"
REVIEWER = "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
STRANGER = "session_01CCCCCCCCCCCCCCCCCCCCCCCC"
HEAD_SHA = "0123456789ab" + "c" * 28
MAIL = "someone" + "@" + "gmail.com"

FAKE_GH = r'''#!/usr/bin/env python3
import json, sys
cfg = json.load(open(%r, encoding="utf-8"))
a = sys.argv[1:]
if a[:2] == ["pr", "view"]:
    print(cfg.get("number", "")); sys.exit(0 if cfg.get("number") else 1)
if a[:1] != ["api"]:
    sys.exit(1)
ep = a[1]
parts = ep.split("/")
if len(parts) == 3:                                   # repos/o/r の公開の別
    v = cfg.get("vis", {}).get(parts[1] + "/" + parts[2])
    if v is None:
        sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
    print(v); sys.exit(0)
if parts[-1] == "commits":
    print("\n".join(cfg.get("commits", []))); sys.exit(0)
if "pulls" in parts:
    sys.stdout.write(cfg.get("head", "") + "\n" + cfg.get("body", "")); sys.exit(0)
sys.exit(1)
'''


@pytest.fixture
def env(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", "https://github.com/fake-owner/fake-private.git"], check=True)
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR", "CLAUDE_CODE_REMOTE_SESSION_ID"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp_path / "scratch")})
    return e


def fake_gh(env, **cfg):
    """作り物の gh（公開の別・PR の先端と本文・commit の説明を cfg から返す）を PATH の頭に置く。"""
    base = Path(env["CLAUDE_PROJECT_DIR"]).parent
    conf = base / "gh.json"
    full = {"head": HEAD_SHA, "body": "書いた窓: %s\n" % WRITER, "commits": [],
            "vis": {"fake-owner/fake-private": "private"}}
    full.update(cfg)
    conf.write_text(json.dumps(full), encoding="utf-8")
    bindir = base / "fakebin"
    bindir.mkdir(exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(FAKE_GH % str(conf), encoding="utf-8")
    gh.chmod(0o755)
    if not env.get("PATH", "").startswith(str(bindir)):
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    return env


def deny(env, payload):
    payload.setdefault("session_id", "s1")
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


def mcp(tool, repo="fake-private", **ti):
    return {"tool_name": "mcp__github__" + tool, "tool_input": {"owner": "fake-owner", "repo": repo, **ti}}


def bash(env, command):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": env["CLAUDE_PROJECT_DIR"]}


def verdict(reviewer=REVIEWER, judged="green"):
    sys.path.insert(0, str(CHECKER))
    import verdict_form  # noqa: E402
    rows = ["- %d %s: %s" % (no, name, "書いた窓 %s ≠ この窓" % WRITER if no == 3 else "pass")
            for no, name in sorted(verdict_form.load_points().items())]
    cards, steps = verdict_form.load_cards()
    later = [c for c in cards if c != verdict_form.STOP_CARD][0]
    return "\n".join(["レビューした窓: %s 判定: %s" % (reviewer, judged), "見た先端: " + HEAD_SHA[:12], "", "## verdict", judged,
                      "", "## 点"] + rows + ["", "## 所見", "- [%s｜%s] 作り物の残り" % (later, steps[0])]) + "\n"


FULL_CLEANUP = ("親窓: %s\n書いた窓: %s\njob: 20261119-fake\n検査: check_all: 緑 (1 本)\n\n## 何をどう変えたか\n作り物。\n\n"
                "## 整地（根治の 4 段）\n\n## 1. 問題\n作り物の問題。\n\n## 2. 原因と同じ原因の他の問題\n**原因**: 作り物。\n\n"
                "## 3. 解決（足す物・畳む物・注入の試験と残る穴）\n**足す物**: 作り物。\n\n## 4. 未来\n作り物の未来。\n" % (STRANGER, WRITER))


# ── 行 …ab-b4a5-cd1e507613d7: 整地の 4 つの見出しが在るかだけを見る ──
@pytest.mark.parametrize("empty", ["", "〔作り物の置き場の字〕", "- \n-", "**原因**:\n**同じ原因の他の問題**:\n- ", "<中身>", "TBD"])
def test_整地の見出しを並べて中身を空にすると止める(env, empty):
    fake_gh(env)
    body = FULL_CLEANUP.replace("作り物の問題。", empty)
    why = deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=body))
    assert "[cleanup]" in why and "1. 問題" in why and "中身が空" in why, (empty, why)
    assert deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=FULL_CLEANUP)) == ""


# ── 行 …14-b7b8-d64c5d549042: 「整地: 不要（-）」で括弧の中が何でも外れる ──
@pytest.mark.parametrize("why_text", ["-", "…", "〔訳〕", "<なぜ>", " ", "TBD"])
def test_整地不要の訳が空と同じなら外さない(env, why_text):
    fake_gh(env)
    body = "## 何をどう変えたか\n誤字。\n\n整地: 不要（%s）\n" % why_text
    assert "[cleanup]" in deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=body)), why_text
    ok = "## 何をどう変えたか\n誤字。\n\n整地: 不要（振る舞いを変えない誤字の直しだけ）\n"
    assert deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=ok)) == ""


# ── 行 …f3-b3d6-fd93ddc6a6a6: HEAD_FIELD が照らさない行を頭の語で決める ──
def test_頭の語の欄でも本文の途中や値が_id_だけでない行の窓の_id_は数える(env):
    fake_gh(env)
    mid = FULL_CLEANUP + "\n検査: %s を見た\n" % STRANGER
    assert "[words]" in deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=mid))
    head = FULL_CLEANUP.replace("検査: check_all: 緑 (1 本)", "検査: %s を見た" % STRANGER)
    assert "[words]" in deny(env, mcp("create_pull_request", title="作り物", head="b", base="main", body=head))


# ── 行 …13-a0ea-dc0c5d088cf5: 窓の id の照らしを PR の題・本文に限る ──
@pytest.mark.parametrize("payload", [
    mcp("issue_write", method="create", title="作り物", body="直す窓 %s" % STRANGER),
    mcp("add_issue_comment", issue_number=1, body="直す窓 %s に頼んだ" % STRANGER),
    mcp("push_files", branch="b", files=[], message="作り物 %s の続き" % STRANGER),
    mcp("merge_pull_request", pullNumber=1, commit_title="作り物", commit_message="直す窓 %s" % STRANGER),
], ids=["issue の本文", "PR のコメント", "commit の説明", "merge の説明"])
def test_窓の_id_は_GitHub_へ出す全ての文で照らす(env, payload):
    fake_gh(env)
    assert "[words]" in deny(env, payload)


def test_判定の形が_id_を置く欄と引いた判定の名乗りは数えない(env):
    fake_gh(env)
    assert deny(env, mcp("add_issue_comment", issue_number=1, body=verdict())) == ""
    quoted = "> レビューした窓: %s 判定: red\n\n直しました。見直しを頼みます。" % REVIEWER
    assert deny(env, mcp("add_issue_comment", issue_number=1, body=quoted)) == ""
    smuggled = verdict().replace("作り物の残り", "直す窓 %s" % STRANGER)
    assert "[words]" in deny(env, mcp("add_issue_comment", issue_number=1, body=smuggled))


# ── 行 …30-9db0-c163b62da661: 判定のコメントを決まった字で見分ける ──
@pytest.mark.parametrize("body", ["**Verdict: green**\n作り物の確かめは済みました。", "## 判定\n\n__判定__：ｇｒｅｅｎ\n",
                                  "見ました。\n\n**判定: red**\n"])
def test_字を寄せると判定の形の行になるコメントは判定として照らす(env, body):
    fake_gh(env)
    why = deny(env, mcp("add_issue_comment", issue_number=1, body=body))
    assert "[verdict]" in why, body


def test_GitHub_のレビューの承認と変更の要求は本文が何でも判定として照らす(env):
    fake_gh(env)
    assert "[verdict]" in deny(env, mcp("pull_request_review_write", pullNumber=1, method="create", event="APPROVE",
                                        body="LGTM"))
    assert "[verdict]" in deny(env, mcp("pull_request_review_write", pullNumber=1, method="create",
                                        event="REQUEST_CHANGES", body="直してください"))
    assert deny(env, mcp("pull_request_review_write", pullNumber=1, method="create", event="APPROVE", body=verdict())) == ""
    assert "[verdict]" in deny(env, bash(env, "gh pr review 1 --approve -b LGTM"))
    assert deny(env, bash(env, "gh pr review 1 --comment -b '作り物の確かめを足しました'")) == ""


# ── 行 …ba-08f3-…（WRITER_LINE・verdict_form が別の目を本文の字で見る）──
def test_書いた窓が別の字の_id_を名乗っても判定を出す窓の実物で止める(env):
    fake_gh(env)
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + WRITER.split("_", 1)[1]       # 判定を出すのは書いた窓
    why = deny(env, mcp("add_issue_comment", issue_number=1, body=verdict(reviewer=REVIEWER)))
    assert "[verdict]" in why and "判定を出す窓" in why and "名乗り" in why
    why = deny(env, mcp("add_issue_comment", issue_number=1, body=verdict(reviewer=WRITER)))
    assert "[verdict]" in why and "別の目でない" in why
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + REVIEWER.split("_", 1)[1]     # 別の窓が出す
    assert deny(env, mcp("add_issue_comment", issue_number=1, body=verdict(reviewer=REVIEWER))) == ""


def test_PR_本文の書いた窓を偽っても_commit_の窓と出す窓が同じなら止める(env):
    fake_gh(env, body="書いた窓: %s\n" % STRANGER,
            commits=["作り物の直し\n\nClaude-Session: https://claude.ai/code/%s" % REVIEWER])
    env["CLAUDE_CODE_REMOTE_SESSION_ID"] = "cse_" + REVIEWER.split("_", 1)[1]
    why = deny(env, mcp("add_issue_comment", issue_number=1, body=verdict(reviewer=REVIEWER).replace(WRITER, STRANGER)))
    assert "[verdict]" in why and "commit を書いた窓" in why


def test_verdict_form_は出す窓を渡すと名乗りの字でなく出す窓で別の目を見る():
    sys.path.insert(0, str(CHECKER))
    import verdict_form  # noqa: E402
    text = verdict(reviewer=REVIEWER)
    assert verdict_form.check(text, writer=WRITER, head=HEAD_SHA) == []
    errs = verdict_form.check(text, writer=WRITER, head=HEAD_SHA, poster=WRITER)
    assert any("名乗り" in e for e in errs) and any("別の目でない" in e for e in errs)
    assert any("commit を書いた窓" in e for e in verdict_form.check(text, writer=STRANGER, head=HEAD_SHA, poster=REVIEWER,
                                                                  others=[REVIEWER]))
    assert verdict_form.form_id_lines(text) == {0, text.splitlines().index("- 3 %s: 書いた窓 %s ≠ この窓" % (
        verdict_form.load_points()[3], WRITER))}


# ── 行 …a4-99d2-f8888a3839ce: 公開の repo かを workflow の字と取り出しの origin で見る ──
def test_窓の取り出しと違う公開の_repo_も_GitHub_の公開の別で照らす(env):
    fake_gh(env, vis={"fake-owner/far-public": "public", "fake-owner/fake-private": "private"})
    why = deny(env, mcp("add_issue_comment", repo="far-public", issue_number=1, body="連絡は %s へ" % MAIL))
    assert "[public]" in why and "メールアドレス" in why
    assert deny(env, mcp("add_issue_comment", repo="far-private", issue_number=1, body="連絡は %s へ" % MAIL)) == ""
    assert deny(env, mcp("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL)) == ""


# ── 行 …1a-be14-cc1dd81639cb: GitHub へ出す道を MCP の道具の名で列挙する ──
def test_Bash_の_gh_と_git_commit_も同じ照らしを当てる(env, tmp_path):
    fake_gh(env)
    assert "[cleanup]" in deny(env, bash(env, 'gh pr create --title 作り物 --body "## 何をどう変えたか\n作り物。"'))
    assert deny(env, bash(env, "gh pr create --title 作り物 --body %s" % shlex.quote(FULL_CLEANUP))) == ""
    assert "[words]" in deny(env, bash(env, "gh pr comment 1 --body '直す窓 %s'" % STRANGER))
    assert "[words]" in deny(env, bash(env, "gh issue create -t 作り物 -b'直す窓 %s'" % STRANGER))
    assert "[words]" in deny(env, bash(env, "gh api repos/{owner}/{repo}/issues/1/comments -f body='直す窓 %s'" % STRANGER))
    assert "[words]" in deny(env, bash(env, "cd . && git commit -am '作り物 %s の続き'" % STRANGER))
    assert "[words]" in deny(env, bash(env, "bash -c \"gh pr comment 1 -b '直す窓 %s'\"" % STRANGER))
    assert "[verdict]" in deny(env, bash(env, "gh pr comment 1 --body '**Verdict: green**'"))
    body = tmp_path / "本文.md"
    body.write_text("直す窓 %s\n" % STRANGER, encoding="utf-8")
    assert "[words]" in deny(env, bash(env, "gh pr comment 1 --body-file %s" % body))
    assert "[words]" in deny(env, bash(env, "gh pr comment 1 -F - <<'EOF'\n直す窓 %s\nEOF" % STRANGER))
    doc = 'git commit -m "$(cat <<\'EOF\'\n作り物の直し\n\n直す窓 %s\nEOF\n)"' % STRANGER
    assert "[words]" in deny(env, bash(env, doc))
    assert deny(env, bash(env, doc.replace("直す窓 " + STRANGER, "作り物"))) == ""


@pytest.mark.parametrize("command", ['gh pr comment 1 --body "$BODY"', "gh pr comment 1 -b \"$(cat body.md)\"",
                                     "gh pr create --fill", "gh pr comment 1 --body-file 無い.md",
                                     "cat body.md | gh pr comment 1 -F -", 'git commit -m "$MSG"'])
def test_Bash_で読めない本文は出す前に止める(env, command):
    fake_gh(env)
    assert "[unread]" in deny(env, bash(env, command)), command


@pytest.mark.parametrize("command", ["gh pr view 1", "gh pr list", "git status", "git commit --amend --no-edit",
                                     "gh api repos/{owner}/{repo}/pulls/1", "ls -la", "gh pr edit 1 --add-label 作り物"])
def test_Bash_の文を出さない命令は止めない(env, command):
    fake_gh(env)
    assert deny(env, bash(env, command)) == "", command


# ── 行 …17-…（pr_shape が試験の file を ^tests/…test_*.py の形で見る）／行 …85-b20d-…（枝の名の頭 claude/）──
def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    for d in ("tests", "plugins/guard/tests", "CHANGELOG.d"):
        (r / d).mkdir(parents=True)
    for f in ("tests/test_old.py", "plugins/guard/tests/test_x.py", "tests/x_test.py", "tests/check_y.py"):
        (r / f).write_text("def test_a():\n    assert 1\n", encoding="utf-8")
    _git(r, "init", "-q", "-b", "main")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "元")
    _git(r, "checkout", "-qb", "claude/20261119-sakumono")
    return r


def shape(repo, branch="claude/20261119-sakumono", *extra):
    return subprocess.run([sys.executable, "-B", str(PR_SHAPE), "--branch", branch, "--base", "main", "--repo", str(repo), *extra],
                          capture_output=True, text=True)


def _append(repo, rel):
    with (repo / rel).open("a", encoding="utf-8") as f:
        f.write("\n\ndef test_tail():\n    assert 1\n")


@pytest.mark.parametrize("rel", ["plugins/guard/tests/test_x.py", "tests/x_test.py"])
def test_pytest_が集める名の試験の_file_はどの置き場でも末尾の追記を止める(repo, rel):
    _append(repo, rel)
    res = shape(repo)
    assert res.returncode == 1 and rel in res.stdout, res.stdout


def test_試験の_file_の名の形は_repo_の_pytest_の設定から読む(repo):
    _append(repo, "tests/check_y.py")
    assert shape(repo).returncode == 0                                   # 既定の形では集めない名
    (repo / "pytest.ini").write_text("[pytest]\npython_files = check_*.py test_*.py\n", encoding="utf-8")
    res = shape(repo)
    assert res.returncode == 1 and "tests/check_y.py" in res.stdout, res.stdout


def test_枝の名が_claude_で始まらなくても_PR_の本文の書いた窓で_AI_の_PR_と読む(repo, tmp_path):
    _append(repo, "tests/test_old.py")
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps({"pull_request": {"body": "親窓: x\n書いた窓: %s\njob: y\n\n## 何をどう変えたか\n" % WRITER,
                                               "user": {"login": "作り物"}}}), encoding="utf-8")
    res = shape(repo, "fix/sakumono", "--event", str(ev))
    assert res.returncode == 1 and "claude/<YYYYMMDD>-<話題>" in res.stdout, res.stdout
    ev.write_text(json.dumps({"pull_request": {"body": "画面で直した誤字\n\n書いた窓: は本文の途中", "user": {"login": "作り物"}}}),
                  encoding="utf-8")
    res = shape(repo, "patch-1", "--event", str(ev))
    assert res.returncode == 0 and "照らしていない" in res.stdout
    assert shape(repo, "fix/sakumono", "--ai").returncode == 1                       # 手元で AI の窓が回す
    assert shape(repo, "fix/sakumono").returncode == 0
    ev.write_text("{壊れた", encoding="utf-8")
    assert shape(repo, "fix/sakumono", "--event", str(ev)).returncode == 2


# ── 行 …1d-e2c3e6c975cc: seal の未決の印を語の列挙で見る ──
SEAL_HEAD = "# 15 台帳\n\n## §6 決定照合\n\n"


@pytest.mark.parametrize("text", [
    "| 決定 | 扱い |\n|---|---|\n| 作り物の決定 A | 直した（理由: 未決） |\n",
    "| 決定 | 扱い |\n|---|---|\n| 作り物の決定 A | 確認待ち |\n",
    "| 決定 | 扱い |\n|---|---|\n| 作り物の決定 A | 直した（理由: 確認待ち） |\n",
    "- 作り物の決定 A: ぶつかる → 関係なし（根拠: 先方の返事待ち）\n",
    "- 作り物の決定 A: ぶつかる → 保留中\n",
])
def test_決まった値の集合の外の扱いは未決と数え_seal_を通さない(tmp_path, text):
    spec = tmp_path / "設計書"
    spec.mkdir()
    (spec / "15_台帳.md").write_text(SEAL_HEAD + text, encoding="utf-8")
    vals = tmp_path / "values.json"
    vals.write_text(json.dumps({"dev-flow": {"spec-doc": {}}}), encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(SEAL), str(spec), "--match-only", "--values", str(vals)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert res.returncode == 1 and "扱いが無い" in res.stderr, (text, res.stderr)
    ok = "| 決定 | 理由 | 扱い |\n|---|---|---|\n| 作り物の決定 A | 未決の文が理由の欄に在っても値は値 | 直した |\n" \
         "| 作り物の決定 B | 作り物 | 覆す＝墓標へ |\n| 作り物の決定 C | 作り物 | 覆す=墓標へ |\n"
    (spec / "15_台帳.md").write_text(SEAL_HEAD + ok, encoding="utf-8")
    res = subprocess.run([sys.executable, "-B", str(SEAL), str(spec), "--match-only", "--values", str(vals)],
                         cwd=tmp_path, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
