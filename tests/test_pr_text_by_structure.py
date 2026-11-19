"""PR の文の守り（pr_text）は、字の在る無しでなく形（道具の呼び出しと結果の結び・走る命令の語・YAML の欄・remote の欄）で見て、
引けない時は黙って通さない、という約束を、誤りの類をわざと入れて拒む試験（PR #77 の red の所見と、同じ原因の台帳の行）。

- 物差しの跡は、物差しを回した道具の呼び出し（値の表 pr_ruler_trace の形）と tool_use の id で結ぶ結果だけを数える
  （PR 本文を読んだ結果・物差しを読んだだけの命令の結果は数えない）
- 連絡板の照らしは、連絡板の repo の正本（細目.md）が読めない・連絡板の在る無しを引けない時に止める
- git push は命令を語に分けて見る（前の代入・env・command・time・sudo・nice・xargs・bash -c・eval）
- PR の review の event（APPROVE・REQUEST_CHANGES）は本文によらず判定と見る
- 引用の中の「整地: 不要」で整地の照らしを外さない
- 公開かの見分けは workflow の注を数えず、ssh の remote も owner/repo に読む
入力は全部作り物。実の GitHub へは出ない（作り物の gh）。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from test_pr_text import (PUBLIC_WORD, _fake_gh, _fake_public_repo, cleanup_body, deny_reason, env, gh,  # noqa: F401
                          transcript_rows, verdict_comment, with_transcript, write_rows)

ROOT = Path(__file__).resolve().parent.parent
RULER = "check_all: 緑 (4 本)"
AT = "git" + "@"                                        # 公開の検査がメールの形と読まないよう、字を分けて組む
SSH_SCP = AT + "github.com:fake-owner/fake-public.git"


def _verdict(env, **log):
    _fake_gh(env)
    return deny_reason(env, with_transcript(env, gh("add_issue_comment", issue_number=1, body=verdict_comment()), **log))


# ── 物差しの跡 ──
def test_PR_本文を読んだだけの道具の結果は物差しの跡に数えない(env):
    why = _verdict(env, results=("検査: " + RULER,), tool="mcp__github__pull_request_read")
    assert "[verdict]" in why and "物差しの跡" in why


def test_本文を引く命令や物差しを読むだけの命令の結果も跡に数えない(env):
    for cmd in ("gh api repos/fake-owner/fake-private/pulls/1 --jq .body",
                "cat scripts/check_all.sh",
                "echo bash scripts/check_all.sh; gh api repos/x/y/pulls/1"):
        why = _verdict(env, results=(RULER,), command=cmd)
        assert "物差しの跡" in why, cmd


def test_物差しの結果と別の道具の結果は_tool_use_の_id_で分ける(env):
    log = Path(env["CLAUDE_PROJECT_DIR"]).parent / "t_id.jsonl"
    ruler = transcript_rows(("check_all: 赤 (1 本)",))                       # 物差しは回したが、別の行
    other = transcript_rows((RULER,), tool="mcp__github__pull_request_read")
    other[0]["message"]["content"][0]["id"] = other[1]["message"]["content"][0]["tool_use_id"] = "x0"
    write_rows(log, ruler + other)
    _fake_gh(env)
    p = dict(gh("add_issue_comment", issue_number=1, body=verdict_comment()), transcript_path=str(log))
    assert "物差しの跡" in deny_reason(env, p)


def test_前置きや_bash_c_で回した物差しは跡に数える(env):
    for cmd in ("bash scripts/check_all.sh", "env A=1 bash scripts/check_all.sh 2>&1",
                "cd /x && ./scripts/check_all.sh", "bash -c 'python3 -m pytest -q tests/'", "time pytest -q"):
        assert _verdict(env, results=("…\n" + RULER,), command=cmd) == "", cmd


def test_物差しの形は値の表で足せる(env):
    table = Path(env["CLAUDE_PROJECT_DIR"]) / "config" / "skill-values.json"
    table.parent.mkdir(parents=True)
    table.write_text(json.dumps({"guard": {"pr_ruler_trace": [{"tool": "Bash", "input": {"command": r"^cargo\s+test\b"}}]}}),
                     encoding="utf-8")
    assert _verdict(env, results=(RULER,), command="cargo test --all") == ""
    assert "物差しの跡" in _verdict(env, results=(RULER,), command="bash scripts/check_all.sh")


# ── 連絡板（引けない時は止める）──
def _guard_without(tmp_path, saimoku=None):
    """guard だけを写した plugin の置き場（core の 細目.md が無いか、saimoku の字で置く）。"""
    plugins = tmp_path / "plugins"
    shutil.copytree(ROOT / "plugins" / "guard", plugins / "guard")          # lib の symlink は中身ごと写す
    if saimoku is not None:
        (plugins / "core").mkdir()
        (plugins / "core" / "細目.md").write_text(saimoku, encoding="utf-8")
    return plugins / "guard" / "scripts" / "guard.py"


def _deny_with(env, guard_py, payload):
    p = subprocess.run([sys.executable, str(guard_py), "pre"], input=json.dumps(with_transcript(env, payload), ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    return out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""


def test_連絡板の_repo_の正本が読めない時は黙って通さない(env, tmp_path):
    _fake_gh(env)
    comment = gh("add_issue_comment", issue_number=2, body="作り物の連絡")
    why = _deny_with(env, _guard_without(tmp_path / "a"), comment)
    assert "[board]" in why and "細目.md" in why and "見つからず" in why
    why = _deny_with(env, _guard_without(tmp_path / "b", saimoku="# 作り物の細目\n連絡の決まりは無い\n"), comment)
    assert "[board]" in why and "連絡板の repo" in why


def test_連絡板の在る無しを引けないまま新しい_issue_を立てない(env):
    import re
    text = (ROOT / "plugins" / "core" / "細目.md").read_text(encoding="utf-8")
    owner, repo = re.search(r"またぐ連絡[^\n]*?`([^`/]+)/([^`]+)`", text).groups()
    _fake_gh(env, fail=True)
    why = deny_reason(env, gh("issue_write", owner=owner, repo=repo, method="create", title="作り物", body="作り物"))
    assert "[board]" in why and "引けない" in why


# ── git push を語で見る ──
def _public_repo_with_commit(proj):
    _fake_public_repo(proj, PUBLIC_WORD)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=作り物", "-c", "user.email=noreply@example.com",
                    "commit", "-qm", "%s の直し" % PUBLIC_WORD], check=True)


def test_前置きや_bash_c_の付いた_git_push_も照らす(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_gh(env, private={"fake-public": "false"})
    _public_repo_with_commit(proj)
    for cmd in ("env A=1 git push origin b", 'bash -c "git push origin b"', "command git push", "time git push",
                "sudo git push", "nice -n 5 git push", "A=1 git push", "echo b | xargs git push origin",
                "bash -lc 'cd %s; git push'" % proj, "eval git push", "timeout 60 git push", "(git push)",
                "/usr/bin/git -c a.b=c push", "git -C %s push" % proj):
        bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(proj), "tool_input": {"command": cmd}}
        why = deny_reason(env, bash)
        assert "[public]" in why and "commit の説明と名義" in why, cmd
    for cmd in ("echo git push", "git log --grep push", 'git commit -m "push it"', "git status"):
        bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(proj), "tool_input": {"command": cmd}}
        assert deny_reason(env, bash) == "", cmd


# ── PR の review の event ──
def test_APPROVE_の_review_は本文によらず判定の形を照らす(env):
    _fake_gh(env)
    for body in ("", "LGTM"):
        why = deny_reason(env, gh("pull_request_review_write", pullNumber=1, method="create", event="APPROVE", body=body))
        assert "[verdict]" in why, body
    assert deny_reason(env, gh("pull_request_review_write", pullNumber=1, method="create", event="COMMENT",
                               body="作り物の問い")) == ""


# ── 引用の中の「整地: 不要」──
def test_引用の中の整地不要で整地の照らしを外さない(env):
    _fake_gh(env, files=("README.md",))
    body = "## 何をどう変えたか\n作り物。\n\n> 整地: 不要（誤字だけ）\n"
    why = deny_reason(env, gh("create_pull_request", title="作り物", head="b", base="main", body=body))
    assert "[cleanup]" in why and "整地の見出しが無い" in why


# ── 公開かの見分け ──
def test_workflow_の注の_public_guard_は公開の印に数えない(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    wf = proj / ".github" / "workflows" / "public-guard.yml"
    wf.write_text("jobs:\n  check:\n    steps:\n      # - uses: fake/agent-foundation-public/public-guard@v0.0.1\n"
                  "      - run: echo 作り物\n", encoding="utf-8")
    _fake_gh(env, fail=True)                          # GitHub から公開かを引けない
    why = deny_reason(env, gh("add_issue_comment", repo="fake-public", issue_number=1, body="%s の話" % PUBLIC_WORD))
    assert "コメント: 置かない語" not in why and "公開かを GitHub から引けず" in why      # 注の印で公開と決めて照らさない


def test_ssh_の_remote_も窓の_repo_の取り出しと見る(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    subprocess.run(["git", "-C", str(proj), "remote", "set-url", "origin", SSH_SCP],
                   check=True)
    _fake_gh(env, fail=True)                          # 引けない時は取り出しの workflow で見分ける
    for k in [k for k in env if k.startswith("GIT_CONFIG_")]:
        del env[k]                                    # 手元の url.insteadOf で https に読み替えさせない
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    why = deny_reason(env, gh("add_issue_comment", repo="fake-public", issue_number=1, body="%s の話" % PUBLIC_WORD))
    assert "[public]" in why and "コメント: 置かない語" in why


def test_remote_の_URL_は形によらず_owner_repo_に読む():
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    import pr_text  # noqa: E402
    for url in (SSH_SCP, "ssh://" + AT + "github.com/fake-owner/fake-public.git",
                "https://github.com/fake-owner/fake-public.git", "https://github.com/fake-owner/fake-public/\n"):
        assert pr_text.remote_repo(url) == "fake-owner/fake-public", url
    assert pr_text.remote_repo("https://gitlab.example.com/fake-owner/fake-public.git") == ""
