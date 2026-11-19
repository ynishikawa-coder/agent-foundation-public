"""Bash の命令を語に分ける口（guard_common.parse_shell）と、それを使う守り（pr_text の git push・物差しの跡）が、知らない形を
黙って通さず照らす側に倒す、という約束を、誤りの類をわざと入れて拒む試験（PR #77 の red の所見 1・2）。

- 注は語の頭の # だけ（`http://x/#frag`・`fix#12` の後ろの命令を捨てない）
- 読み切れない形（関数・coproc・`bash -c --`・env -S・表に無い前置き・`$(…)`・`` `…` ``・`| bash`・`<<<`・find -exec 等）は
  unknowns に名指しで返す。git push の見分けは、それが在り命令の字に git と push が在れば push と見る
- 物差しの跡は、読み切れる物差しの命令 1 つだけの呼び出しの、走った結果（誤りなく返った物か、Exit code N で始まる＝物差しが
  赤を返した物）の最後の行だけ。拒まれた・hook に止められた・中断した返りは数えない（PR #77 の 3 回目の red の所見 1）
- push の先は、読めた cd・-C を捨てず窓の cwd と合わせた全部に公開の検査を当て、cd・-C の先が字で決まらなければ止める（所見 2）
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
        assert pr_text.git_push(cmd) == ([], False, ""), cmd


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
    res = {"type": "tool_result", "tool_use_id": "t0", "content": result, "is_error": bool(is_error)}
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


# ── 物差しが赤の時も判定を出せる（PR #77 の 3 回目の red の所見 1）──
RED = "check_all: 赤 (1/5 本: pytest) @0123456789ab 直し: 赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す"


def _red_verdict():
    return verdict_comment(judged="red", fail=4, stop=True).replace(RULER, RED)


def _red_log(env, result, is_error):
    log = Path(env["CLAUDE_PROJECT_DIR"]).parent / "t_red.jsonl"
    res = {"type": "tool_result", "tool_use_id": "t0", "content": result, "is_error": bool(is_error)}
    write_rows(log, [{"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t0", "name": "Bash", "input": {"command": "bash scripts/check_all.sh"}}]}},
        {"type": "user", "message": {"role": "user", "content": [res]}}])
    _fake_gh(env)
    return deny_reason(env, dict(gh("add_issue_comment", issue_number=1, body=_red_verdict()), transcript_path=str(log)))


@pytest.mark.parametrize("result", ["Exit code 1\n検査: …\n" + RED, [{"type": "text", "text": "Exit code 1\n" + RED + "\n"}]])
def test_物差しが赤を返した結果の最後の行で赤の判定を出せる(env, result):
    assert _red_log(env, result, True) == ""


@pytest.mark.parametrize("result", [
    RED,                                                                    # Exit code で始まらない誤り＝走った証にならない
    "The user doesn't want to proceed with this tool use.\n" + RED,        # 拒まれた
    "PreToolUse:Bash hook error: blocked\n" + RED,                          # hook に止められた
    "[Request interrupted by user]\n" + RED,                                # 中断
])
def test_走っていない返りの字は赤の判定の跡に数えない(env, result):
    assert "物差しの跡" in _red_log(env, result, True)


def test_走ったかは_tool_use_の_id_の返りで見る():
    def rows(**res):
        return [{"type": "user", "message": {"content": [dict({"type": "tool_result", "tool_use_id": "t0"}, **res)]}}]
    assert G.tool_use_ran(rows(content="ok", is_error=False), "t0") == (True, "ok", "")
    assert G.tool_use_ran(rows(content="Exit code 1\n赤", is_error=True), "t0") == (True, "Exit code 1\n赤", "")
    for got in (G.tool_use_ran(rows(content="denied", is_error=True), "t0"),      # 拒まれた・hook・中断
                G.tool_use_ran(rows(content="ok"), "t0"),                         # is_error の欄が無い
                G.tool_use_ran(rows(content="ok", is_error=False), "t1"),          # 返りが無い
                G.tool_use_ran([], "")):
        assert got[0] is False and got[2], got


def test_is_error_の欄の無い返りは物差しの跡に数えない(env):
    log = Path(env["CLAUDE_PROJECT_DIR"]).parent / "t_noflag.jsonl"
    write_rows(log, [{"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t0", "name": "Bash", "input": {"command": "bash scripts/check_all.sh"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t0", "content": RULER}]}}])
    _fake_gh(env)
    why = deny_reason(env, dict(gh("add_issue_comment", issue_number=1, body=verdict_comment()), transcript_path=str(log)))
    assert "物差しの跡" in why


def test_走った証の読みは_82_と同じ():
    assert G.result_state(None) == "none"
    assert G.result_state({"content": "x"}) == "ok"
    assert G.result_state({"is_error": True, "content": "Exit code 1\nx"}) == "exit"
    assert G.result_state({"is_error": True, "content": [{"type": "text", "text": "Exit code 127"}]}) == "exit"
    assert G.result_state({"is_error": True, "content": "denied"}) == "no"


# ── push の先（読めた cd を捨てない・字で決まらなければ止める・PR #77 の 3 回目の red の所見 2）──
def _committed_public(proj):
    _fake_public_repo(proj, PUBLIC_WORD)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=作り物", "-c", "user.email=noreply@example.com",
                    "commit", "-qm", "%s の直し" % PUBLIC_WORD], check=True)


CD_PUBLIC = (
    "cd {pub} && flock /tmp/l git push",
    "cd {pub} && bash -c -- 'git push'",
    "cd {pub} && echo 'git push' | bash",
    "cd {pub}; f() {{ git push; }}; f",
    "git -C {pub} status && watch git push",
    "(cd {pub} && flock /tmp/l git push)",
    "cd {pub} && git push origin b",
    "pushd {pub} && git push origin b",
)


@pytest.mark.parametrize("cmd", CD_PUBLIC)
def test_読み切れない形でも読めた_cd_の先の公開の_repo_を照らす(env, tmp_path, cmd):
    pub = tmp_path / "pub"
    pub.mkdir()
    _committed_public(pub)
    _fake_gh(env, private={"fake-public": "false"})
    other = tmp_path / "elsewhere"                  # 窓の cwd は repo でない所
    other.mkdir()
    bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(other), "tool_input": {"command": cmd.format(pub=pub)}}
    why = deny_reason(env, bash)
    assert "[public]" in why and "commit の説明と名義" in why, cmd


@pytest.mark.parametrize("cmd", [
    "cd $P && flock /tmp/l git push",
    'cd "$(cat /tmp/where)" && git push origin b',
    "cd && git push origin b",
    "cd - && git push origin b",
    "popd && git push origin b",
    "git -C $P push origin b",
    "echo $(cd /x) && flock /tmp/l git push",
    "env -C /x git push origin b",
    "GIT_DIR=/x/.git git push origin b",
    "sudo -D /x git push origin b",
])
def test_push_の先が字で決まらなければ止める(env, tmp_path, cmd):
    other = tmp_path / "elsewhere"
    other.mkdir()
    _fake_gh(env)
    bash = {"tool_name": "Bash", "session_id": "s1", "cwd": str(other), "tool_input": {"command": cmd}}
    why = deny_reason(env, bash)
    assert "[public]" in why and "push する repo を読み切れず" in why, cmd


def test_push_の先の候補は窓の_cwd_と読めた_cd_と_C_の全部():
    assert pr_text.git_push("cd a && flock /tmp/l git -C b push")[:2] == (["", "a", "a/b"], True)
    assert pr_text.git_push("cd a && git -C b push origin x") == (["a/b"], True, "")
    assert pr_text.git_push("git --git-dir=/p/.git push") == (["/p/.git"], True, "")


# ── 読み切れない所は機械で読める code で返す（呼ぶ側は code で決め、訳の字を見ない）──
CODE_OF = {
    "echo $(id)": "subst",
    "echo `id`": "backtick",
    "diff <(ls) x": "process_subst",
    "git push 'origin": "unclosed_quote",
    "$G push": "var_program",
    "function f { git push; }": "function_def",
    "f() { git push; }": "function_def",
    "coproc git push": "compound",
    "(git push)": "subshell",
    "echo 'git push' | bash": "pipe_to_shell",
    "bash <<< 'git push'": "heredoc_to_shell",
    "bash <<'EOF'\ngit push\nEOF": "heredoc_to_shell",
    'bash -c "$X"': "exec_shell",
    "bash -c -- 'git push'": "dash_c_dashdash",
    "env -S 'git push'": "env_S",
    "eval $X": "eval_dyn",
    "flock /tmp/l git push": "unknown_wrapper",
    "git -c alias.p=push p": "git_alias",
    "eval eval eval eval eval eval x": "nesting_deep",
}


@pytest.mark.parametrize("cmd,code", list(CODE_OF.items()))
def test_読み切れない所は_code_つきで返す(cmd, code):
    unknowns = G.parse_shell(cmd)[1]
    assert all(isinstance(u, G.Unknown) and u.code in G.UNKNOWN_CODES and u.message for u in unknowns), unknowns
    assert code in [u.code for u in unknowns], (cmd, unknowns)


def test_code_の表は全部が試験で当たる():
    hit = {u.code for c in CODE_OF for u in G.parse_shell(c)[1]} | {u.code for u in G.parse_shell(None)[1]}
    assert G.UNKNOWN_CODES - hit == set()
