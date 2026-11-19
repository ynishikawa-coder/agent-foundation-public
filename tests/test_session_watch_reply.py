"""返事の中身の差し戻し（session-watch の Stop の hook）: 平文の問い・中の言葉・時刻・完了の言い切り・題の材料・鍵。

止める側（わざと悪い返事）と止めない側（正しい返事の型）を両方置く。会話ログの作り物と口は test_session_watch と同じ物を使う。
"""
import json
import re

import pytest

from test_session_watch import CLOUD, LOGS, OK_REPLY, rows, set_title, stop_data, stop_env, sw


def test_返し先が別の窓の子窓には親が付けた題を付け直すよう知らせる(tmp_path):
    """親が create_session で付けた題は会話ログに無く、返事の差し戻しが照らせない＝付け直させる。
    子の窓かは頼みの文（写し）と頼みの行の記録（別の窓から来た）の両方で決める。"""
    log = tmp_path / "child.jsonl"
    row = {"type": "user", "message": {"content": "作り物を見て（親窓 session_X の子）"}, "origin": {"kind": "task-notification"}}
    log.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    text = sw.remind({"prompt": "作り物を見て（親窓 session_X の子）", "transcript_path": str(log)}, CLOUD)
    assert text and "set_session_title" in text and "付け直す" in text


@pytest.mark.parametrize("origin", [None, {"kind": "human"}])
def test_注入_人が貼った引き継ぎの文では子窓の知らせにしない(tmp_path, origin):
    """オーナーが引き継ぎの文を貼った窓（記録が人・記録なし）は、文に親窓が在っても子の窓の知らせにしない。"""
    log = tmp_path / "owner.jsonl"
    row = {"type": "user", "message": {"content": "作り物を見て（親窓 session_X の子）"}}
    if origin:
        row["origin"] = origin
    log.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    text = sw.remind({"prompt": row["message"]["content"], "transcript_path": str(log)}, CLOUD)
    assert text and "付け直す" not in text
    assert sw.remind({"prompt": row["message"]["content"]}, CLOUD) and "付け直す" not in sw.remind(
        {"prompt": row["message"]["content"]}, CLOUD)


# ── 返事の中身の差し戻し（平文の問い・中の言葉・時刻・完了の言い切り・題の材料・秘密）──
def owner_log(tmp_path, rs=None):
    """返し先がオーナーの窓（🙋 の題を会話ログで付けた）の会話ログ。"""
    log = tmp_path / "owner.jsonl"
    rs = rows("owner_ok.jsonl") if rs is None else rs
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rs) + "\n", encoding="utf-8")
    return str(log)


def stopped(tmp_path, text, rs=None, env=None):
    """差し戻した札の並び（差し戻さなければ []）。"""
    reason = sw.stop(stop_data(text, owner_log(tmp_path, rs)), env or stop_env(tmp_path))
    return sorted({ln.split(":")[0][2:] for ln in (reason or "").splitlines() if re.match(r"^- [a-z]+:", ln)})


def owner_reply(*body, card="✅終わった"):
    return "\n".join((card,) + body + ("AI がこの後やること: なし", "あなたがやること: なし。この窓は閉じて大丈夫です。"))


# 作り物の鍵（形だけ・本物でない）。試験の文に鍵の形をそのまま書かない（公開の検査に当たる）＝組み立てる。
FAKE_KEY = "gh" + "p_" + "A1b2C3d4" * 5


