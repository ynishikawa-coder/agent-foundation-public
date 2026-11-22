"""guard の prior_ask: 選択肢の画面を出す前に、この窓の文脈（最後に縮めた境より後）と助手の中で決定の記録と問いの表を引いた
跡が無ければ AI だけ止めるか（注入の試験）。

意図: 問いの前に決定の記録と問いの表を引かせる。
課題: 引いた後に子の窓の知らせが届く・前の頼みで引いた・助手に引かせた時に、引いたのに問いを止めていた（原因の台帳の行）。
原因: 「人の行」を origin の欠けで見分けて知らせの行・縮めた要約を人の頼みと数え、その頼みで跡を切っていた。助手のログは
  見ず、読めない行は黙って捨てていた。
"""
import json

import pytest

from test_guard import ask_pre, deny_reason, env, q, write_log  # noqa: F401  （env は fixture）

# ── prior_ask（選択肢の画面の前に決定の記録と問いの表を引いた跡）──
LOOKUP = ["作り物の記録を引く道具", "\\bGrep\\b.*問いの表"]


def use(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}


def owner(text, uuid):
    return {"type": "user", "uuid": uuid, "message": {"content": text}}


def prior_log(tmp_path, *rows, name="p.jsonl"):
    return write_log(tmp_path / name, [owner("作り物の頼み", "u1"), *rows])


def ask_with(tpath, *qs, sid="s1"):
    p = ask_pre(*(qs or (q("会議を回数で別に数えますか", header="会議の数え方"),)))
    p.update({"transcript_path": tpath, "session_id": sid})
    return p


def lookup_values(env, tmp_path, **extra):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"ask_prior_lookup": LOOKUP, **extra}}, ensure_ascii=False), encoding="utf-8")
    env["SKILL_VALUES"] = str(table)


BOUNDARY = {"type": "system", "subtype": "compact_boundary", "timestamp": "2026-11-22T01:00:00Z"}
NOTICE = {"type": "user", "uuid": "n1", "origin": {"kind": "task-notification"}, "promptSource": "system",
          "message": {"content": "<task-notification>作り物の子の窓が終わった</task-notification>"}}
SUMMARY = {"type": "user", "uuid": "c1", "isCompactSummary": True, "message": {"content": "作り物の要約"}}

PRIOR_BAD = [
    ("何も引いていない", [use("Read", {"file_path": "/x/作り物.txt"})]),
    ("引いたのは縮めた境より前だけ", [use("作り物の記録を引く道具", {"q": "会議"}), BOUNDARY]),
    ("引く先と違う所を探しただけ", [use("Grep", {"pattern": "会議", "path": "/x/作り物のコード"})]),
    ("前に出した画面は跡に数えない", [use("AskUserQuestion", {"questions": [{"question": "作り物の記録を引く道具"}]})]),
]


@pytest.mark.parametrize("name,rows", PRIOR_BAD, ids=[c[0] for c in PRIOR_BAD])
def test_prior_ask_引いた跡の無い画面は出す前に止め引き方を返す(env, tmp_path, name, rows):
    lookup_values(env, tmp_path)
    why = deny_reason(env, ask_with(prior_log(tmp_path, *rows)))
    assert "引いた跡が会話ログに無い" in why and "聞く前に引く" in why, why
    assert "guard.ask_prior_exempt" in why and "画面はまだ人に出ていない" in why


PRIOR_GOOD = [
    ("記録を引いた", [use("作り物の記録を引く道具", {"q": "会議の数え方"})]),
    ("問いの表を grep した", [use("Grep", {"pattern": "会議", "path": "/x/問いの表.md"})]),
    ("引いた後に他の道具を使った", [use("作り物の記録を引く道具", {}), use("Read", {"file_path": "/x/a"})]),
    ("前の頼みで引いた", [use("作り物の記録を引く道具", {"q": "会議"}), owner("次の作り物の頼み", "u2")]),
    ("引いた後に子の窓の知らせが届いた", [use("作り物の記録を引く道具", {"q": "会議"}), NOTICE]),
    ("縮めた境より後に引いた", [BOUNDARY, SUMMARY, use("作り物の記録を引く道具", {"q": "会議"})]),
]


@pytest.mark.parametrize("name,rows", PRIOR_GOOD, ids=[c[0] for c in PRIOR_GOOD])
def test_prior_ask_この窓の文脈の中で引いた跡があれば通す(env, tmp_path, name, rows):
    lookup_values(env, tmp_path)
    assert deny_reason(env, ask_with(prior_log(tmp_path, *rows))) == ""


def test_prior_ask_同じ頼みの中で止めるのは上限までで新しい頼みで数え直す(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = prior_log(tmp_path)
    assert deny_reason(env, ask_with(tpath)) and deny_reason(env, ask_with(tpath))
    assert deny_reason(env, ask_with(tpath)) == ""          # 3 回目は通す（引く道具が無い窓が回り続けない）
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1"), owner("次の作り物の頼み", "u2")])
    assert deny_reason(env, ask_with(tpath))                 # 新しい頼みでは数え直す


def test_prior_ask_値の表に引く先が無い窓は1回だけ止め値を足す道を返す(env, tmp_path):
    tpath = prior_log(tmp_path)
    why = deny_reason(env, ask_with(tpath))
    assert "guard.ask_prior_lookup" in why and "1 回だけ止める" in why, why
    assert deny_reason(env, ask_with(tpath)) == ""
    assert deny_reason(env, ask_with(tpath, sid="s2"))       # 別の窓では止める


def test_prior_ask_引く要の無い問いは値の表で外せ選択肢の画面の外と助手の中は見ない(env, tmp_path):
    lookup_values(env, tmp_path, ask_prior_exempt=["終わりましたか"])
    tpath = prior_log(tmp_path)
    assert deny_reason(env, ask_with(tpath, q("設定の保存は終わりましたか", header="手の確かめ"))) == ""
    assert deny_reason(env, ask_with(tpath, q("設定の保存は終わりましたか", header="保存"),
                                     q("保存の置き場は A にしますか", header="保存"))), "外さない問いが混ざれば照らす"
    assert deny_reason(env, {"tool_name": "Bash", "session_id": "s1", "transcript_path": tpath,
                             "tool_input": {"command": "echo"}}) == ""
    d = tmp_path / "subagents"
    d.mkdir()
    assert deny_reason(env, ask_with(write_log(d / "a.jsonl", [owner("作り物", "u1")]))) == ""


