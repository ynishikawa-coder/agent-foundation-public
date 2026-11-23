"""guard の spec_gate: 設計書の型の gate を封の入口 seal.py を通さず --lock で直に呼ぶ手を止めるか（注入の試験）。"""
import pytest

from test_guard import bash, denied, env, hook  # noqa: F401  （env は fixture）
from test_dougu_bun_okiba import 根治の入口を指す


@pytest.mark.parametrize("cmd", [
    "python3 ~/型/check_spec_doc.py 設計書 --lock",
    "cd 設計書 && python3 ../型/check_spec_doc.py . --lock",
    "python3 seal.py 設計書 --match-only; python3 型/check_spec_doc.py 設計書 --lock",
])
def test_gate_を_lock_で直に呼ぶ手は止める(env, cmd):
    out = hook(env, "pre", bash(cmd))
    assert out.get("permissionDecision") == "deny", cmd
    assert "seal.py" in out["permissionDecisionReason"]
    assert 根治の入口を指す(out["permissionDecisionReason"])


@pytest.mark.parametrize("cmd", [
    "python3 plugins/dev-flow/skills/spec-doc/seal.py 設計書",
    "python3 型/check_spec_doc.py 設計書",
    "python3 型/check_spec_doc.py 設計書 --verify-receipt",
    "python3 型/check_spec_doc.py 型 --stamp",
    "python3 型/check_spec_doc.py 設計書 --locked-list",
])
def test_封の入口と_lock_の無い呼び出しは通す(env, cmd):
    assert not denied(env, bash(cmd)), cmd


def test_Bash_の外は見ない(env):
    payload = {"tool_name": "Write", "session_id": "s1",
               "tool_input": {"file_path": "/x/手順.md", "content": "check_spec_doc.py 設計書 --lock"}}
    assert not denied(env, payload)
