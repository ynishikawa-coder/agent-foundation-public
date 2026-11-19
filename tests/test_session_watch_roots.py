"""返事の差し戻しの字の形の推し量りの穴（原因の台帳の session-watch の行）を、わざと入れて拒む試験。

- 時刻の「17時53分」の書き方・日本時間の印が別の句の時刻に掛かる形
- 「た、」で切れた前の句の言い切りを、見込みの句に掛ける形
- 頭が 3 字以上の英数字の固有名（COVID19・SHA256）を番号と数える形
- 値の表の読み口（lib/skill_values.py）が無い時に、返し先が別の窓の窓で黙って空の値の表で進む形
- 手の窓が頼んだ窓へ返さずに ✅ で締める形
"""
import copy

import pytest

from test_session_watch import rows, set_last_text, set_title, sw
from test_session_watch_reply import owner_reply, stopped


@pytest.mark.parametrize("bad, code", [
    (owner_reply("2026-11-19 8時53分 に入れた。"), "time"),
    (owner_reply("11月19日 17時5分 に送った。"), "time"),
    (owner_reply("2026-11-19 01:00 に入れ、日本時間 10:00 に再開した。"), "time"),
    (owner_reply("書き直した、ほぼ終わった。"), "done"),
    (owner_reply("PR12 を直した。"), "inner"),
    (owner_reply("ABC123-4 を直した。"), "inner"),
])
def test_穴の形を入れると差し戻す(tmp_path, bad, code):
    assert code in stopped(tmp_path, bad)


@pytest.mark.parametrize("good", [
    owner_reply("2026-11-19 17時53分（日本時間）に入れた。"),
    owner_reply("日本時間 2026-11-19 17時53分 に入れた。"),
    owner_reply("2026-11-19 10:00 日本時間 に入れ、2026-11-19 11:00 日本時間 に再開した。"),
    owner_reply("期限は 2026-11-19 17:00 まで、日本時間で。"),
    owner_reply("書き直した、次の版はたぶん来週できる。"),
    owner_reply("COVID19 と SHA256 の作り物を直した。"),
])
def test_正しい返事は差し戻さない(tmp_path, good):
    assert stopped(tmp_path, good) == []


def test_値の表の読み口が無ければ返し先が別の窓の窓でも黙らない(tmp_path, monkeypatch):
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🤖✅ 作り物の続き")
    rs[0]["message"]["content"] = "作り物の続きを頼む（返し先=session_PARENT01）。"
    monkeypatch.setattr(sw, "_loaded", dict(sw._loaded, skill_values=None))
    sw.neighbor("ask_shape"); sw.neighbor("public_guard")
    found = sw.check(sw.Log(rs), owner_reply("作り物を直した。"))
    assert [c for c, m in found if c == "neighbor" and "skill_values" in m]


HAND_CLOSE = "\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。"


def hand_done(with_send):
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋⏳ 手: 作り物の設定")
    rs = set_last_text(rs, "✅終わった\n済んだ目印（画面の「保存しました」）を確かめ、頼んだ窓へ返した。" + HAND_CLOSE)
    if with_send:
        send = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu9", "name": "mcp__claude-code-remote__send_message",
             "input": {"session_id": "session_PREV03", "message": "済んだ"}}]}}
        rs = rs[:-1] + [send, copy.deepcopy(rs[-1])]
    return sw.check(sw.Log(rs))


def test_手の窓が頼んだ窓へ返さずに終わったで締めると拾う():
    found = [m for c, m in hand_done(False) if c == "title"]
    assert found and "send_message" in found[0]
    assert [c for c, _ in hand_done(True)] == []
