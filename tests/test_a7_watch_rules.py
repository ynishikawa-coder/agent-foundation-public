"""見張りが核・振る舞いの決まりを照らし、要約の後も状態を失わないか（注入の試験）。

番の切り方の正本は guard_common.starts_turn（人が打った行で、要約の行・別の窓の知らせでない）。
どれも直す前の形（is_owner_row で番を切る・同じ窓の問いを「前の窓の問い」に出す・Stop で手の点検の札と
ASK_BEFORE を捨てる・✅ の返事だけ言い切りを照らす・「概ね」を拾わない）に戻すと赤になる。
"""
import importlib.util
import json
import sys
from pathlib import Path

from test_guard import env, hook, write_log, _ask_post  # noqa: F401  （env は fixture）
from test_guard_prior_ask import ask_with, lookup_values, owner, use
from test_guard import deny_reason
from test_session_watch import OK_REPLY, stop_data, stop_env, sw

ROOT = Path(__file__).resolve().parent.parent
GUARD_SCRIPTS = ROOT / "plugins" / "guard" / "scripts"


def _load(name, path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def summary_row(text="This session is being continued from a previous conversation. 推奨 を選ぶ。"):
    """文脈を詰めた後の要約の行（人が打った行ではない）。"""
    return {"type": "user", "isCompactSummary": True, "uuid": "c1", "message": {"content": text}}


# ── 8114a76: 要約・再開で SessionStart がまた来ても、同じ窓の問いを「前の窓の問い」に出さない ──
def test_同じ窓の問いは要約の後に前の窓の問いとして出さず_別の窓へは渡す(env):
    labels = ["A に置く（推奨）", "B に置く", "分からない"]
    hook(env, "post", _ask_post("作り物の置き場を A と B のどちらにしますか", labels, False, "s1"))
    assert hook(env, "start", {"session_id": "s1", "source": "compact"}) == {}
    again = hook(env, "start", {"session_id": "s2", "source": "startup"}).get("additionalContext", "")
    assert "作り物の置き場を A と B のどちらにしますか" in again


# ── 81549cd: 要約の行は番を切らない＝要約の前に引いた跡を消さない ──
def test_要約の行は引いた跡を消さない(env, tmp_path):
    lookup_values(env, tmp_path)
    tpath = write_log(tmp_path / "p.jsonl", [owner("作り物の頼み", "u1"), use("作り物の記録を引く道具", {"q": "会議"}),
                                             summary_row()])
    assert deny_reason(env, ask_with(tpath)) == ""
    # 人が新しく打った頼みは番を切る（跡は数え直す）
    tpath2 = write_log(tmp_path / "p2.jsonl", [owner("作り物の頼み", "u1"), use("作り物の記録を引く道具", {"q": "会議"}),
                                              owner("次の作り物の頼み", "u2")])
    assert "引いた跡が会話ログに無い" in deny_reason(env, ask_with(tpath2))


# ── 81549cd と同じ原因: pick_one のオーナーの言葉に要約の行を数えない ──
def test_オーナーの言葉に要約の行を数えない(tmp_path):
    po = _load("pick_one_a7", GUARD_SCRIPTS / "pick_one.py")
    tpath = write_log(tmp_path / "o.jsonl", [owner("作り物を直して", "u1"), summary_row("要約: 推奨の案で進める")])
    words = po.owner_words(tpath)
    assert "作り物を直して" in words and "推奨の案" not in words


# ── 8131851・819dba3: Stop で手の点検の札と ASK_BEFORE も知らせる ──
def _ask(q, labels):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "a1", "name": "AskUserQuestion",
                                                          "input": {"questions": [{"question": q, "header": "h",
                                                                                   "options": [{"label": x} for x in labels]}]}}]}}


def test_Stop_は手の点検の札も知らせる():
    for c in ("idk", "unanswered", "rest", "hand"):
        assert c in sw.STOP_CODES, c


def test_分からないの無い問いは出したターンだけ知らせる(tmp_path):
    human = lambda t: {"type": "user", "origin": {"kind": "human"}, "message": {"content": t}}  # noqa: E731
    rs = [human("作り物を直して（返し先=オーナー）"), _ask("作り物の置き場は A と B のどちらですか", ["A", "B"])]
    log = write_log(tmp_path / "t.jsonl", rs)
    note = sw.stop(stop_data(OK_REPLY, log), stop_env(tmp_path)) or ""
    assert "- idk:" in note
    later = write_log(tmp_path / "t2.jsonl", rs + [human("続けて")])
    assert "- idk:" not in (sw.stop(stop_data(OK_REPLY, later, sid="s2"), stop_env(tmp_path)) or "")


# ── 81498bb: 「概ね」も拾い、✅ でない返事も照らす ──
def test_概ねと_終わった札でない返事のぼかしを拾う():
    for text in ("✅終わった\n概ね直った。", "💤待ち\nほぼ終わった。残りは判定だけ。", "🛑止まった\nたぶん鍵を足せば通る。"):
        assert "done" in [c for c, _ in sw.words(sw.Log([]), text)], text


# ── 81749c3（推測の行・起きない事を確かめる）: 要約の行は最初の頼みも番もずらさない ──
def test_要約の行は最初の頼みも番もずらさない():
    human = {"type": "user", "origin": {"kind": "human"}, "message": {"content": "作り物を直して（返し先=オーナー）"}}
    title = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0",
                                                           "name": "mcp__claude-code-remote__set_session_title",
                                                           "input": {"title": "🙋 作り物"}}]}}
    rs = [human, title, _ask("作り物の置き場は A と B のどちらですか", ["A", "B", "分からない"])]
    with_summary = rs[:2] + [summary_row()] + rs[2:]
    a, b = sw.Log(rs), sw.Log(with_summary)
    assert b.first_prompt == a.first_prompt
    assert [e for e in b.turn if e[0] != "notice"] == [e for e in a.turn if e[0] != "notice"]
    assert sorted(c for c, _ in sw.check(b, OK_REPLY)) == sorted(c for c, _ in sw.check(a, OK_REPLY))
    assert json.dumps(b.events, ensure_ascii=False).count('"owner"') == 1
