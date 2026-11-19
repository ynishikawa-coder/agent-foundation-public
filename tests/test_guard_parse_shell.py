"""Bash の命令を語に分ける口（guard_common.parse_shell）と、それを使う守り（pr_text の git push・物差しの跡）が、知らない形を
黙って通さず照らす側に倒す、という約束を、誤りの類をわざと入れて拒む試験（PR #77 の red の所見 1・2）。

- 注は語の頭の # だけ（`http://x/#frag`・`fix#12` の後ろの命令を捨てない）
- 読み切れない形（関数・coproc・`bash -c --`・env -S・表に無い前置き・`$(…)`・`` `…` ``・`| bash`・`<<<`・find -exec 等）は
  unknowns に名指しで返す。git push の見分けは、それが在り命令の字に git と push が在れば push と見る
- 物差しの跡は、読み切れる物差しの命令 1 つだけの呼び出しの、誤りでない結果の最後の行だけ
入力は全部作り物。実の GitHub へは出ない（作り物の gh）。
"""
import subprocess
import sys
from pathlib import Path

import pytest

from test_pr_text import (PUBLIC_WORD, _fake_gh, _fake_public_repo, deny_reason, env, gh, verdict_comment,  # noqa: F401
                          write_rows)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
import guard_common as G  # noqa: E402
import pr_text  # noqa: E402

RULER = "check_all: 緑 (4 本)"

# 所見 1 の形（前の先端 d84d63f では push と見られず、公開の検査を通らなかった物）
BYPASS = (
    "curl -s http://x/#frag; git push origin b",
    "git commit -m fix#12 && git push origin b",
    "function f { git push; }",
    "f() { git push; }",
    "coproc git push",
    "bash -c -- 'git push'",
    "env -S 'git push'",
    "flock /tmp/l git push",
    "watch git push",
    "unbuffer git push",
    "strace -f git push",
    "su -c 'git push'",
    "script -qc 'git push'",
    "busybox sh -c 'git push'",
    "fish -c 'git push'",
    "find . -exec git push \\;",
    'echo "$(git push)"',
    "echo `git push`",
    "echo 'git push' | bash",
    "bash <<< 'git push'",
    "bash <<'EOF'\ngit push\nEOF",
    "python3 -c 'import os; os.system(\"git push\")'",
    "git -c alias.p=push p",
    "xargs -I{} sh -c 'git push' <<< x",
)


# ── 語に分ける口 ──
def test_注は語の頭の_井桁だけ():
    assert G.parse_shell("curl -s http://x/#frag; git push origin b") == (
        [["curl", "-s", "http://x/#frag"], ["git", "push", "origin", "b"]], [])
    assert G.parse_shell("git commit -m fix#12 && git push")[0][1] == ["git", "push"]
    assert G.parse_shell("git status # git push") == ([["git", "status"]], [])


def test_知っている形は読み切って_unknowns_を出さない():
    for cmd, want in (("env A=1 git push origin b", [["git", "push", "origin", "b"]]),
                      ('bash -c "git push"', [["git", "push"]]),
                      ("sudo -u me nice -n 5 timeout 60 git push", [["git", "push"]]),
                      ("echo b | xargs git push origin", [["echo", "b"], ["git", "push", "origin"]]),
                      ("eval git push", [["git", "push"]]),
                      ("cat <<EOF\ngit push\nEOF\ngit status", [["cat"], ["git", "status"]]),
                      ("bash scripts/check_all.sh 2>&1 >/dev/null", [["bash", "scripts/check_all.sh"]]),
                      ("g\\it pu''sh", [["git", "push"]]),
                      ('git commit -m "push it"', [["git", "commit", "-m", "push it"]])):
        assert G.parse_shell(cmd) == (want, []), cmd


@pytest.mark.parametrize("cmd", BYPASS)
def test_読み切れない形は_unknowns_か_git_push_の語の並びになる(cmd):
    cmds, unknowns = G.parse_shell(cmd)
    assert unknowns or ["git", "push"] in [c[:2] for c in cmds], cmd


