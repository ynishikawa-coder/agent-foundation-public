"""守りの hook の pr_text（GitHub へ出す前の PR の題・本文・コメントを照らす）が約束どおり効くかを見る。

判定の形・整地の欄・窓の id・公開の repo に置かない物を、作り物の入力で入口（guard.py pre）から当てる。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard" / "scripts" / "guard.py"


@pytest.fixture
def env(tmp_path):
    """試験ごとに一時の箱・台帳の置き場・repo の根を分ける（実の印を汚さない）。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1",
              "TMPDIR": str(tmp_path / "scratch")})
    return e


def deny_reason(env, payload):
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


WRITER = "session_01AAAAAAAAAAAAAAAAAAAAAAAA"
REVIEWER = "session_01BBBBBBBBBBBBBBBBBBBBBBBB"
STRANGER = "session_01CCCCCCCCCCCCCCCCCCCCCCCC"


def gh(tool, owner="fake-owner", repo="fake-private", **ti):
    return {"tool_name": "mcp__github__" + tool, "session_id": "s1",
            "tool_input": {"owner": owner, "repo": repo, **ti}}


FAKE_HEAD = "0123456789ab" + "c" * 28


def _fake_gh(env, head=FAKE_HEAD, writer=WRITER, fail=False, commits=None, total=None, comments=(), visibility="private"):
    """作り物の gh を PATH の頭に置く。実の GitHub へは出ない。
    PR を引く呼び出しには先端と本文の `書いた窓:`（写し）を、commit を引く呼び出しには各 commit の説明（`Claude-Session:` の
    記録。既定は書いた窓の 1 本・1 本ごとに JSON の 1 行）を返す。commits の None の要素は記録の無い commit。
    total は PR の commit の数（既定は返す commit の数。GitHub が commit の一覧を 250 本で切る時の作り物に、返す数より大きくする）。
    repo の見え方を引く呼び出しには visibility を返す（None なら引けない＝exit 1）。"""
    bindir = Path(env["CLAUDE_PROJECT_DIR"]).parent / "fakebin"
    bindir.mkdir(exist_ok=True)
    gh_path = bindir / "gh"
    body = "書いた窓: %s\\n" % writer if writer else "作り物の本文\\n"
    commits = [WRITER] if commits is None else commits
    msgs = "".join(json.dumps("作り物の commit\n\n" + ("Claude-Session: https://claude.ai/code/%s\n" % c if c else ""),
                              ensure_ascii=False).replace("\\", "\\\\") + "\\n" for c in commits)
    total = len(commits) if total is None else total
    # PR のコメント（初めの判定の決まりの版を読む）: 本文 1 つごとに JSON の 1 行。既定は判定の無い PR
    comments = "".join(json.dumps(c, ensure_ascii=False).replace("\\", "\\\\") + "\\n" for c in comments)
    gh_path.write_text("#!/bin/sh\n" + ("echo 'not found' >&2; exit 1\n" if fail else
                       'case "$*" in %s *"/commits"*) printf \'%s\' ;; *"/issues/"*"/comments"*) printf \'%s\' ;; *".head.sha"*) echo \'%s\' ;; *) printf \'%%s\\n%%s\\n%%s\' \'%s\' \'%s\' \'%s\' ;; esac\n'
                       % ('*".visibility"*) ' + ("echo 'not found' >&2; exit 1 ;;" if visibility is None else
                                                 "echo %s ;;" % visibility), msgs, comments, head, head, total, body)), encoding="utf-8")
    gh_path.chmod(0o755)
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    return env


def _fake_public_repo(proj, deny_word, url="https://github.com/fake-owner/fake-public.git"):
    """作り物の公開の repo の取り出し（origin が owner/repo・workflow が action public-guard を呼ぶ）。"""
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", url], check=True)
    wf = proj / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "public-guard.yml").write_text(
        "on: [pull_request]\njobs:\n  public-guard:\n    steps:\n"
        "      - uses: ynishikawa-coder/agent-foundation-public/public-guard@main\n"
        "        with:\n          deny-words-file: data/deny.txt\n", encoding="utf-8")
    (proj / "data").mkdir()
    (proj / "data" / "deny.txt").write_text(deny_word + "\n", encoding="utf-8")


PUBLIC_WORD = "作り物" + "ノ禁句"
MAIL = "someone" + "@" + "gmail.com"


def test_pr_text_公開の_repo_へは置かない物の在る文を出す前に止める(env, tmp_path):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    pub = dict(repo="fake-public")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, **pub))
    assert "[public]" in why and "コメント: メールアドレス" in why and MAIL not in why.split("直し方")[0].replace("コメント: メールアドレス", "")
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, title="%s の直し" % PUBLIC_WORD, **pub))
    assert "[public]" in why and "PR の題: 置かない語" in why and PUBLIC_WORD not in why
    why = deny_reason(env, gh("issue_write", method="create", title="作り物", body="連絡は %s へ" % MAIL, **pub))
    assert "issue の本文: メールアドレス" in why
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめを足しました", **pub)) == ""
    why = deny_reason(env, gh("merge_pull_request", pullNumber=1, merge_method="squash",
                              commit_title="作り物", commit_message="連絡は %s へ" % MAIL, **pub))
    assert "commit の説明: メールアドレス" in why
    why = deny_reason(env, gh("push_files", branch="b", files=[], message="%s の直し" % PUBLIC_WORD, **pub))
    assert "commit の説明: 置かない語" in why
    assert deny_reason(env, gh("push_files", branch="b", files=[], message="作り物の直し", **pub)) == ""
    # 同じ文でも公開でない repo（取り出しが別の repo・GitHub の記録が private）は照らさない
    _fake_gh(env)
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL)) == ""


def test_pr_text_公開の_repo_で検査が見つからない時も止める(env, tmp_path):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    env["AF_PUBLIC_GUARD"] = str(tmp_path / "無い.py")
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[public]" in why and "見つからず" in why
    del env["AF_PUBLIC_GUARD"]
    (Path(env["CLAUDE_PROJECT_DIR"]) / "data" / "deny.txt").unlink()
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[public]" in why and "置かない語の表" in why and "無く" in why


def test_pr_text_手元に取り出しの無い公開の_repo_は値の表で足せる(env, tmp_path):
    table = tmp_path / "values.json"
    env["SKILL_VALUES"] = str(table)
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="far-public")
    _fake_gh(env)                                                  # GitHub の記録は private（記録が違っても値の表で足せる）
    assert deny_reason(env, p) == ""
    table.write_text(json.dumps({"guard": {"public_repos_extra": ["^fake-owner/far-public$"]}}), encoding="utf-8")
    assert "[public]" in deny_reason(env, p)


def test_pr_text_道具の名は_MCP_の_server_の名を問わず末尾で見る(env):
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    p = gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="fake-public")
    p["tool_name"] = "mcp__0a1b2c3d__add_issue_comment"
    assert "[public]" in deny_reason(env, p)
    p["tool_name"] = "mcp__github__add_issue_comment_reaction"
    assert deny_reason(env, p) == ""


def test_pr_text_照らしの途中で壊れたら黙って通さず止める(env, tmp_path):
    """一時の置き場に書けない等で照らしが壊れても、見る道具なら止める（入口が例外を通す側に倒すため）。"""
    blocker = tmp_path / "置き場でない"
    blocker.write_text("file なので dir を作れない", encoding="utf-8")
    env["AF_GUARD_TMP"] = str(blocker)
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="作り物の確かめ", repo="fake-public"))
    assert "[broken]" in why and "照らせない文は出さない" in why
    assert deny_reason(env, gh("create_branch", branch="b", from_branch="main")) == ""