@pytest.mark.parametrize("bad, code", [
    # 1. 平文の問い（選択肢の画面を使わずに本文で聞く）
    (owner_reply("作り物の置き場を A と B のどちらにしますか？", card="⏳待ち（オーナーの答え）"), "plain"),
    ("❓答えて\n作り物の置き場はどちらがよいですか\nAI がこの後やること: なし\nあなたがやること: 答える。これが済むまで置き場の直しに進めません。",
     "plain"),
    # 2. 返事の本文の中の言葉
    (owner_reply("Q202611-67 の問いは答え済みとして降ろした。"), "inner"),
    (owner_reply("#616 の直しを入れた。"), "inner"),
    (owner_reply("続きは session_011ABCdef の窓が持つ。"), "inner"),
    (owner_reply("直し_0020 を当てた。"), "inner"),
    (owner_reply("先端は 1a21016e8983 です。"), "inner"),
    (owner_reply("E02 の件は直した。"), "inner"),
    # 3. 時刻は日本時間
    (owner_reply("2026-11-19T08:53:00Z に入れた。"), "time"),
    (owner_reply("08:53 UTC に入れた。"), "time"),
    (owner_reply("入れた時刻は 2026-11-19 08:53 です。"), "time"),
    (owner_reply("11/19 17:30 に送った。"), "time"),
    (owner_reply("2026-11-19 17:53+00:00 に送った。"), "time"),
    # 4. 完了の言い切り
    (owner_reply("ほぼ終わった。"), "done"),
    (owner_reply("たぶん直った。"), "done"),
    (owner_reply("大体できた。"), "done"),
    (owner_reply("これで試験は通るはずです。"), "done"),
    (owner_reply("おそらく効いている。"), "done"),
    (owner_reply("次の試験はたぶん通った。"), "done"),                 # 見込みの語が在っても過去の言い切りは数える
    (owner_reply("予定どおり、たぶん直った。"), "done"),
    (owner_reply("明日の分も含めて、ほぼ終わった。"), "done"),
    # 6. 返事に鍵
    (owner_reply("鍵は " + FAKE_KEY + " です。"), "secret"),
    (owner_reply("```", "TOKEN=" + FAKE_KEY, "```"), "secret"),     # コードの囲みの中でも止める
])
def test_返事の中身が崩れると_AI_へ差し戻す(tmp_path, bad, code):
    assert code in stopped(tmp_path, bad)


GOOD_REPLIES = [
    # 普通の終わった返事
    owner_reply("作り物を直した。", "根拠: 作り物の試験が緑。"),
    # URL・コード・path・file 名・版は数えない（核 §2 コード・パス・固有名は英語でよい）
    owner_reply("直しは https://github.com/example/repo/pull/616 です。"),
    owner_reply("`session_watch.py` の `check()` を直した。", "置き場は plugins/session-watch/scripts です。"),
    owner_reply("config/skill-values.json に 1 行足した。版は v0.3.0 のまま。"),
    owner_reply("```", "Q202611-67 2026-11-19T08:53:00Z", "```", "記録の写しは上のとおり。"),
    owner_reply("snake_case の名 reply_exempt を足した。"),
    # 日常の英数字・日付・数
    owner_reply("A4 で 2 枚にした。", "締めは 2026/11/19 です。"),
    owner_reply("画面は 1920x1080 で確かめた。"),
    # 日本時間の時刻
    owner_reply("2026-11-19 17:53 日本時間 に入れた。"),
    owner_reply("2026-11-19 17:53（日本時間）に入れた。"),
    owner_reply("2026-11-19T17:53:00+09:00 に入れた。"),
    owner_reply("日本時間 2026-11-19 17:53 に入れた。"),
    owner_reply("11/19 17:30〜18:00 日本時間 に会う。"),
    owner_reply("所要は 1:30 ほど。毎日 9:00 に回る。"),
    owner_reply("比は 3:2 にした。"),
    # 終わったの言い切り: 終わりの語と別の文の「ほぼ」、引いた言葉、✅ でない札の見込み
    owner_reply("作り物を直した。", "元の誤りはほぼ毎回起きていた。"),
    owner_reply("作り物を直した。", "「ほぼ終わった」と書く返事を差し戻すようにした。"),
    owner_reply("作り物を直した。", "外すはずしの手は値の表に置いた。"),
    "🛑止まった\n鍵が無いので止めた。たぶん鍵を足せば通る。\nAI がこの後やること: なし\nあなたがやること: 鍵を足す。これが済むまで試験に進めません。",
    "⏳待ち（レビューの窓・今日中）\nほぼ終わった。残りはレビューの判定だけ。\nAI がこの後やること: 判定を受けて直す（この窓）\nあなたがやること: なし。この窓はまだ閉じないでください。",
    # 開いた問いは AI の今の読みを添えれば平文でよい／締めの「なし」は問いにしない
    owner_reply("この言葉はどの意味で使いましたか。", "AI の今の読み: 置き場の意味。", card="❓答えて"),
    owner_reply("どちらでも動く形にした。"),
    owner_reply("A と B のどちらが速いかを測り、A にした。"),
    owner_reply("終わったかは記録で確かめた: 試験 93 本が緑。"),
    owner_reply("期限は 11月20日 18:00 日本時間。"),
    owner_reply("済んだ。思ったより早く終わった。"),
    owner_reply("Wi-Fi と PDF の作り物を直した。"),
    owner_reply("会議は 11月19日 10:00 から（日本時間）。"),
    owner_reply("期限は 2026-11-19 17:00 まで、日本時間で。"),
    owner_reply("日本時間で 2026-11-19 17:00 まで。"),
    owner_reply("作り物を直した。次の版はたぶん来週できる。"),
    # 鍵の在り処の名だけ
    owner_reply("鍵は環境の値 GITHUB_TOKEN に在る（値は書かない）。"),
    # 一言の返事
    "作り物は 3 つです。",
]


