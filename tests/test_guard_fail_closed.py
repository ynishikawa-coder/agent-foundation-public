"""守りの hook は、見張りが壊れた・入力や値の表が読めない時に、pre では止める（既定で止める）。

意図: 守りが働いたかを判らないまま、止めるべき呼び出しを通さない。
課題: 見張りの例外・読めない HOOKS・読めない入力の JSON・読めない足した形（irreversible_*_extra）が、黙って通していた。
原因: 「見張りの故障で窓を止めない」を、止める側の出来事（pre）にも同じに当てていた（既定で通す）。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "guard"
GUARD = PLUGIN / "scripts" / "guard.py"
sys.path.insert(0, str(PLUGIN / "scripts"))


@pytest.fixture
def env(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (tmp_path / "scratch").mkdir()
    e = {k: v for k, v in os.environ.items() if not k.startswith(("AF_", "_AF_", "SKILL_VALUES", "CLAUDE_PROJECT_DIR"))}
    e.update({"AF_GUARD_TMP": str(tmp_path / "tmp"), "AF_GUARD_STATE": str(tmp_path / "state"),
              "CLAUDE_PROJECT_DIR": str(proj), "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(tmp_path / "scratch")})
    return e


def run(env, event, stdin, guard=GUARD):
    p = subprocess.run([sys.executable, str(guard), event], input=stdin, capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out)["hookSpecificOutput"] if out else {}


def bash(cmd, sid="s1", cwd=""):
    return json.dumps({"tool_name": "Bash", "session_id": sid, "cwd": cwd, "tool_input": {"command": cmd}})


@pytest.fixture
def broken_plugin(tmp_path):
    """guard の写しに、わざと壊した見張りを 2 つ足す（呼ぶと例外・HOOKS が読めない）。"""
    dst = tmp_path / "guard"
    shutil.copytree(PLUGIN, dst, symlinks=False)
    s = dst / "scripts"
    (s / "zz_raises.py").write_text('HOOKS = {"pre": "check", "post": "check", "start": "check"}\n'
                                    "def check(data, vals):\n    raise RuntimeError('わざと壊した')\n", encoding="utf-8")
    return s / "guard.py"


def test_見張りが例外を上げたら_pre_は止めて名指す(env, broken_plugin):
    out = run(env, "pre", bash("ls"), broken_plugin)
    assert out.get("permissionDecision") == "deny"
    assert "zz_raises" in out["permissionDecisionReason"] and "わざと壊した" in out["permissionDecisionReason"]


def test_見張りが例外を上げても_post_と_start_は止めず名を知らせる(env, broken_plugin):
    for ev in ("post", "start"):
        out = run(env, ev, json.dumps({"session_id": "s1", "tool_name": "Bash"}), broken_plugin)
        assert "permissionDecision" not in out
        assert "zz_raises" in out.get("additionalContext", "")


def test_HOOKS_の宣言が読めない見張りは_pre_で止める(env, broken_plugin):
    (broken_plugin.parent / "zz_raises.py").unlink()
    (broken_plugin.parent / "zz_badhooks.py").write_text("HOOKS = {'pre': check_func()}\n", encoding="utf-8")
    out = run(env, "pre", bash("ls"), broken_plugin)
    assert out.get("permissionDecision") == "deny"
    assert "zz_badhooks" in out["permissionDecisionReason"]


@pytest.mark.parametrize("stdin", ["こわれた", "[1, 2]", "null", ""])
def test_読めない入力の_JSON_は_pre_で止め_post_と_start_は黙る(env, stdin):
    assert run(env, "pre", stdin).get("permissionDecision") == "deny"
    assert run(env, "post", stdin) == {}
    assert run(env, "start", stdin) == {}


def _away(env, sid="s1"):
    """離席の窓を開く（答えの無い問いが閉じた形）。"""
    q = {"question": "作り物の置き場を A と B のどちらにしますか", "header": "置き場",
         "options": [{"label": "A", "description": "作り物の A"}, {"label": "B", "description": "作り物の B"}]}
    run(env, "post", json.dumps({"tool_name": "AskUserQuestion", "session_id": sid, "transcript_path": "",
                                 "tool_response": {"questions": [q], "answers": {}}}))


@pytest.mark.parametrize("rows", [["("], [{"pattern": "[", "why": "x"}], "not-a-list"])
def test_足した戻せない形が読めないと_離席中の_Bash_を止める(env, tmp_path, rows):
    t = tmp_path / "values.json"
    t.write_text(json.dumps({"guard": {"irreversible_bash_extra": rows}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(t)
    _away(env)
    out = run(env, "pre", bash("ls"))
    assert out.get("permissionDecision") == "deny"
    assert "irreversible_bash_extra" in out["permissionDecisionReason"]


def test_値の表そのものが読めないと_離席中の_Bash_と_MCP_の道具を止める(env, tmp_path):
    t = tmp_path / "values.json"
    t.write_text("{こわれた", encoding="utf-8")
    env["SKILL_VALUES"] = str(t)
    _away(env)
    assert run(env, "pre", bash("ls")).get("permissionDecision") == "deny"
    mcp = json.dumps({"tool_name": "mcp__x__do_thing", "session_id": "s1", "tool_input": {}})
    assert run(env, "pre", mcp).get("permissionDecision") == "deny"


def test_足した道具の形が読めないと_離席中の_MCP_の道具を止め_Read_は通す(env, tmp_path):
    t = tmp_path / "values.json"
    t.write_text(json.dumps({"guard": {"irreversible_tools_extra": ["(" ]}}), encoding="utf-8")
    env["SKILL_VALUES"] = str(t)
    _away(env)
    mcp = json.dumps({"tool_name": "mcp__x__do_thing", "session_id": "s1", "tool_input": {}})
    out = run(env, "pre", mcp)
    assert out.get("permissionDecision") == "deny" and "irreversible_tools_extra" in out["permissionDecisionReason"]
    read = json.dumps({"tool_name": "Read", "session_id": "s1", "tool_input": {"file_path": "/x"}})
    assert run(env, "pre", read).get("permissionDecision") != "deny"


def test_窓の_repo_の根は_CLAUDE_PROJECT_DIR_より入力の_cwd_を正本にする(tmp_path, monkeypatch):
    import guard_common as G
    a, b = tmp_path / "a", tmp_path / "b"
    for r in (a, b):
        (r / "sub").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(r)], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(a))
    assert G.project_dir({"cwd": str(b / "sub")}) == str(b)
    assert G.project_dir({"cwd": str(tmp_path / "no-such")}) == str(a)
    assert G.project_dir({}) == str(a)
