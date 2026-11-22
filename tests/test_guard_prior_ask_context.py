"""guard の prior_ask: 助手に引かせた跡を数え、読めない行を黙って捨てず、知らせ・要約の行で頼みを数え直さないか（注入の試験）。

意図: 問いの前に決定の記録と問いの表を引かせる。
課題: 助手に引かせた時に引いたのに問いを止め、読めない行を黙って捨て、知らせの行で上限を数え直していた（原因の台帳の行）。
原因: 助手のログを見ず、読めない行を捨て、「人の行」を origin の欠けで見分けていた。
"""
from test_guard import deny_reason, env, write_log  # noqa: F401  （env は fixture）
from test_guard_prior_ask import BOUNDARY, NOTICE, SUMMARY, ask_with, lookup_values, owner, prior_log, use


def helper(tmp_path, rows, main="p.jsonl"):
    d = tmp_path / main.rsplit(".", 1)[0] / "subagents"
    d.mkdir(parents=True, exist_ok=True)
    return write_log(d / "agent-x.jsonl", rows)


def test_prior_ask_助手に引かせた跡も数え_縮めた境より前の助手は数えない(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = prior_log(tmp_path)
    helper(tmp_path, [dict(use("作り物の記録を引く道具", {"q": "会議"}), timestamp="2026-11-22T02:00:00Z")])
    assert deny_reason(env, ask_with(tpath)) == ""
    tpath = prior_log(tmp_path, BOUNDARY)          # 境（01:00）より前に引いた助手は今の文脈に無い
    helper(tmp_path, [dict(use("作り物の記録を引く道具", {"q": "会議"}), timestamp="2026-11-22T00:30:00Z")])
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(tpath, sid="s2"))


def test_prior_ask_読めない行は黙って捨てず行の番号を止める文に出す(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = prior_log(tmp_path)
    with open(tpath, "a", encoding="utf-8") as f:
        f.write('{"type": "assistant", "message": 壊れた行\n')
    why = deny_reason(env, ask_with(tpath))
    assert "読めなかった所" in why and "行の番号: 2" in why, why
    hp = helper(tmp_path, [owner("作り物", "h1")])
    with open(hp, "a", encoding="utf-8") as f:
        f.write("壊れた助手の行\n")
    assert "agent-x.jsonl の 1 行" in deny_reason(env, ask_with(tpath, sid="s2"))


def test_prior_ask_知らせの行と要約の行は新しい頼みと数えず上限を数え直さない(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = prior_log(tmp_path)
    assert deny_reason(env, ask_with(tpath)) and deny_reason(env, ask_with(tpath))
    tpath = prior_log(tmp_path, NOTICE, SUMMARY)
    assert deny_reason(env, ask_with(tpath)) == ""           # 人の頼みは u1 のまま＝上限を越えた