@pytest.mark.parametrize("good", GOOD_REPLIES)
def test_正しい返事は差し戻さない(tmp_path, good):
    assert stopped(tmp_path, good) == []


def test_返し先が別の窓の窓は中の言葉を見ない_時刻と秘密は見る(tmp_path):
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🤖✅ 作り物の続き")
    rs[0]["message"]["content"] = "作り物の続きを頼む（返し先=session_PARENT01）。"
    ok = owner_reply("PR は #616、先端は 1a21016e8983、続きは session_011ABCdef の窓が持つ。")
    assert stopped(tmp_path, ok, rs) == []
    assert stopped(tmp_path, owner_reply("08:53 UTC に入れた。"), rs) == ["time"]
    assert stopped(tmp_path, owner_reply("鍵は " + FAKE_KEY), rs) == ["secret"]


def test_差し戻しの文に鍵の値を出さない(tmp_path):
    reason = sw.stop(stop_data(owner_reply("鍵は " + FAKE_KEY), owner_log(tmp_path)), stop_env(tmp_path))
    assert "GitHub のトークン" in reason and FAKE_KEY not in reason


def test_差し戻しの文に直し方と誤った時の外し方を出す(tmp_path):
    reason = sw.stop(stop_data(owner_reply("#616 を 08:53 UTC に入れた。"), owner_log(tmp_path)), stop_env(tmp_path))
    assert "[inner]" in reason and "[time]" in reason
    assert "session-watch.watch-log.reply_exempt" in reason and "guard.ask_term_allow" in reason


def test_誤って止まる行は値の表で外せる(tmp_path, monkeypatch):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session-watch": {"watch-log": {"reply_exempt": ["^元の記録:"]}},
                                 "guard": {"ask_term_allow": ["^B202$"]}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    assert stopped(tmp_path, owner_reply("元の記録: 2026-11-19T08:53:00Z", "部屋は B202 です。")) == []
    assert stopped(tmp_path, owner_reply("部屋は C303 です。")) == ["inner"]


def test_中の言葉と秘密の形は正本を直に呼ぶ(monkeypatch):
    """写しを持たない: 正本の形を変えると返事の見分けも変わる。"""
    A, PG = sw.neighbor("ask_shape"), sw.neighbor("public_guard")
    assert A.__file__.endswith("plugins/guard/scripts/ask_shape.py")
    assert PG.__file__.endswith("public-guard/guard.py")
    log = sw.Log(rows("owner_ok.jsonl"))
    monkeypatch.setattr(A, "INNER", A.INNER + (("中の言葉", re.compile("例の関所")),))
    assert "inner" in {c for c, _ in sw.check(log, owner_reply("例の関所を直した。"))}
    monkeypatch.setitem(PG.SECRET_PATTERNS, "作り物の鍵", r"FAKEKEY-\d{4}")
    assert "secret" in {c for c, _ in sw.check(log, owner_reply("FAKEKEY-1234"))}


def test_隣の正本が無ければ黙って抜かず_窓ごとに1回だけ差し戻す(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"ask_shape": None, "guard_common": None, "public_guard": None})
    e = stop_env(tmp_path)
    first = stopped(tmp_path, OK_REPLY, env=e)
    assert first == ["neighbor"]
    assert stopped(tmp_path, OK_REPLY, env=e) == []          # 2 回目からは通す（AI には直せない＝回さない）


def test_隣の正本は入れた_plugin_の形でも見つかる(tmp_path, monkeypatch):
    cache = tmp_path / "plugins" / "cache" / "mk"
    sw_root = cache / "session-watch" / "v1"
    (sw_root / "scripts").mkdir(parents=True)
    (cache / "guard" / "v1" / "scripts").mkdir(parents=True)
    (cache / "guard" / "v1" / "scripts" / "ask_shape.py").write_text("X = 1\n", encoding="utf-8")
    pg = tmp_path / "plugins" / "marketplaces" / "mk" / "public-guard"
    pg.mkdir(parents=True)
    (pg / "guard.py").write_text("X = 1\n", encoding="utf-8")
    monkeypatch.setattr(sw, "PLUGIN_ROOT", str(sw_root))
    assert sw.neighbor_path("ask_shape", {}) == str(cache / "guard" / "v1" / "scripts" / "ask_shape.py")
    assert sw.neighbor_path("public_guard", {}) == str(pg / "guard.py")
    assert sw.neighbor_path("public_guard", {"AF_PUBLIC_GUARD": str(tmp_path / "none.py")}) == str(pg / "guard.py")


