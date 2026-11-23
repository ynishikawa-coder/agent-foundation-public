"""選択肢の画面の前に、判断の前提（具体例と判断の物差し）を見せていなければ、画面を出す前に止める注入の試験。

意図: オーナーに判断させる時は、具体例と、どんな理由で判断してほしいかを先に示して確かめてから聞く（オーナーの声 2026-11-23）。
課題: 選択肢の画面は、問いの文の形（長さ・中の言葉・話題・推奨の印）だけを照らし、何を例に・何を物差しに選べばよいかを
見せないまま人に出られた。
原因: 「案と前提をチャットで先に見せる」が文の決まり（核「聞き方」・細目「聞き方」）だけで、画面の前のチャットを照らす物が無かった。
ここでは、2 行の見出しが無い・片方だけ・前の頼みの中にだけ在る・行頭でない（文中に語が在るだけ）画面が止まり、2 行が在る画面と
照らさない問い（値の表で外した問い）が通る事を見る。入力は全部作り物。
"""
import json

import pytest

from test_guard import ask_pre, deny_reason, env, q, write_log  # noqa: F401  （env は fixture）


def owner(text, uuid):
    return {"type": "user", "uuid": uuid, "message": {"content": text}}


def said(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


@pytest.fixture(autouse=True)
def _prior_off(env, tmp_path):
    """聞く前に引いた跡の見張り（prior_ask）はこの問いを外し、ここでは判断の前提だけを見る。"""
    values(env, tmp_path)


def values(env, tmp_path, **extra):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"ask_prior_exempt": ["会議を回数で"], **extra}}, ensure_ascii=False), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)


def ask_after(tmp_path, *rows):
    tpath = write_log(tmp_path / "t.jsonl", [owner("作り物の頼み", "u1"), *rows])
    p = ask_pre(q("会議を回数で別に数えますか", header="会議の数え方", labels=("回数で数える", "時間で数える", "分からない")))
    p["transcript_path"] = tpath
    return p


BOTH = "具体例: 作り物の会社の 10 月の会議 3 回（計 4 時間）\n判断の物差し: 請求の明細と合わせたいなら回数・工数を見たいなら時間"

BAD = [
    ("2 行とも無い", [said("会議の数え方を聞きます。")], ("具体例:", "判断の物差し:")),
    ("具体例だけ", [said("具体例: 作り物の会議 3 回")], ("判断の物差し:",)),
    ("物差しだけ", [said("- **判断の物差し**: 作り物の理由")], ("具体例:",)),
    ("前の頼みの中にだけ在る", [said(BOTH), owner("次の作り物の頼み", "u2")], ("具体例:", "判断の物差し:")),
    ("文中に語が在るだけ", [said("具体例と判断の物差しは前に話した通りです。")], ("具体例:", "判断の物差し:")),
    ("見出しだけで中身が空", [said("具体例:\n判断の物差し:")], ("具体例:", "判断の物差し:")),
]


@pytest.mark.parametrize("name,rows,miss", BAD, ids=[c[0] for c in BAD])
def test_判断の前提を見せていない画面は出す前に止める(env, tmp_path, name, rows, miss):
    """意図: 例と物差しの無い判断を人に頼まない。課題: 前提を見せずに画面だけが出ていた。"""
    why = deny_reason(env, ask_after(tmp_path, *rows))
    assert "[premise]" in why and "画面はまだ人に出ていない" in why, why
    for m in miss:
        assert "「%s」" % m in why or m in why


GOOD = [
    ("2 行が在る", [said(BOTH)]),
    ("箇条と太字の 2 行", [said("- **具体例**: 作り物の会議 3 回\n- **判断の物差し**：請求と合わせたいか")]),
    ("2 行が別の文に分かれる", [said("具体例: 作り物の会議 3 回"), said("判断の物差し: 請求と合わせたいか")]),
]


@pytest.mark.parametrize("name,rows", GOOD, ids=[c[0] for c in GOOD])
def test_判断の前提を見せた画面は通す(env, tmp_path, name, rows):
    """意図: 正しい道（2 行を見せてから聞く）は止めない。"""
    assert deny_reason(env, ask_after(tmp_path, *rows)) == ""


def test_値の表で外した問いは前提を照らさない(env, tmp_path):
    """意図: 誤って止めた時の口は ask_shape の外し（問いの文）1 本に寄せる＝新しい鍵を作らない。"""
    values(env, tmp_path, ask_shape_exempt=["会議を回数で"])
    assert deny_reason(env, ask_after(tmp_path, said("会議の数え方を聞きます。"))) == ""


def test_会話ログが読めない時と助手の中は照らさない(env, tmp_path):
    """意図: 見張りの故障で窓を止めない。課題: 会話ログの無い呼び出しまで止めると、どの画面も出られなくなる。"""
    p = ask_pre(q("会議を回数で別に数えますか", header="会議の数え方", labels=("回数で数える", "時間で数える", "分からない")))
    p["transcript_path"] = str(tmp_path / "無い.jsonl")
    assert deny_reason(env, p) == ""
    sub = tmp_path / "subagents"
    sub.mkdir()
    p["transcript_path"] = write_log(sub / "a.jsonl", [owner("作り物の頼み", "u1"), said("前提なし")])
    assert deny_reason(env, p) == ""


def test_持ち越した問いの出し直しは前提の2行の名を正本どおりに頼む(env):
    """意図: 答えの無い問いを出し直す時も、具体例と判断の物差しを先に見せる。課題: 出し直しの知らせが前提を 1〜2 文と
    言うだけだと、AI は 2 行を書かずに画面を出し、問いの照らしに止められて出し直せない。名は ask_shape の PREMISE を正本に引く。"""
    import importlib.util
    from pathlib import Path
    from test_guard import ask_result, hook
    src = Path(__file__).resolve().parents[1] / "plugins/guard/scripts/ask_shape.py"
    spec = importlib.util.spec_from_file_location("ask_shape_premise", src)
    ask_shape = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ask_shape)
    hook(env, "post", ask_result())
    again = hook(env, "start", {"session_id": "s2"}).get("additionalContext", "")
    for name, _ in ask_shape.PREMISE:
        assert f"「{name}:」" in again