def test_閉じない引用符や変数の命令の名は_unknowns():
    for cmd in ("git push 'origin", 'echo "a', "$G push", "${G} push", "(git push)", "x=$(echo git); $x push"):
        assert G.parse_shell(cmd)[1], cmd


# ── git push の見分け（照らす側に倒す）──
@pytest.mark.parametrize("cmd", BYPASS)
def test_読み切れない形の_git_push_も_push_と見る(cmd):
    assert pr_text.git_push(cmd)[1], cmd


def test_読み切れて_push_を走らせない命令は_push_と見ない():
    for cmd in ("echo git push", "git log --grep push", 'git commit -m "push it"', "git status", "grep -r 'git push' docs"):
        assert pr_text.git_push(cmd) == ("", False), cmd


def test_読み切れない形の_git_push_で公開の検査を当てる(env):
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_gh(env, private={"fake-public": "false"})
    _fake_public_repo(proj, PUBLIC_WORD)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=作り物", "-c", "user.email=noreply@example.com",
                    "commit", "-qm", "%s の直し" % PUBLIC_WORD], check=True)
    for cmd in BYPASS[:6] + ("echo 'git push' | bash", 'echo "$(git push)"', "find . -exec git push \\;"):
        bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(proj), "tool_input": {"command": cmd}}
        why = deny_reason(env, bash)
        assert "[public]" in why and "commit の説明と名義" in why, cmd


# ── 物差しの跡（結果の最後の行・物差しの命令だけ）──
def _ruler_log(env, command, result, is_error=False):
    log = Path(env["CLAUDE_PROJECT_DIR"]).parent / "t_ruler.jsonl"
    res = {"type": "tool_result", "tool_use_id": "t0", "content": result}
    if is_error:
        res["is_error"] = True
    write_rows(log, [{"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t0", "name": "Bash", "input": {"command": command}}]}},
        {"type": "user", "message": {"role": "user", "content": [res]}}])
    _fake_gh(env)
    return deny_reason(env, dict(gh("add_issue_comment", issue_number=1, body=verdict_comment()), transcript_path=str(log)))


def test_本文を引く命令と同じ呼び出しで回した物差しは跡に数えない(env):
    why = _ruler_log(env, "gh api repos/fake-owner/fake-private/pulls/1 --jq .body; bash scripts/check_all.sh",
                     "検査: %s\ncheck_all: 赤 (1 本)" % RULER)
    assert "物差しの跡" in why


@pytest.mark.parametrize("cmd,result,err", [
    ("bash /nonexistent/check_all.sh; echo '%s'" % RULER, "bash: /nonexistent/check_all.sh: No such file\n" + RULER, False),
    ("bash scripts/check_all.sh", "検査: %s\ncheck_all: 赤 (1 本)" % RULER, False),        # 途中の行は数えない
    ("bash scripts/check_all.sh", RULER, True),                                             # 誤りの結果は数えない
    ("pytest --version", RULER, False),                                                     # 走らせない形は物差しでない
    ("bash scripts/check_all.sh | tail -3", RULER, False),
    ("bash scripts/check_all.sh; cat /tmp/x", RULER, False),
    ("bash scripts/check_all.sh $(echo)", RULER, False),
    ('bash -c "bash scripts/check_all.sh; echo x"', RULER, False),
])
def test_物差しの最後の行でない字は跡に数えない(env, cmd, result, err):
    assert "物差しの跡" in _ruler_log(env, cmd, result, err), cmd


def test_物差しだけの呼び出しの最後の行は跡に数える(env):
    for cmd in ("bash scripts/check_all.sh", "cd /x && bash scripts/check_all.sh 2>&1", "bash -c 'bash scripts/check_all.sh'"):
        assert _ruler_log(env, cmd, "…\n%s\n\n" % RULER) == "", cmd