def test_クラウドの窓で題が会話ログに無ければ差し戻し_付け直せば通す(tmp_path):
    """題の材料（親が create_session で付けた題）が会話ログの外にある時は、既定で止めて会話ログに載せさせる。"""
    rs = [r for r in rows("owner_ok.jsonl") if "set_session_title" not in json.dumps(r, ensure_ascii=False)]
    cloud = stop_env(tmp_path, CLAUDE_CODE_REMOTE="true")
    reason = sw.stop(stop_data(OK_REPLY, owner_log(tmp_path, rs)), cloud)
    assert reason and sw.NO_TITLE in reason and "get_session" in reason
    assert sw.stop(stop_data(OK_REPLY, owner_log(tmp_path)), stop_env(tmp_path, CLAUDE_CODE_REMOTE="true",
                                                                      AF_SESSION_WATCH_TMP=str(tmp_path / "b"))) is None
    local = [r for r in rs if "claude-code-remote" not in json.dumps(r, ensure_ascii=False)]   # 題の道具を持たない窓
    assert sw.stop(stop_data(OK_REPLY, owner_log(tmp_path, local)), stop_env(tmp_path, AF_SESSION_WATCH_TMP=str(tmp_path / "c"))) is None


def test_値の表に読めない形があっても他の札は黙って抜けず_読めない事を知らせる(tmp_path, monkeypatch):
    """1 つの誤った正規表現で差し戻しが全部抜ける（hook が例外を受けて黙って通す）形に戻すと赤。"""
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session-watch": {"watch-log": {"reply_exempt": ["(", "^元の記録:"]}},
                                 "guard": {"ask_term_allow": ["["]}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    got = stopped(tmp_path, owner_reply("鍵は " + FAKE_KEY, "#616 を 08:53 UTC に入れた。", "元の記録: 2026-11-19T08:53:00Z"))
    assert {"secret", "time", "neighbor"} <= set(got)
    reason = sw.stop(stop_data(owner_reply("鍵は " + FAKE_KEY), owner_log(tmp_path)),
                     stop_env(tmp_path, AF_SESSION_WATCH_TMP=str(tmp_path / "b")))
    assert "reply_exempt に正規表現として読めない形" in reason and "- secret:" in reason


def test_値の表の読み口が無ければ中の言葉を黙って抜かない(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "_loaded", dict(sw._loaded, guard_common=None))
    sw.neighbor("ask_shape"); sw.neighbor("public_guard")
    assert "neighbor" in stopped(tmp_path, owner_reply("#616 を入れた。"))


def test_中の言葉の値の表に読めない形があっても次のターンも中の言葉を止める(tmp_path, monkeypatch):
    """読めない形で inner がまるごと例外で抜け、neighbor は窓ごとに 1 回なので 2 ターン目から黙って通る形に戻すと赤。"""
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"guard": {"ask_term_allow": ["[", "^B202$"], "ask_inner_terms_extra": ["("]}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    e = stop_env(tmp_path)
    first = sw.stop(stop_data(owner_reply("#617 と Q202611-67 を入れた。部屋は B202。"), owner_log(tmp_path)), e)
    assert "- inner:" in first and "ask_term_allow「[」" in first and "B202" not in first.split("- inner:")[1].splitlines()[0]
    second = sw.stop(stop_data(owner_reply("#617 と Q202611-67 を入れた。"), owner_log(tmp_path), sid="s1"), e)
    assert second and "- inner:" in second and "- neighbor:" not in second    # 2 ターン目も止める（知らせは 1 回）


def test_外す形の鍵は値の表の知っている鍵に載る():
    """reply_exempt を土台の知らない鍵（読まれずに黙って効かない）にしない。"""
    import importlib.util
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts" / "values_keys.py"
    spec = importlib.util.spec_from_file_location("af_values_keys", p)
    vk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vk)
    assert vk.unknown({"session-watch": {"watch-log": {"reply_exempt": ["^元の記録:"]}}}) == []
