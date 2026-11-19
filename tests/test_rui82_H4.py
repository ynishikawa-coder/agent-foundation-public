"""字の並びで照らす類の根治（受け持ち H4: session-watch の会話ログの見張り・guard の選択肢の画面の形と 1 つだけ選ばせる問い）。

注入の試験: 台帳の行の「起きた問題」の形を入れ、今は拾う（止める）ことを見る。前から通していた正しい形は通すことも見る。
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))

import ask_shape  # noqa: E402
import pick_one  # noqa: E402

_spec = importlib.util.spec_from_file_location("session_watch_h4", ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

VALS = {"ask_question_max_chars": 60, "ask_question_max_sentences": 1}


def user(text, **extra):
    return dict({"type": "user", "message": {"role": "user", "content": text}}, **extra)


def said(text, **extra):
    return dict({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}, **extra)


def tool(name, inp, **extra):
    return dict({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": name, "input": inp}]}}, **extra)


def codes(rows, closing=None):
    return [c for c, _ in sw.check(sw.Log(rows), closing)]


OWNER_CLOSE = "\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。"


# ── 行 …fa0bdb9e97c3: クラウドの窓かは道具の名の頭でなく環境の実物（記録の欄 entrypoint）──
def test_クラウドの窓かは記録の欄で決まり_道具の名の頭では決まらない():
    reply = "✅終わった\n作り物を直した。" + OWNER_CLOSE
    remote = [user("作り物を直して", entrypoint="remote"), said(reply, entrypoint="remote")]
    assert any(m.startswith(sw.NO_TITLE) for c, m in sw.check(sw.Log(remote)) if c == "title")
    other_server = [user("作り物を直して"), tool("mcp__other-remote__create_session", {"prompt": "x"}), said(reply)]
    assert not sw.Log(other_server).cloud            # 名の頭が違う server でも、名の頭では決めない
    assert not hasattr(sw, "REMOTE_PREFIX")


# ── 行 …dc9b00e0e297: 締めの中身（済むまで <何> に進めません）──
@pytest.mark.parametrize("owner", [
    "あなたがやること: 確認（済むまで）",                     # 語だけ置いて何に進めないかが無い
    "あなたがやること: 確認。これが済むまで <何> に進めません。",   # 置き場の印のまま
    "あなたがやること: 確認。済むまで",
])
def test_済むまでの語だけでは何に進めないかを書いたと数えない(owner):
    rows = [user("作り物を直して"), said("⏳待ち（オーナー）\n確認を頼んだ。\nAI がこの後やること: なし\n" + owner)]
    assert "close" in codes(rows)


@pytest.mark.parametrize("owner", [
    "あなたがやること: 確認。これが済むまで公開に進めません。",
    "あなたがやること: 上の問いに答える。これが済むまで置き場を作れません。",
    "あなたがやること: 設定を 1 つ。これが済むまで先へ進めません。",
])
def test_済むまでの後に何を書けば通す(owner):
    rows = [user("作り物を直して"), said("⏳待ち（オーナー）\n確認を頼んだ。\nAI がこの後やること: なし\n" + owner)]
    assert "close" not in codes(rows)


# ── 行 …caef91504869: 窓の種類は言い回しでなく自分でない窓の id ──
@pytest.mark.parametrize("prompt, want", [
    ("作り物を直して（返事先: オーナー）", sw.HUMAN),
    ("作り物を直して（戻り先＝session_01ParentX）", sw.AI),
    ("作り物を直して。返す窓 ｓｅｓｓｉｏｎ＿01ParentY", sw.AI),      # 全角に寄せても読む
    ("作り物を直して（返し先=session_01OwnSelf）", sw.HUMAN),        # 自分の id は返す先でない
])
def test_窓の種類は自分でない窓の_id_で決まる(prompt, want):
    assert sw.kind_of(prompt, own="01OwnSelf") == want


def test_自分の_id_は環境の実物から読む(monkeypatch):
    monkeypatch.setenv(sw.OWN_ID_ENV, "cse_01OwnSelf")
    assert sw.own_id() == "01OwnSelf"
    assert sw.kind_of("続き（session_01OwnSelf）") == sw.HUMAN
    assert not hasattr(sw, "RETURN_TO") and not hasattr(sw, "CHILD_OF")


# ── 行 …fe6226fc6e6b: AI の読みは欄の中身で見る ──
@pytest.mark.parametrize("reading", ["AI の読み: なし", "AI の今の読み:", "AI の今の読み: 〔あとで〕", "ＡＩ の読み： -"])
def test_AI_の読みの札だけ置いた平文の問いを拾う(reading):
    rows = [user("作り物を直して"), said("❓ 答えて\n置き場は上と下のどちらにしますか？\n" + reading)]
    assert "plain" in codes(rows)


def test_AI_の読みに中身があれば開いた問いとして通す():
    rows = [user("作り物を直して"), said("❓ 答えて\nこの言葉はどういう意味で使っていますか？\nAI の今の読み: 置き場の意味だと読んでいる")]
    assert "plain" not in codes(rows)


# ── 行 …ef4edf9886fe: 時刻 ──
@pytest.mark.parametrize("text, hit", [
    ("10:30 PST に入れた", "10:30PST"),
    ("10時30分 UTC に入れた", "10時30分UTC"),
    ("１０：３０ ＵＴＣ に入れた", "10:30UTC"),
    ("10:30 (CEST) に入れた", "10:30CEST"),
    ("10時半 GMT に入れた", "10時半GMT"),
    ("2026-11-19 10時30分 に入れた", "2026-11-19 10時30分"),
])
def test_時刻は字を寄せた後に時分と時差の略の一般の形で読む(text, hit):
    assert hit in [t for t, _ in sw.time_hits(text)]


@pytest.mark.parametrize("text", [
    "10:30 JST に入れた", "10時30分（日本時間）に入れた", "2026-11-19 10時30分 日本時間", "10:30 MTG を入れた",
    "10時間かかった", "10:30 +09:00 に入れた",
])
def test_日本時間と時差でない英字と時間の長さは時刻の崩れにしない(text):
    assert sw.time_hits(text) == []


# ── 行 …fad0fa0dc723: 人の手の手順: 「問い」の語を入れても、選択肢の画面を出していなければ手順を拾う ──
def test_手順に問いの語を入れても選択肢の画面を出していなければ拾う():
    owner = "あなたがやること: 1. 問いの画面を開く 2. 値を貼る。これが済むまで合流に進めません。"
    rows = [user("作り物を直して"), said("⏳待ち（オーナー）\nPR を出した。\nAI がこの後やること: なし\n" + owner)]
    assert "hand" in codes(rows)
    assert not hasattr(sw, "ANSWER")


# ── 行 …e6040305947f: reply_exempt は neighbor の在り処探しでなく値の表の読み口を直に読む ──
def test_reply_exempt_は値の表の読み口を直に読み_guard_の在り処に頼らない(tmp_path, monkeypatch):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session-watch": {"watch-log": {"reply_exempt": ["^元の記録:"]}}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    assert "guard_common" not in sw.NEIGHBORS
    monkeypatch.setattr(sw, "neighbor", lambda name: None)        # guard が無い・版がずれても
    assert sw.reply_exempt({}) == (["^元の記録:"], [])


def test_値の表の読み口が無ければ_reply_exempt_を黙って空にせず名指す(tmp_path, monkeypatch):
    monkeypatch.setattr(sw, "_loaded", {"skill_values": None})
    with pytest.raises(LookupError):
        sw.reply_exempt({})
    found = sw.words(sw.Log([user("作り物")]), "✅終わった\n直した。", {})
    assert any(c == "neighbor" and "reply_exempt" in m for c, m in found)


def test_reply_exempt_の読めない形は鍵ごと既定に倒し名指す(tmp_path, monkeypatch):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session-watch": {"watch-log": {"reply_exempt": ["(", "^元の記録:"]}}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(table))
    pats, bad = sw.reply_exempt({})
    assert pats == [] and bad and "reply_exempt" in bad[0]



def _q(question, labels, multi=False):
    return {"question": question, "multiSelect": multi, "options": [{"label": lb} for lb in labels]}


# ── 行 …efdf119acf77: 推奨の印は見出しの中の印を 1 つの読み手で（記号は字の種類で読む）──
@pytest.mark.parametrize("labels", [("A", "B ★"), ("A ⭐", "B"), ("A", "B 👍"), ("A ◎", "B")])
def test_見出しの記号の印は決まりの形でなければ止める(labels):
    got = ask_shape.findings([_q("作り物の置き場をどちらにしますか", labels + ("分からない",))], VALS)
    assert any(c == "rec" for c, _ in got), labels


def test_決まりの形の印は全角でも通す():
    for lb in ("A（推奨）", "A (推奨)", "A（Recommended）"):
        assert ask_shape.rec_marked(lb) and ask_shape.rec_canon(lb)
    assert not ask_shape.rec_canon("A ★(推奨)")


# ── 行 …fc0ec98cf8e1: 文の数は区切りの類（；・…・改行）を 1 つの読み手で ──
@pytest.mark.parametrize("text", ["表を調べました；回数で数えますか", "表を調べました…回数で数えますか",
                                  "表を調べました\n回数で数えますか", "表を調べました...回数で数えますか"])
def test_文を区切りの類でつないでも2文と数える(text):
    assert len(ask_shape.sentences(text)) == 2
    got = ask_shape.findings([_q(text, ["A", "分からない"])], VALS)
    assert any(c == "long" and "2 文" in m for c, m in got)


def test_完了の言い切りも同じ文の読み手で区切る():
    assert sw.hedge_hits("たぶん直した；確かめた") == ["たぶん直した"]
    assert sw.hedge_hits("確かめた\nたぶん来週に直す予定") == []
