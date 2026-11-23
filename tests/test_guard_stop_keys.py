"""値の表の「止める鍵」（schema で "stops": true）が読めない時、その鍵を使う見張りは自分が止める場面で止める側へ倒す。

意図: 足した止める形（上流の課金の印・中の言葉・戻せない操作・公開の repo）が、表の書き違いで黙って効かなくならない。
課題: values()・table() は読めない表・型の違う鍵を既定（[]）へ落とす。止める鍵ではそれが「足した形を素通りさせる」になっていた。
原因: 鍵が落ちた時にどちらへ倒れるかを鍵ごとに持たず、全部の鍵を「既定で動く」に当てていた。
解決: schema で止める鍵に印を付け、印の付いた鍵は guard_common.broken_stop_key で読めない訳を取り、見張りが自分の場面でだけ止める。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "guard"
GUARD = PLUGIN / "scripts" / "guard.py"
SCHEMA = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(PLUGIN / "scripts"))

STOPS = sorted(k for k, s in SCHEMA["sections"]["guard"]["keys"].items() if isinstance(s, dict) and s.get("stops"))


@pytest.fixture
def env(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "_AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp_path / "scratch")})
    return e


def table(env, tmp_path, body):
    t = tmp_path / "values.json"
    t.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    env["SKILL_VALUES"] = str(t)


def run(env, stdin):
    p = subprocess.run([sys.executable, str(GUARD), "pre"], input=stdin, capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def denied_for(out, key):
    return out.get("permissionDecision") == "deny" and key in out.get("permissionDecisionReason", "")


def test_止める鍵はどれも_どこかの見張りが読めない訳を取る():
    assert STOPS, "schema に止める鍵の印が無い"
    src = {p.name: p.read_text(encoding="utf-8") for p in (PLUGIN / "scripts").glob("*.py")}
    users = [n for n, s in src.items() if "broken_stop_key(" in s and n != "guard_common.py"]
    for k in STOPS:
        assert any('"%s"' % k in src[n] for n in users), "%s を読めない時に止める側へ倒す見張りが無い" % k


def test_印の無い鍵を止める鍵として問うと落ちる():
    import guard_common as G
    with pytest.raises(KeyError):
        G.broken_stop_key("ask_term_allow")


WRITE_TEST = json.dumps({"tool_name": "Write", "session_id": "s1",
                         "tool_input": {"file_path": "/w/tests/test_x.py", "content": "print('hello')\n"}})
WRITE_OTHER = json.dumps({"tool_name": "Write", "session_id": "s1",
                          "tool_input": {"file_path": "/w/notes/x.md", "content": "hello\n"}})
BASH_TEST = json.dumps({"tool_name": "Bash", "session_id": "s1",
                        "tool_input": {"command": "echo hello > tests/test_x.py"}})


@pytest.mark.parametrize("body", [{"guard": {"paid_markers_extra": "not-a-list"}},
                                  {"guard": {"paid_markers_extra": ["a\\\\b"]}}, "{こわれた"])
def test_足した課金の印が読めないと試験の_file_へ書く手だけ止める(env, tmp_path, body):
    table(env, tmp_path, body)
    assert run(env, WRITE_TEST).get("permissionDecision") == "deny"
    assert run(env, BASH_TEST).get("permissionDecision") == "deny"
    assert not denied_for(run(env, WRITE_OTHER), "paid_markers_extra")


def test_足した課金の印が読めれば試験の_file_へ書く手は止めない(env, tmp_path):
    table(env, tmp_path, {"guard": {"paid_markers_extra": ["MY_PAID_KEY"]}})
    assert not denied_for(run(env, WRITE_TEST), "paid_markers_extra")


ASK = json.dumps({"tool_name": "AskUserQuestion", "session_id": "s1", "tool_input": {"questions": [
    {"question": "置き場を A と B のどちらにしますか", "header": "置き場",
     "options": [{"label": "A", "description": "A に置く"}, {"label": "B", "description": "B に置く"}]}]}})


@pytest.mark.parametrize("body", [{"guard": {"ask_inner_terms_extra": ["("]}},
                                  {"guard": {"ask_inner_terms_extra": "not-a-list"}}, "{こわれた"])
def test_足した中の言葉の形が読めないと選択肢の画面を止める(env, tmp_path, body):
    table(env, tmp_path, body)
    out = run(env, ASK)
    assert out.get("permissionDecision") == "deny"
    if not isinstance(body, str):
        assert "ask_inner_terms_extra" in out["permissionDecisionReason"]


def test_足した中の言葉の形が読めれば止めない(env, tmp_path):
    table(env, tmp_path, {"guard": {"ask_inner_terms_extra": ["ZZZ-[0-9]+"]}})
    assert not denied_for(run(env, ASK), "ask_inner_terms_extra")


@pytest.mark.parametrize("body", ["{こわれた", {"guard": "x"}, {"guard": {"public_repos_extra": "^o/r$"}}])
def test_公開の_repo_の表が読めないと公開と見る(tmp_path, monkeypatch, body):
    import pr_text
    t = tmp_path / "values.json"
    t.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(t))
    assert pr_text._public_extra("someone/private-thing", {}, {})


def test_公開の_repo_の表が読めれば名の全体で当てる(tmp_path, monkeypatch):
    import pr_text
    t = tmp_path / "values.json"
    t.write_text(json.dumps({"guard": {"public_repos_extra": ["^o/r$"]}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(t))
    assert pr_text._public_extra("o/r", {}, {})
    assert not pr_text._public_extra("o/r-fork", {}, {})
