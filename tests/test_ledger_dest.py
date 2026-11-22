"""原因の台帳の行き先の見張り（guard の ledger_dest・止めずに知らせる）の注入の試験。

前の形: 細目 §3 の行き先は 3 つ（直す窓・直した・直さない）なのに、各社の台帳（Notion）は 5 つの値を選べ、表に無い値
（「オーナーの判断」）で行が書かれても誰も照らさなかった。今の形: Notion へ書く入力の `行き先` を細目の表と照らし、表に無い値なら
書いた後に知らせる（止めない）。
"""
import sys
from pathlib import Path

import pytest

from test_guard import env, hook  # noqa: F401  （env は fixture）

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
import ledger_dest as L  # noqa: E402

NOTION = "mcp__8f4aaec6-0000__notion-"


def update(dest, tool="update-page"):
    return {"tool_name": NOTION + tool, "session_id": "s1", "transcript_path": "",
            "tool_input": {"page_id": "作り物", "command": "update_properties", "properties": {"行き先": dest, "直し": "作り物"}}}


def create(*dests):
    return {"tool_name": NOTION + "create-pages", "session_id": "s1", "transcript_path": "",
            "tool_input": {"parent": {"data_source_id": "作り物"},
                           "pages": [{"properties": {"原因": "作り物", "行き先": d}} for d in dests]}}


def test_表は細目の原因の台帳の行から読む():
    assert L.table((ROOT / "plugins" / "core" / "細目.md").read_text(encoding="utf-8")) == (["直す窓", "直した", "直さない"], "未定")


@pytest.mark.parametrize("payload,bad", [
    (update("オーナーの判断"), "「オーナーの判断」"),
    (create("直す窓", "保留"), "「保留」"),
    (update("直した "), "「直した 」"),          # 前後の空白も表の値と別（前方一致・部分一致で通さない）
    (update("直"), "「直」"),
])
def test_表に無い行き先は書いた後に知らせる(env, payload, bad):  # noqa: F811
    ctx = hook(env, "post", payload).get("additionalContext", "")
    assert bad in ctx and "止めていない" in ctx and "`直す窓`・`直した`・`直さない`" in ctx, ctx


@pytest.mark.parametrize("payload", [
    update("直した"), update("未定"), create("直す窓", "直さない"),
    {"tool_name": "Write", "tool_input": {"file_path": "/x/a.json", "content": '{"行き先": "オーナーの判断"}'}},
    {"tool_name": NOTION + "fetch", "tool_input": {"行き先": "オーナーの判断"}},
])
def test_表の値と台帳へ書かない道具は黙る(env, payload):  # noqa: F811
    assert hook(env, "post", payload) == {}


def test_止めない(env):  # noqa: F811
    assert hook(env, "pre", update("オーナーの判断")) == {}


def test_細目が読めない時は値を推さず照らせなかったと知らせる(env, tmp_path):  # noqa: F811
    """注入の試験: 前の形は細目が無い・行の形が変わった時に黙り、照らしていないのに照らした事になった。"""
    (tmp_path / "崩れ.md").write_text("- **原因の台帳** — 行き先の書き方を変えた\n", encoding="utf-8")
    for f in ("無い.md", "崩れ.md"):
        e = dict(env, AF_SAIMOKU=str(tmp_path / f))
        for dest in ("オーナーの判断", "直した"):
            ctx = hook(e, "post", update(dest)).get("additionalContext", "")
            assert "照らせなかった" in ctx and "「%s」" % dest in ctx and "止めていない" in ctx, ctx
    assert hook(dict(env, AF_SAIMOKU=str(tmp_path / "無い.md")), "post", update(None)) == {}   # 行き先を書かない入力は黙る


def test_細目の表を書き換えると照らす値も変わる(env, tmp_path):  # noqa: F811
    """注入の試験: 写しが無い＝細目に値を足すと、その値は知らせなくなる。"""
    text = (ROOT / "plugins" / "core" / "細目.md").read_text(encoding="utf-8")
    p = tmp_path / "細目.md"
    p.write_text(text.replace("／`直さない`（", "／`オーナーの判断`（作り物）／`直さない`（", 1), encoding="utf-8")
    env = dict(env, AF_SAIMOKU=str(p))
    assert hook(env, "post", update("オーナーの判断")) == {}
