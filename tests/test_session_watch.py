"""会話ログの点検（plugins/session-watch）が、作り物の会話ログで拾う／拾わないが合うかを見る。"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import re

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "session-watch"
SCRIPT = PLUGIN / "scripts" / "session_watch.py"
LOGS = ROOT / "tests" / "session_watch"

spec = importlib.util.spec_from_file_location("session_watch", SCRIPT)
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True   # 写しの置き場（plugins/）に __pycache__ を作らない＝写しの照らしを汚さない
spec.loader.exec_module(sw)


def rows(name):
    return sw.read_rows(LOGS / name)


def codes(rs):
    return sorted({c for c, _ in sw.check(sw.Log(rs))})


def set_title(rs, old, new):
    rs = copy.deepcopy(rs)
    for r in rs:
        for b in (r.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b["input"].get("title") == old:
                b["input"]["title"] = new
    return rs


def set_last_text(rs, text):
    rs = copy.deepcopy(rs)
    rs[-1]["message"]["content"] = [{"type": "text", "text": text}]
    return rs


# ── 拾わない（型どおりの窓）──
def test_子の窓が型どおりに返すと何も拾わない():
    assert codes(rows("child_ok.jsonl")) == []


def test_オーナーへ返す窓が型どおりに返すと何も拾わない():
    assert codes(rows("owner_ok.jsonl")) == []


# ── 拾う ──
def test_平文の問いと答えの無い問いを拾う():
    found = sw.check(sw.Log(rows("plain_unanswered.jsonl")))
    assert sorted({c for c, _ in found}) == ["plain", "unanswered"]
    assert any("作り物の置き場" in m for c, m in found if c == "unanswered")


def test_モーダルで聞き直したターンは平文の問いにしない():
    rs = rows("plain_unanswered.jsonl")
    ask = copy.deepcopy(rs[3])        # 前のターンの AskUserQuestion
    rs = rs[:-1] + [ask, rs[-1]]
    assert "plain" not in codes(rs)


# ── 種類は「オーナーが相手の窓か」（parent_session_id を見ない）──
def test_種類は返し先で決まり立てた窓では決まらない():
    first = rows("owner_ok.jsonl")[0]
    assert sw.kind_of(sw.text_of(first)) == sw.HUMAN
    assert sw.kind_of("作り物を調べて（返し先=session_Y）。", seeded=True) == sw.AI
    assert sw.kind_of("あなたは書く窓です（親窓 session_X の子）。", seeded=True) == sw.AI
    assert sw.kind_of("作り物を直して") is None
    assert sw.kind_of("作り物を直して", seeded=True) is None
    assert sw.kind_of("作り物の続き（返し先=オーナー）", seeded=True) == sw.HUMAN


def test_parent_session_id_が在っても返し先がオーナーなら_AI_の題を拾う():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🤖 作り物の続き")
    found = sw.check(sw.Log(rs))
    assert [c for c, _ in found] == ["title"]


def test_題の目印の誤りを拾う():
    base = rows("child_ok.jsonl")
    assert codes(set_title(base, "🤖✅ 作り物の作業", "作り物の作業")) == ["title"]       # 種類が無い
    assert codes(set_title(base, "🤖✅ 作り物の作業", "🤖 作り物の作業")) == ["title"]   # 残りなしなのに ✅ が無い
    assert "title" in codes(set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋🟢 作り物の続き"))  # 表に無い状態の印
    q = set_title(rows("plain_unanswered.jsonl"), "🤖❓ 作り物の置き場", "🤖 作り物の置き場")
    assert any("❓" in m for c, m in sw.check(sw.Log(q[:5])) if c == "title")             # 問いの前に ❓ が無い


def test_締めの2行と1行目の札を拾う():
    c = set_last_text(rows("child_ok.jsonl"), "終わりました。\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。")
    assert codes(c) == ["card"]
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nこの窓: 残りなし")       # 古い 1 行の締め
    assert "close" in codes(c)
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nAI がこの後やること: なし")         # あなたがやることが無い
    assert "close" in codes(c)



def test_あなたがやることは閉じてよいかも進めない事も求めない():
    """畳んだ決まり文（「この窓は閉じて大丈夫です」「これが済むまで <何> に進めません」）が無くても close を拾わない。"""
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nAI がこの後やること: なし\nあなたがやること: なし")
    assert "close" not in codes(c)
    c = set_last_text(rows("owner_ok.jsonl"), "⏳待ち（オーナー・今日中）\n設定を頼んだ。\nAI がこの後やること: なし\nあなたがやること: 設定を 1 つ")
    assert "close" not in codes(c)


def test_あなたがやることがある締めでは言い回しの平文の問いを拾う():
    body = "⏳待ち（オーナー・今日中）\n置き場は上の箱と下の箱のどちらがよいか教えてください\n"
    c = set_last_text(rows("owner_ok.jsonl"), body + "AI がこの後やること: なし\nあなたがやること: 上の問いに答える。これが済むまで置き場を作れません。")
    assert sw.is_plain_question(c[-1]["message"]["content"][0]["text"])
    c = set_last_text(rows("owner_ok.jsonl"), body + "AI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。")
    assert not sw.is_plain_question(c[-1]["message"]["content"][0]["text"])

def test_開いた問いは_AI_の今の読みを添えれば平文でも拾わない():
    body = "❓答えて\n言葉の意味を確かめたい。\nAI の今の読み: 作り物の箱は上の箱の事だと読んでいる。\nこの読みで合っていますか？\n"
    tail = "AI がこの後やること: なし\nあなたがやること: 上の問いに答える。これが済むまで置き場を作れません。"
    assert "plain" not in codes(set_last_text(rows("owner_ok.jsonl"), body + tail))
    # 注入: 同じ問いから AI の読みを抜くと拾う
    bare = body.replace("AI の今の読み: 作り物の箱は上の箱の事だと読んでいる。\n", "")
    assert "plain" in codes(set_last_text(rows("owner_ok.jsonl"), bare + tail))


def test_選択肢の画面の問いに分からないが無ければ拾う():
    rs = rows("plain_unanswered.jsonl")
    assert "idk" not in codes(rs)
    # 注入: 「分からない」の選択肢を抜くと拾う
    rs = copy.deepcopy(rs)
    for r in rs:
        for b in (r.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("name") == "AskUserQuestion":
                for q in b["input"]["questions"]:
                    q["options"] = [o for o in q["options"] if "分からない" not in o["label"]]
    found = sw.check(sw.Log(rs))
    assert any(c == "idk" and "作り物の置き場" in m for c, m in found)


def test_手で回す口は拾えば_exit_1_型どおりなら_exit_0():
    run = lambda name: subprocess.run([sys.executable, str(SCRIPT), str(LOGS / name)], capture_output=True, text=True)
    bad = run("plain_unanswered.jsonl")
    assert bad.returncode == 1 and "plain:" in bad.stdout
    assert run("child_ok.jsonl").returncode == 0


def test_知らせる_hook_と返事の形を差し戻す_hook_を持つ():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert list(hooks) == ["UserPromptSubmit", "Stop"]
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["command"].endswith("session_watch.py\" --remind")
    assert hooks["Stop"][0]["hooks"][0]["command"].endswith("session_watch.py\" --stop")
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"] == "session-watch"


# ── 手の窓（題 `✋ <何を>`）──
def test_手の窓に型が欠ければ拾い_揃えば拾わない():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "✋ 作り物の設定")
    close = "\nAI がこの後やること: 済んだら頼んだ窓へ返す（今日中・この窓で）\nあなたがやること: この窓で設定を 1 つする。これが済むまで先へ進めません。"
    bad = set_last_text(rs, "⏳待ち（オーナー・今日中）\n作り物の設定を直してください。" + close)
    found = sw.check(sw.Log(bad))
    assert [c for c, _ in found] == ["hand"] and "済んだ目印" in found[0][1]
    good = set_last_text(rs, "⏳待ち（オーナー・今日中）\n目的: 作り物の設定が動く。\n手順:\n1. 作り物の画面を開く\n"
                             "2. `保存` を押す\n済んだ目印: 画面に「保存しました」が出る\n済んだ後: 頼んだ窓へ返して閉じる。" + close)
    assert codes(good) == []


def test_手の窓でない待ちは型を見ない():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋💤 作り物の続き")
    rs = set_last_text(rs, "⏳待ち（子の窓・今日中）\n子の窓の返しを待つ。\nAI がこの後やること: 子の返しを受けて合流（今日中・この窓で）\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。")
    assert codes(rs) == []


# ── 題の印を付けるよう知らせる（UserPromptSubmit の hook・止めない）──
CLOUD = {"CLAUDE_CODE_REMOTE": "true"}


def test_クラウドの窓で題に種類が無ければ知らせる(tmp_path):
    log = tmp_path / "t.jsonl"
    log.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "作り物を直して（返し先=オーナー）"}},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    text = sw.remind({"transcript_path": str(log)}, CLOUD)
    assert "set_session_title" in text and "🙋（最初の頼みの返し先から）" in text


def test_最初の頼みの前でも知らせ_種類が決まらなければ両方を書く():
    text = sw.remind({"prompt": "作り物を直して"}, CLOUD)
    assert "オーナーと話す窓なら 🙋" in text


def test_題に種類を付けた窓とクラウドでない窓には知らせない():
    assert sw.remind({"transcript_path": str(LOGS / "owner_ok.jsonl")}, CLOUD) is None
    assert sw.remind({"prompt": "作り物を直して"}, {}) is None
    untitled = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "作り物の続き")
    assert not sw.titled(sw.Log(untitled))


def test_知らせる口は止めず_JSON_で隣に出す():
    run = lambda env: subprocess.run([sys.executable, str(SCRIPT), "--remind"], input='{"prompt": "作り物"}',
                                     capture_output=True, text=True, env=env)
    import os
    out = run(dict(os.environ, CLAUDE_CODE_REMOTE="true"))
    assert out.returncode == 0
    body = json.loads(out.stdout)["hookSpecificOutput"]
    assert body["hookEventName"] == "UserPromptSubmit" and "decision" not in out.stdout
    # 読めない入力は窓を止めず（exit 0）、黙りもしない＝見張りが壊れたと 1 回だけ知らせる
    tmp = dict(os.environ, AF_SESSION_WATCH_TMP=str(Path(__import__("tempfile").mkdtemp())))
    bad = subprocess.run([sys.executable, str(SCRIPT), "--remind"], input="壊れた", capture_output=True, text=True, env=tmp)
    assert bad.returncode == 0 and "見張りの --remind が壊れて" in json.loads(bad.stdout)["hookSpecificOutput"]["additionalContext"]
    again = subprocess.run([sys.executable, str(SCRIPT), "--remind"], input="壊れた", capture_output=True, text=True, env=tmp)
    assert again.returncode == 0 and again.stdout == ""


# ── 動かしていない AI がこの後やること（核 §5）──
def test_AI_の残りを書いて動かさずに締めると拾い_子窓を立てれば拾わない():
    close = "\nAI がこの後やること: レビューして合流（今日中・レビューの窓で）\nあなたがやること: なし。この窓は閉じて大丈夫です。"
    rs = set_last_text(rows("owner_ok.jsonl"), "✅終わった（一部）\nPR を出した。" + close)
    assert "rest" in codes(rs)
    spawn = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu9", "name": "mcp__claude-code-remote__create_session", "input": {"title": "🤖 レビュー"}}]}}
    moved = rs[:-1] + [spawn, rs[-1]]
    assert "rest" not in codes(moved)


def test_背で走らせた助手は残りを動かす手に数え_前で待つ助手は数えない():
    close = "\nAI がこの後やること: 調べを受けて直す（今日中・この窓で）\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。"
    rs = set_last_text(rows("owner_ok.jsonl"), "✅終わった（一部）\n調べを頼んだ。" + close)
    agent = lambda bg: {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tuA", "name": "Agent", "input": {"prompt": "作り物", "run_in_background": bg}}]}}
    assert "rest" not in codes(rs[:-1] + [agent(True), rs[-1]])
    assert "rest" in codes(rs[:-1] + [agent(False), rs[-1]])


def test_Workflow_は残りを動かす手に数える():
    close = "\nAI がこの後やること: 流れの返しを受けて直す（今日中・この窓で）\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。"
    rs = set_last_text(rows("owner_ok.jsonl"), "✅終わった（一部）\n流れを回した。" + close)
    wf = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tuW", "name": "Workflow", "input": {"script": "作り物"}}]}}
    assert "rest" in codes(rs)
    assert "rest" not in codes(rs[:-1] + [wf, rs[-1]])


# ── 頼んだ窓のあなたがやること（手の窓の URL だけ・細目 §4）──
AI_DONE = "\nAI がこの後やること: なし\n"
STEPS = [
    "あなたがやること: 1. 作り物の画面を開く 2. 値を貼る。これが済むまで合流に進めません。",
    "あなたがやること: 作り物の設定を開いて、下の値を貼って保存を押す。これが済むまで合流に進めません。\n```\n作り物の値\n```",
    "あなたがやること: 設定 → 作り物 → 追加 で値を入れる。これが済むまで合流に進めません。",
]
NO_STEPS = [
    "あなたがやること: 手の窓 https://claude.ai/code/session_HAND01 で設定を 1 つする。これが済むまで合流に進めません。",
    "あなたがやること: なし。この窓は閉じて大丈夫です。",
    "あなたがやること: 上の選択肢の画面で問いに答える。これが済むまで合流に進めません。",
    "あなたがやること: 作り物の PR を見る。これが済むまで合流に進めません。",
    "あなたがやること: 上の選択肢の画面で 1) か 2) を選んで答える。これが済むまで合流に進めません。",
    "あなたがやること: 1.5 時間後に作り物の PR を見る。これが済むまで合流に進めません。",
]


def reply(rs, owner):
    return set_last_text(rs, "⏳待ち（オーナー・今日中）\n作り物の PR を出した。" + AI_DONE + owner)


def test_あなたがやることに手順を直に書けば拾い_URL_なし_問いだけは拾わない():
    rs = rows("owner_ok.jsonl")
    for owner in STEPS:
        found = [m for c, m in sw.check(sw.Log(reply(rs, owner))) if c == "hand"]   # 締めの後のコードブロックは close も拾う
        assert len(found) == 1 and "手の窓の URL だけ" in found[0] and "細目 §4" in found[0], owner
    for owner in NO_STEPS:
        assert "hand" not in codes(reply(rs, owner)), owner


def test_手の窓自身のあなたがやることは手順を見ない():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "✋ 作り物の設定")
    body = "⏳待ち（オーナー・今日中）\n目的: 作り物が動く。\n手順:\n1. 開く\n済んだ目印: 出る\n済んだ後: 返す。"
    rs = set_last_text(rs, body + "\nAI がこの後やること: 済んだら返す（今日中・この窓で）\n"
                       "あなたがやること: 上の手順 1 を開いて押す。これが済むまで先へ進めません。")
    assert "hand" not in codes(rs)
    assert sw.remind_hand(sw.Log(rs)) is None


def test_前の返事に手順を直に書いた窓へ次の頼みで知らせる(tmp_path):
    rs = reply(rows("owner_ok.jsonl"), STEPS[0])
    log = tmp_path / "t.jsonl"
    nxt = {"type": "user", "message": {"role": "user", "content": "次を頼む"}}
    for extra in ([], [nxt]):            # 新しい頼みが記録に載る前でも後でも、前の返事を見る
        log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs + extra), encoding="utf-8")
        text = sw.remind({"transcript_path": str(log)}, CLOUD)
        assert text and text.startswith("[session-watch] 前の返事の") and "✋ <何を>" in text
        assert "set_session_title" not in text          # 題は付いている＝題の知らせと重ねない
    ok = reply(rows("owner_ok.jsonl"), NO_STEPS[0])
    log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ok), encoding="utf-8")
    assert sw.remind({"transcript_path": str(log)}, CLOUD) is None
    log.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rs), encoding="utf-8")
    assert sw.remind({"transcript_path": str(log)}, {}) is None   # クラウドでない窓には出さない


def test_一言で済む返事は札と締めを求めない():
    """細目 §5: 札も締めも無い 3 行以下の返事（問いを出していない）は card・close を拾わない。"""
    c = set_last_text(rows("child_ok.jsonl"), "はい、main の先端は d7b1191 です。")
    assert not {"card", "close"} & set(codes(c))
    c = set_last_text(rows("child_ok.jsonl"), "はい。\n枝は claude/20261119-x です。\n試験は通っています。")
    assert not {"card", "close"} & set(codes(c))


def test_一言の外は今までどおり札と締めを求める():
    """古い形に戻す注入: 4 行以上・札を付けた短い返事・締めだけ書いた短い返事は、今までどおり拾う。"""
    c = set_last_text(rows("child_ok.jsonl"), "はい。\n枝は作り物です。\n試験は通っています。\nPR も出しました。")
    assert {"card", "close"} <= set(codes(c))
    c = set_last_text(rows("child_ok.jsonl"), "✅終わった\nPR を出した。")
    assert "close" in codes(c)
    c = set_last_text(rows("child_ok.jsonl"), "終わりました。\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。")
    assert "card" in codes(c)


def test_問いを出したターンは短くても札を求める():
    rs = rows("plain_unanswered.jsonl")
    ask = copy.deepcopy(rs[3])   # 選択肢の画面を出した行
    assert ask["message"]["content"][0]["name"] == "AskUserQuestion"
    rs = set_last_text(rs, "選んでください。")
    rs.insert(len(rs) - 1, ask)  # 最後のターンで問いを出してから短く締める
    assert sw.Log(rs).turn_asked()
    assert "card" in codes(rs)


# ── 返事の形の崩れを知らせる（Stop の hook が置き、次の頼みの時に出す・差し戻さない）──
OK_REPLY = ("✅終わった\n作り物を直した。\n根拠: 作り物の試験が緑。\nAI がこの後やること: なし\n"
            "あなたがやること: なし")


def stop_env(tmp_path, **extra):
    return dict({"AF_SESSION_WATCH_TMP": str(tmp_path / "sw")}, **extra)


EMPTY_LOG = Path(__import__("tempfile").mkdtemp()) / "empty.jsonl"   # 在るが中身の無い会話ログ（無い会話ログは nolog で知らせる）
EMPTY_LOG.write_text("", encoding="utf-8")


def stop_data(text, tpath=str(EMPTY_LOG), active=False, sid="s1"):
    return {"hook_event_name": "Stop", "session_id": sid, "transcript_path": tpath,
            "stop_hook_active": active, "last_assistant_message": text}


@pytest.mark.parametrize("broken, code", [
    (OK_REPLY.replace("✅終わった\n", "", 1) + "\n作り物の続き。", "card"),         # 1 行目の札が無い
    (OK_REPLY.replace("あなたがやること: なし", ""), "close"),                       # 締めの 2 行が無い
])
def test_返事の形を崩すと知らせるが書き直させない(tmp_path, broken, code):
    note = sw.stop(stop_data(broken), stop_env(tmp_path))
    assert note and ("- %s:" % code) in note and "書き直さない" in note and "次の返事から" in note
    assert note.strip().splitlines()[-1] == sw.ROOT_CAUSE, "知らせが出し直しだけを促す形に戻った"


def test_型どおりの返事と一言の返事は知らせない(tmp_path):
    assert sw.stop(stop_data(OK_REPLY), stop_env(tmp_path)) is None
    assert sw.stop(stop_data("作り物は 3 つです。"), stop_env(tmp_path)) is None


def test_題の印の崩れも知らせ_過ぎた事は知らせない(tmp_path):
    bad = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "作り物の続き")   # 種類の印が無い題
    log = tmp_path / "t.jsonl"
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in bad) + "\n", encoding="utf-8")
    reason = sw.stop(stop_data(OK_REPLY, str(log)), stop_env(tmp_path))
    assert reason and "- title:" in reason
    good = tmp_path / "g.jsonl"
    good.write_text((LOGS / "owner_ok.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    assert sw.stop(stop_data(OK_REPLY, str(good)), stop_env(tmp_path)) is None


def test_知らせは回数で切らず_stop_hook_active_でも同じ(tmp_path):
    """前の形（同じターンで上限まで差し戻して書き直させる）は回数の印を持った。知らせるだけなので数えない。"""
    e, bad = stop_env(tmp_path), "作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"
    first = sw.stop(stop_data(bad), e)
    assert first and all(sw.stop(stop_data(bad, active=True), e) == first for _ in range(4))
    assert not hasattr(sw, "STOP_MAX") and not hasattr(sw, "STOP_OFF")


def test_差し戻した後は書き直した返事だけを締めとして見る():
    rs = rows("owner_ok.jsonl")
    rs.append({"type": "assistant", "message": {"content": [{"type": "text", "text": "作り物を直した。\n崩れた返事。\nあ。\nい。"}]}})
    rs.append({"type": "user", "isMeta": True, "message": {"content": "[session-watch] 返事の形が崩れている"}})
    rs.append({"type": "assistant", "message": {"content": [{"type": "text", "text": OK_REPLY}]}})
    assert sw.Log(rs).closing_text() == OK_REPLY


def test_Stop_の口は何も出さず_次の頼みの時に1回だけ知らせる(tmp_path):
    """注入: Stop の口が decision=block を出す形（返事を書き直させる）に戻すと赤。"""
    import os
    env = dict({k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE"}, AF_SESSION_WATCH_TMP=str(tmp_path / "sw"))
    run = lambda flag, body: subprocess.run([sys.executable, str(SCRIPT), flag], input=body, capture_output=True,  # noqa: E731
                                            text=True, env=env)
    out = run("--stop", json.dumps(stop_data("作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"), ensure_ascii=False))
    assert out.returncode == 0 and out.stdout == ""
    told = run("--remind", json.dumps({"session_id": "s1"}))
    ctx = json.loads(told.stdout)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "UserPromptSubmit" and "- card:" in ctx["additionalContext"]
    assert run("--remind", json.dumps({"session_id": "s1"})).stdout == ""          # 1 回だけ
    assert run("--stop", json.dumps(stop_data(OK_REPLY), ensure_ascii=False)).stdout == ""
    assert run("--remind", json.dumps({"session_id": "s1"})).stdout == ""          # 崩れの無い返事は知らせない
    bad = run("--stop", "壊れた")
    assert bad.returncode == 0 and bad.stdout == ""


def test_問いの前に題を問いの印にしなかった過ぎた事は知らせない(tmp_path):
    """手で回す点検は拾うが、今の題を直しても消えない事なので知らせない。"""
    def tool(name, inp):
        return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}}
    q = {"question": "作り物の置き場を A と B のどちらにしますか", "header": "置き場",
         "options": [{"label": "A（推奨）"}, {"label": "B"}, {"label": "分からない"}]}
    rs = [{"type": "user", "message": {"content": "作り物を直して（返し先=オーナー）"}},
          tool("mcp__claude-code-remote__set_session_title", {"title": "🙋 作り物"}),
          tool("AskUserQuestion", {"questions": [q]}),
          {"type": "user", "toolUseResult": {"questions": [q], "answers": {q["question"]: "A（推奨）"}},
           "message": {"content": [{"type": "tool_result", "content": "A"}]}}]
    log = tmp_path / "t.jsonl"
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rs) + "\n", encoding="utf-8")
    assert any(c == "title" and m.startswith(sw.ASK_BEFORE) for c, m in sw.check(sw.Log(rs), OK_REPLY))
    assert sw.stop(stop_data(OK_REPLY, str(log)), stop_env(tmp_path)) is None


def test_拾えば最後の行で根治の入口を指し拾わなければ出さない():
    """拾った物を出し直すだけで返す古い形（指す行が無い）に戻すと赤。"""
    bad = subprocess.run([sys.executable, str(SCRIPT), str(LOGS / "plain_unanswered.jsonl")], capture_output=True, text=True)
    assert bad.returncode == 1 and bad.stdout.strip().splitlines()[-1] == sw.ROOT_CAUSE
    assert "細目 §3「まず構造を疑う」" in sw.ROOT_CAUSE
    ok = subprocess.run([sys.executable, str(SCRIPT), str(LOGS / "child_ok.jsonl")], capture_output=True, text=True)
    assert ok.returncode == 0 and sw.ROOT_CAUSE not in ok.stdout


def test_知らない印と読めないログは拾う物なしに化けず止まる(tmp_path):
    for arg in ("--remnd", str(tmp_path / "無いログ.jsonl")):
        p = subprocess.run([sys.executable, str(SCRIPT), arg], capture_output=True, text=True)
        assert p.returncode == 2 and p.stdout == "", arg


def test_hook_の口の印は知らない印の照らしより前で通る(tmp_path):
    """--remind と --stop を知らない印の照らしの後ろに置くと、hook が exit 2 で落ちる＝その形に戻すと赤。"""
    import os
    env = dict(os.environ, AF_SESSION_WATCH_TMP=str(tmp_path / "sw"))
    for flag in ("--remind", "--stop"):
        p = subprocess.run([sys.executable, str(SCRIPT), flag], input="{}", capture_output=True, text=True, env=env)
        assert p.returncode == 0 and "使い方" not in p.stderr, flag
    out = subprocess.run([sys.executable, str(SCRIPT), "--stop"], env=env, capture_output=True, text=True,
                         input=json.dumps(stop_data("作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"), ensure_ascii=False))
    assert out.stdout == "" and list((tmp_path / "sw").glob("*.note"))  # hook_stop に届き、知らせを置いた
