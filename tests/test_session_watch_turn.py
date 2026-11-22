"""会話ログの点検（plugins/session-watch）の読み口と番の切り方の注入の試験。
番は人が打った行（guard_common.starts_turn）だけで切り、読めない行・照らしの故障は黙って「拾う物なし」にしない。
どれも直す前の形（読めない行を飛ばす・例外を [] にする・問いの後の題を見ない・知らせの行で番を切る・答えを画面の返りだけで
探す）に戻すと赤になる。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
spec = importlib.util.spec_from_file_location("session_watch_turn", SCRIPT)
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(sw)

TITLE = "mcp__claude-code-remote__set_session_title"
SEND = "mcp__claude-code-remote__send_message"


def human(text):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def notice(text):
    return {"type": "user", "origin": {"kind": "session"}, "message": {"content": text}}


def tool(name, inp, tid="t", mid=None):
    m = {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}
    if mid:
        m["id"] = mid
    return {"type": "assistant", "message": m}


def result(tid, err=False, tur=None):
    r = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": "x",
                                                  **({"is_error": True} if err else {})}]}}
    r["toolUseResult"] = tur if tur is not None else ("Error: rejected" if err else {})
    return r


def say(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def ask(q, tid):
    return tool("AskUserQuestion", {"questions": [{"question": q, "header": "h", "options": [
        {"label": "上"}, {"label": "分からない"}]}]}, tid)


def answered(q, tid):
    return result(tid, tur={"questions": [{"question": q}], "answers": {q: "上"}})


def codes(rows, closing=None):
    return [c for c, _ in sw.check(sw.Log(rows), closing)]


def write(tmp_path, lines):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ── 読めない行を黙って飛ばさない ──
def test_読めない行は印として残り_unread_で行の番号を名指す(tmp_path):
    p = write(tmp_path, [json.dumps(human("作り物を直して（返し先=オーナー）"), ensure_ascii=False),
                         '{"type": "assistant", "message": {"content": [', "[1, 2]"])
    rows = sw.read_rows(p)
    assert [r.get(sw.UNREADABLE) for r in rows[1:]] == [2, 3]
    found = [m for c, m in sw.check(sw.Log(rows)) if c == "unread"]
    assert len(found) == 1 and "2 行" in found[0] and "2・3 行目" in found[0]


def test_読めない行は_Stop_でも窓ごとに1回だけ知らせる(tmp_path):
    p = write(tmp_path, [json.dumps(human("作り物（返し先=オーナー）"), ensure_ascii=False), "{壊れ"])
    env = {"AF_SESSION_WATCH_TMP": str(tmp_path / "w")}
    data = {"transcript_path": str(p), "session_id": "s1", "last_assistant_message": "済んだ。"}
    first = sw.stop(data, env) or ""
    assert "- unread:" in first
    assert "- unread:" not in (sw.stop(data, env) or "")


# ── 照らしの故障を「拾う物なし」にしない ──
def test_手で回す口は照らしが壊れたら_exit_2(tmp_path, monkeypatch):
    p = write(tmp_path, [json.dumps(human("作り物（返し先=オーナー）"), ensure_ascii=False)])
    monkeypatch.setattr(sw, "check", lambda log: (_ for _ in ()).throw(TypeError("壊れた")))
    assert sw.main(["sw", str(p)]) == 2


def test_問いの形が崩れた行でも照らしは壊れない(tmp_path):
    p = write(tmp_path, [json.dumps(human("作り物（返し先=オーナー）"), ensure_ascii=False),
                         json.dumps(tool("AskUserQuestion", {"questions": 3}, "a1"), ensure_ascii=False)])
    out = subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True, text=True)
    assert out.returncode in (0, 1), out.stderr


def test_Stop_の口は照らしが壊れても窓を止めず次の頼みで1回だけ知らせる(tmp_path, monkeypatch):
    import io
    monkeypatch.setenv("AF_SESSION_WATCH_TMP", str(tmp_path / "w"))
    monkeypatch.setattr(sw, "stop", lambda data: (_ for _ in ()).throw(AttributeError("壊れた")))
    assert sw.hook_stop(io.StringIO('{"session_id": "s2"}')) == 0
    note = sw.take_note({"AF_SESSION_WATCH_TMP": str(tmp_path / "w")}, "s2") or ""
    assert "見張りの --stop が壊れて" in note and "AttributeError" in note
    assert sw.hook_stop(io.StringIO('{"session_id": "s2"}')) == 0
    assert sw.take_note({"AF_SESSION_WATCH_TMP": str(tmp_path / "w")}, "s2") is None


# ── 問いと同じ返事で付けた題は問いの前に付けたと見る ──
def test_同じ_message_で問いの後に題を問いの印にしても拾わない():
    rows = [human("作り物（返し先=オーナー）"), tool(TITLE, {"title": "🙋 作り物"}, "t0"), result("t0"),
            tool("AskUserQuestion", {"questions": [{"question": "どれ", "options": [{"label": "分からない"}]}]}, "a1", mid="m1"),
            tool(TITLE, {"title": "🙋❓ 作り物"}, "t1", mid="m1")]
    assert not [m for c, m in sw.check(sw.Log(rows)) if m.startswith(sw.ASK_BEFORE)]
    # 別の message で後から付けた題は、問いの時に ❓ でなかった
    rows[-1] = tool(TITLE, {"title": "🙋❓ 作り物"}, "t1", mid="m2")
    rows[-2]["message"]["id"] = "m1"
    assert [m for c, m in sw.check(sw.Log(rows)) if m.startswith(sw.ASK_BEFORE)]


# ── 番は人が打った行だけで切る ──
def test_知らせの行は番を切らない():
    log = sw.Log([human("作り物（返し先=オーナー）"), say("始める"), human("続けて"), say("a"), notice("子の窓の返事"), say("b")])
    assert [k for k, _ in log.turn][:1] == ["text"] and ("notice", "子の窓の返事") in log.turn
    assert log.closing_text() == "b"


def test_手の窓は返した後に知らせが届いても返した跡を見つける():
    title = "🙋⏳ 手: 作り物の設定"
    done = "✅ 終わった\n設定を確かめて返した。\nAI がこの後やること: なし\nあなたがやること: なし"
    rows = [human("作り物の設定を頼む（返し先=オーナー）"), tool(TITLE, {"title": title}, "t0"), result("t0"),
            tool(SEND, {"session_id": "session_X", "message": "済んだ"}, "s1"), result("s1"),
            notice("頼んだ窓の返事: ありがとう"), say(done)]
    assert not [m for c, m in sw.check(sw.Log(rows)) if "send_message" in m]
    # 返した後に人が打った次の頼みでも消えない（手の窓は返すのが 1 回）
    rows[5] = human("閉じて")
    assert not [m for c, m in sw.check(sw.Log(rows)) if "send_message" in m]
    # 一度も返していなければ拾う
    rows = rows[:3] + rows[5:]
    assert [m for c, m in sw.check(sw.Log(rows)) if "send_message" in m]


# ── 答えは画面の返りだけで探さない ──
def test_画面を閉じてチャットで答えた問いは答えの無い問いにしない():
    rows = [human("作り物（返し先=オーナー）"), ask("置き場はどれ", "a1"), result("a1", err=True), human("上の箱で")]
    assert "unanswered" not in codes(rows)
    # 閉じた後に届いたのが知らせの行だけなら、答えは返っていない
    rows[-1] = notice("子の窓の返事")
    assert "unanswered" in codes(rows)


def test_言い直して出し直した問いに答えが返れば元の問いも閉じる():
    rows = [human("作り物（返し先=オーナー）"), ask("置き場はどれ", "a1"), result("a1", err=True),
            ask("置き場は上と下のどちら", "a2"), answered("置き場は上と下のどちら", "a2")]
    assert "unanswered" not in codes(rows)


def test_答えの無いまま閉じられず答えも無い問いは今までどおり拾う():
    rows = [human("作り物（返し先=オーナー）"), ask("置き場はどれ", "a1"), result("a1"), human("続けて")]
    assert "unanswered" in codes(rows)
