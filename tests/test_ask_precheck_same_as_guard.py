"""問いを出す前の照らしの道具（ask_precheck.py）は、guard が選択肢の画面を止める時と同じ照らしを返すか。

意図: 選択肢の画面の問いを、止められてから直すのでなく、初めから通る形で出す。
課題: 問いの形は出す時に guard が照らして止め、AI は止められてから直して出し直す往復をしていた。
原因: 照らしの正本（guard の見張り）は出す時の hook からしか呼べず、出す前に同じ照らしを当てる口が無かった。
ここでは、guard が止める問いの類（1 つだけ選ばせる・長い・中の言葉・推奨の印の崩れ）をわざと入れて、道具が同じ訳で
「止まる形」と返すこと、guard が通す問いは道具も通すこと、見張りを足すと道具の照らしにも入る（一覧を写していない）ことを見る。
入力は全部作り物。
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_guard import env, hook  # noqa: F401  （env は fixture）

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "guard"
TOOL = PLUGIN / "scripts" / "ask_precheck.py"
DUNNO = {"label": "分からない", "description": "選ぶと AI が聞き方を変えて聞き直す"}


def q(question, header="作り物", options=None):
    return {"question": question, "header": header, "multiSelect": False,
            "options": options or [{"label": "進める", "description": "そのまま進める"}, DUNNO]}


BAD = {
    "pick_one": [q("どれから先に進めますか？")],
    "long": [q("作り物の背景を長く書いた文です。" * 12 + "進めてよいですか？")],
    "inner": [q("作り物の file の scripts/foo_bar.py を消してよいですか？")],
    "rec": [q("作り物の作り方をどちらにしますか？", options=[
        {"label": "甲の作り方", "description": "甲で作る"},
        {"label": "乙の作り方 (推奨)", "description": "乙で作る"}, DUNNO])],
}
GOOD = [q("作り物の作業を始めてよいですか？")]


def run_tool(env, qs, tool=TOOL):
    p = subprocess.run([sys.executable, str(tool)], input=json.dumps({"questions": qs}, ensure_ascii=False),
                       capture_output=True, text=True, env=env, timeout=60, cwd=env["CLAUDE_PROJECT_DIR"])
    return p.returncode, p.stdout.strip()


def payload(env, qs):
    return {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion", "tool_input": {"questions": qs},
            "cwd": env["CLAUDE_PROJECT_DIR"]}


@pytest.mark.parametrize("name", sorted(BAD))
def test_guard_が止める問いは_道具も同じ訳で止まる形と返す(env, name):
    got = hook(env, "pre", payload(env, BAD[name]))
    assert got.get("permissionDecision") == "deny", name
    rc, out = run_tool(env, BAD[name])
    assert rc == 2 and out == got["permissionDecisionReason"].strip()


def test_guard_が通す問いは道具も通す(env):
    assert hook(env, "pre", payload(env, GOOD)) == {}
    assert run_tool(env, GOOD) == (0, "通る")


def test_読めない入力は照らさず使い方の誤りで返す(env):
    p = subprocess.run([sys.executable, str(TOOL)], input="{壊れた", capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 1 and p.stdout == ""


def test_見張りを足すと道具の照らしにも入る_一覧を写していない(env, tmp_path):
    copy = tmp_path / "guard"
    shutil.copytree(PLUGIN, copy, symlinks=False)
    (copy / "scripts" / "zz_fake_watch.py").write_text(
        'HOOKS = {"pre": "check"}\n\ndef check(data, vals):\n'
        '    return "[作り物] 足した見張りが止めた" if data.get("tool_name") == "AskUserQuestion" else ""\n',
        encoding="utf-8")
    rc, out = run_tool(env, GOOD, tool=copy / "scripts" / "ask_precheck.py")
    assert rc == 2 and "足した見張りが止めた" in out


def test_細目の聞き方は出す前の照らしの道具を名で指し_その道具が在る():
    text = (PLUGIN.parent / "core" / "細目" / "04-聞き方.md").read_text(encoding="utf-8")
    assert "`ask_precheck.py`（plugin guard）" in text and TOOL.is_file()
