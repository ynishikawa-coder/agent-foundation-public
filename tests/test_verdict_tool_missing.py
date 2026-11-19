"""判定の形の道具（checker の verdict_form.py）が無い・古い版の時、guard の pr_text は判定かどうか見分けられない。
その時は止めず（ふつうのコメントまで止めない＝オーナーの同意の無い止める範囲の広がりを作らない）、出した後に知らせる。
判定と見分けた後に道具が壊れた時は止める。道具をわざと消す・古くする・壊して、入口（guard.py pre／post）から当てる。
"""
import json
import subprocess
import sys

from test_pr_text import GUARD, _fake_gh, deny_reason, env, gh, verdict_comment  # noqa: F401


def post_notice(env, payload):
    p = subprocess.run([sys.executable, str(GUARD), "post"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"].get("additionalContext", "") if p.stdout.strip() else ""


def test_pr_text_判定の道具が無い時は止めずに知らせる(env, tmp_path):
    """判定かどうか見分けられない時（道具が無い・古い版で --looks に答えない）は、判定に見える文もふつうのコメントも止めず、
    出した後に知らせる（止める範囲を広げない）。わざと道具を消す・古い版にして当てる。"""
    _fake_gh(env)
    plain = "作り物のふつうのコメント。直したので見てください。"
    env["AF_VERDICT_FORM"] = str(tmp_path / "無い.py")
    for body in (plain, verdict_comment()):
        payload = gh("add_issue_comment", issue_number=1, body=body)
        assert deny_reason(env, payload) == ""
        note = post_notice(env, payload)
        assert "見分けられず" in note and "見つからない" in note and "止めていない" in note
    old = tmp_path / "verdict_form.py"
    old.write_text("import sys\nif '--looks' in sys.argv:\n    sys.stderr.write('unknown option --looks\\n'); sys.exit(2)\n"
                   "sys.exit(0)\n", encoding="utf-8")
    env["AF_VERDICT_FORM"] = str(old)
    payload = gh("add_issue_comment", issue_number=1, body=plain)
    assert deny_reason(env, payload) == ""
    assert "--looks に答えない" in post_notice(env, payload)


def test_pr_text_見分けられた判定の道具が壊れたら止める(env, tmp_path):
    """--looks で判定と見分けた後に形の照らしが壊れた時は、これまでどおり止める（判定を形の照らしの外へ逃がさない）。"""
    _fake_gh(env)
    broken = tmp_path / "verdict_form.py"
    broken.write_text("import sys\nif '--looks' in sys.argv:\n    print('verdict'); sys.exit(0)\nsys.exit(3)\n", encoding="utf-8")
    env["AF_VERDICT_FORM"] = str(broken)
    payload = gh("add_issue_comment", issue_number=1, body=verdict_comment())
    assert "壊れた" in deny_reason(env, payload)
    assert post_notice(env, payload) == ""


def test_pr_text_道具が在れば知らせない(env):
    _fake_gh(env)
    for body in ("作り物のふつうのコメント。", verdict_comment()):
        assert post_notice(env, gh("add_issue_comment", issue_number=1, body=body)) == ""
