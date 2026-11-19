"""入れて起動する試験（scripts/plugin_smoke.py）が、照らせない物を黙って飛ばして緑にしないか。

入った台帳が空・行が無い（入った commit を照らせない）、起動の hook の出力の JSON が読めない、終わり方（exit_code）が
分からない、をわざと入れて外れと名指す事を見る注入の試験。本物の claude は要らない（照らす口に作り物の入力を直に当てる）。
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import plugin_smoke as S  # noqa: E402

SHA = "a" * 40
PLUGINS = ["core", "guard"]


def _ok_ctx(text="核"):
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}})


@pytest.mark.parametrize("rows", [
    {},                                                    # 台帳が空
    {"core": {"gitCommitSha": SHA}},                       # guard の行が無い
])
def test_台帳に行の無い_plugin_は入った_commit_を照らせないと名指す(rows):
    bad = S.sha_problems(rows, PLUGINS, SHA)
    missing = [p for p in PLUGINS if p not in rows]
    assert missing and all(any(f"plugin {p} の行が入った台帳" in b for b in bad) for p in missing), bad


def test_台帳が空なら試したい先端を渡さなくても名指す():
    assert S.sha_problems({}, PLUGINS, None)


def test_全部の行が試したい先端を指す時だけ外れが無い():
    rows = {p: {"gitCommitSha": SHA} for p in PLUGINS}
    assert S.sha_problems(rows, PLUGINS, SHA) == []
    rows["guard"]["gitCommitSha"] = "b" * 40
    assert any("guard" in b and "試したい先端" in b for b in S.sha_problems(rows, PLUGINS, SHA))


def test_出力の_JSON_が読めない_hook_を捨てずに名指す():
    ctx, bad = S.hook_contexts([{"hook_name": "SessionStart:startup", "exit_code": 0, "output": '{"hookSpecificOutput": '}])
    assert ctx == [] and any("JSON が読めない" in b for b in bad), bad


def test_終わり方が分からない_hook_を通さない():
    ctx, bad = S.hook_contexts([{"hook_name": "SessionStart:startup", "output": _ok_ctx()}])
    assert ctx == ["核"] and any("終わり方" in b for b in bad), bad


def test_落ちた_hook_を名指す():
    _, bad = S.hook_contexts([{"hook_name": "h", "exit_code": 2, "stderr": "壊れた", "output": ""}])
    assert any("落ちた" in b and "壊れた" in b for b in bad), bad


def test_読める出力と字の出力は文脈に足して外れにしない():
    ctx, bad = S.hook_contexts([
        {"hook_name": "a", "exit_code": 0, "output": _ok_ctx("核の文")},
        {"hook_name": "b", "exit_code": 0, "output": "字のまま\n"},
        {"hook_name": "c", "exit_code": 0, "output": "{}"},
        {"hook_name": "d", "exit_code": 0, "output": ""},
    ])
    assert bad == [] and ctx == ["核の文", "字のまま"]
