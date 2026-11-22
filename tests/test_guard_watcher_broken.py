"""guard の入口: 壊れた見張りを黙って通さず、名と訳を知らせるか（注入の試験）。

意図: 1 つの見張りの故障で他の見張りや仕事を止めない。
課題: 入口の _run が見張りの例外を全部「通す」にし、訳は stderr にしか出さなかった＝守りが外れても誰も気づかない（原因の台帳の行）。
原因: 故障を「通す」と「黙る」を 1 つにしていた。通すのは残し、黙るのをやめる。
"""
import json
import shutil
import subprocess
import sys

import pytest

from test_guard import PLUGIN, env  # noqa: F401  （env は fixture）

# 止める見張りの無い道具の呼び出し（どの見張りも照らして何も言わない）
QUIET = {"tool_name": "Bash", "session_id": "s1", "tool_input": {"command": "echo 作り物"}}
# 止める見張りが言う呼び出し（tests/ に有料の上流の鍵の名を書く。名は字を分けて書く＝この file 自身は上流へつながらない）
STOPPED = {"tool_name": "Write", "tool_input": {"file_path": "/x/tests/test_a.py", "content": "OPENAI_" + "API_KEY"}}

BREAKS = [
    ("import で壊れる", "HOOKS = {'pre': 'check'}\nraise ImportError('作り物の故障')\n"),
    ("呼び出しで壊れる", "HOOKS = {'pre': 'check', 'post': 'check', 'start': 'check'}\n"
                        "def check(data, vals):\n    raise RuntimeError('作り物の故障')\n"),
    ("HOOKS が読めない", "HOOKS = {'pre': check_not_literal}\n"),
]


@pytest.fixture
def copy(tmp_path):
    shutil.copytree(PLUGIN, tmp_path / "plugin")
    return tmp_path / "plugin" / "scripts"


def run(env, scripts, event, payload):
    p = subprocess.run([sys.executable, str(scripts / "guard.py"), event], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else {}


@pytest.mark.parametrize("name,src", BREAKS, ids=[b[0] for b in BREAKS])
def test_壊れた見張りは止めの無い時も黙らず名と訳を出す(env, copy, name, src):
    (copy / "zz_sakumono.py").write_text(src, encoding="utf-8")
    out = run(env, copy, "pre", QUIET)
    assert "zz_sakumono" in out.get("systemMessage", "") and "照らせなかった" in out["systemMessage"], out
    assert out["hookSpecificOutput"].get("permissionDecision") is None      # 通す（故障で仕事を止めない）


def test_壊れた見張りは止めの文と隣への文にも添える(env, copy):
    (copy / "zz_sakumono.py").write_text(BREAKS[1][1], encoding="utf-8")
    out = run(env, copy, "pre", STOPPED)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"                              # 他の見張りの止めは残る
    assert "zz_sakumono" in out["permissionDecisionReason"] and "作り物の故障" in out["permissionDecisionReason"]
    post = run(env, copy, "post", QUIET)["hookSpecificOutput"]["additionalContext"]
    start = run(env, copy, "start", {"session_id": "s1"})["hookSpecificOutput"]["additionalContext"]
    assert "zz_sakumono" in post and "zz_sakumono" in start


def test_壊れた見張りが無ければ何も出さない(env, copy):
    assert run(env, copy, "pre", QUIET) == {}
