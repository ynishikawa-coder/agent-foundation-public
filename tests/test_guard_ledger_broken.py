"""guard の unanswered: 読めない問いの台帳を空と取り違えて上書きせず、脇へ移して知らせるか（注入の試験）。

意図: 答えの無い問いを次の窓へ漏らさず渡す。
課題: update_ledger が読めない台帳を空として読み、その上に書いて、積んであった問いを黙って消していた（原因の台帳の行）。
原因: 読めない台帳を「無い」と同じに扱っていた。
"""
import json
from pathlib import Path

from test_guard import ask_result, env, hook, run_cli  # noqa: F401  （env は fixture）


def _ledger_files(env):
    return sorted(Path(env["AF_GUARD_STATE"]).rglob("unanswered*"))


def _break_ledger(env):
    hook(env, "post", ask_result())                    # 台帳を作る
    led = [p for p in _ledger_files(env) if ".broken-" not in p.name][0]
    led.write_text('{"pending": [壊れた台帳', encoding="utf-8")
    return led


def test_読めない台帳は上書きせず脇へ移して知らせる(env):
    led = _break_ledger(env)
    note = hook(env, "post", ask_result(sid="s2")).get("additionalContext", "")
    aside = [p for p in _ledger_files(env) if ".broken-" in p.name]
    assert len(aside) == 1 and aside[0].read_text(encoding="utf-8") == '{"pending": [壊れた台帳', aside
    assert "unanswered-ledger-trouble" in note and aside[0].name in note, note
    assert json.loads(led.read_text(encoding="utf-8"))["pending"], "新しい台帳に今の問いが積まれる"


def test_窓の起動でも読めない台帳は脇へ移して知らせる(env):
    _break_ledger(env)
    note = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    assert ".broken-" in note, note
    assert [p for p in _ledger_files(env) if ".broken-" in p.name]


def test_読めない台帳は命令の口のlistで1を返す(env):
    _break_ledger(env)
    r = run_cli(env, "list")
    assert r.returncode == 1 and "読めない" in r.stderr, r
