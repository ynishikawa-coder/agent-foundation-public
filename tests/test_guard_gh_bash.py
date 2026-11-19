"""守りの hook の gh_bash（Bash から GitHub へ PR・issue の文を書く命令を止め、MCP の道具へ回す）が約束どおり効くかを見る。

入口（guard.py pre）から作り物の Bash の呼び出しを当てる。実の GitHub へは出ない（止まる命令は走らない・通る命令も走らせない）。
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
    proj = tmp_path / "proj"
    proj.mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1"})
    return e


def reason(env, cmd):
    payload = {"tool_name": "Bash", "session_id": "s1", "tool_input": {"command": cmd}}
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else {}
    r = out.get("permissionDecisionReason", "") if out.get("permissionDecision") == "deny" else ""
    return r if "[guard] Bash から GitHub へ" in r else ""


VERDICT = "レビューした窓: session_01BBBBBBBBBBBBBBBBBBBBBBBB 判定: green"

STOP = [
    # 判定を Bash の gh で出す（作った窓の id を環境の差し替えで名乗る形も）
    'gh pr comment 74 --body "%s"' % VERDICT,
    'CLAUDE_CODE_REMOTE_SESSION_ID=cse_01BBBB gh pr comment 74 -F verdict.md',
    "gh pr review 74 --approve -b ok",
    "gh pr create --title t --body b",
    "gh pr edit 74 --body-file body.md",
    "gh issue comment 3 --body x",
    "/usr/bin/gh -R o/r pr comment 74 -b x",
    "gh api repos/o/r/issues/74/comments -f body='%s'" % VERDICT,
    "gh api -X PATCH repos/o/r/pulls/74 -f body=x",
    "gh api --method=POST repos/o/r/issues/74/comments --input c.json",
    "gh api -XPOST repos/o/r/issues/74/comments",
    "gh api graphql -f query='mutation { addComment(input:{}) { clientMutationId } }'",
    "curl -s -X POST https://api.github.com/repos/o/r/issues/74/comments -d @c.json",
    "curl -sd '{\"body\":\"x\"}' https://api.github.com/repos/o/r/issues/74/comments",
    "curl --json @c.json https://api.github.com/repos/o/r/issues/74/comments",
    "wget --post-data='x' https://api.github.com/repos/o/r/issues/74/comments",
    "http POST https://api.github.com/repos/o/r/issues/74/comments body=x",
    # 包んだ形・つないだ形
    "bash -c 'gh pr comment 74 -b x'",
    "eval \"gh pr comment 74 -b x\"",
    "cd /tmp && gh pr comment 74 -b x",
    "echo $(gh pr comment 74 -b x)",
    "env FOO=1 gh pr comment 74 -b x",
    # 読み切れない形（引用の閉じ忘れ）は止める側
    "gh pr comment 74 -b 'x",
]

PASS = [
    "gh api -X GET search/code -f q='x repo:o/r' --paginate",
    "gh pr view 74 --json body",
    "gh pr diff 74",
    "gh api repos/o/r/pulls/74 --jq .head.sha",
    "gh api graphql -f query='{ viewer { login } }'",
    "curl -s https://api.github.com/repos/o/r/pulls/74",
    "curl -s -X POST https://example.com/x -d y",
    "git push -u origin claude/x",
    "echo 'gh pr comment は MCP の道具で出す'",
    "grep -rn 'gh pr comment' docs/",
]


@pytest.mark.parametrize("cmd", STOP)
def test_stops_github_writes_from_bash(env, cmd):
    r = reason(env, cmd)
    assert r, cmd
    assert "MCP の道具" in r


@pytest.mark.parametrize("cmd", PASS)
def test_passes_reads_and_other_commands(env, cmd):
    assert reason(env, cmd) == "", cmd


def test_other_tools_untouched(env):
    payload = {"tool_name": "Read", "session_id": "s1", "tool_input": {"file_path": "/x"}}
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=json.dumps(payload), capture_output=True,
                       text=True, env=env, timeout=60)
    assert "Bash から GitHub へ" not in p.stdout
