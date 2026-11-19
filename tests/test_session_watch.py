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
    assert sw.kind_of("作り物を調べて（返し先=session_Y）。") == sw.AI
    assert sw.kind_of("あなたは書く窓です（親窓 session_X の子）。") == sw.AI
    assert sw.kind_of("作り物を直して") is None


def test_parent_session_id_が在っても返し先がオーナーなら_AI_の題を拾う():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🤖 作り物の続き")
    found = sw.check(sw.Log(rs))
    assert [c for c, _ in found] == ["title"]


def test_題の目印の誤りを拾う():
    base = rows("child_ok.jsonl")
    assert codes(set_title(base, "🤖✅ 作り物の作業", "作り物の作業")) == ["title"]       # 種類が無い
    assert codes(set_title(base, "🤖✅ 作り物の作業", "🤖 作り物の作業")) == ["title"]   # 残りなしなのに ✅ が無い
    assert "title" in codes(set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋✅ 作り物の続き"))  # 🙋 に ✅
    q = set_title(rows("plain_unanswered.jsonl"), "🤖❓ 作り物の置き場", "🤖 作り物の置き場")
    assert any("❓" in m for c, m in sw.check(sw.Log(q[:5])) if c == "title")             # 問いの前に ❓ が無い


def test_締めの2行と1行目の札を拾う():
    c = set_last_text(rows("child_ok.jsonl"), "終わりました。\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。")
    assert codes(c) == ["card"]
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nこの窓: 残りなし")       # 古い 1 行の締め
    assert "close" in codes(c)
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nAI がこの後やること: なし")         # あなたがやることが無い
    assert "close" in codes(c)



def test_あなたがやることなしは窓を閉じてよいかを書く():
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nAI がこの後やること: なし\nあなたがやること: なし")
    assert "close" in codes(c)
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\nAI がこの後やること: なし\nあなたがやること: なし。この窓は閉じて大丈夫です。")
    assert "close" not in codes(c)


def test_あなたがやることがあれば済むまで進めない事を書く():
    c = set_last_text(rows("owner_ok.jsonl"), "⏳待ち（オーナー・今日中）\n設定を頼んだ。\nAI がこの後やること: なし\nあなたがやること: 設定を 1 つ")
    assert "close" in codes(c)
    c = set_last_text(rows("owner_ok.jsonl"), "⏳待ち（オーナー・今日中）\n設定を頼んだ。\nAI がこの後やること: なし\n"
                                              "あなたがやること: 設定を 1 つ。これが済むまで公開に進めません。")
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


# ── 手の窓（題 `🙋⏳ 手: <何を>`）──
def test_手の窓に型が欠ければ拾い_揃えば拾わない():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋⏳ 手: 作り物の設定")
    close = "\nAI がこの後やること: 済んだら頼んだ窓へ返す（今日中・この窓で）\nあなたがやること: この窓で設定を 1 つする。これが済むまで先へ進めません。"
    bad = set_last_text(rs, "⏳待ち（オーナー・今日中）\n作り物の設定を直してください。" + close)
    found = sw.check(sw.Log(bad))
    assert [c for c, _ in found] == ["hand"] and "済んだ目印" in found[0][1]
    good = set_last_text(rs, "⏳待ち（オーナー・今日中）\n目的: 作り物の設定が動く。\n手順:\n1. 作り物の画面を開く\n"
                             "2. `保存` を押す\n済んだ目印: 画面に「保存しました」が出る\n済んだ後: 頼んだ窓へ返して閉じる。" + close)
    assert codes(good) == []


def test_手の窓でない待ちは型を見ない():
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋⏳ 作り物の続き")
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
    bad = subprocess.run([sys.executable, str(SCRIPT), "--remind"], input="壊れた", capture_output=True, text=True)
    assert bad.returncode == 0 and bad.stdout == ""


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


def test_返し先が別の窓の子窓には親が付けた題を付け直すよう知らせる():
    """親が create_session で付けた題は会話ログに無く、返事の差し戻しが照らせない＝付け直させる。"""
    text = sw.remind({"prompt": "作り物を見て（親窓 session_X の子）"}, CLOUD)
    assert text and "set_session_title" in text and "付け直す" in text


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
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "🙋⏳ 手: 作り物の設定")
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
        assert text and text.startswith("[session-watch] 前の返事の") and "🙋⏳ 手: <何を>" in text
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


# ── 返事の形の崩れを AI へ差し戻す（Stop の hook・止まるのは AI だけ）──
OK_REPLY = ("✅終わった\n作り物を直した。\n根拠: 作り物の試験が緑。\nAI がこの後やること: なし\n"
            "あなたがやること: なし。この窓は閉じて大丈夫です。")


def stop_env(tmp_path, **extra):
    return dict({"AF_SESSION_WATCH_TMP": str(tmp_path / "sw")}, **extra)


def stop_data(text, tpath="", active=False, sid="s1"):
    return {"hook_event_name": "Stop", "session_id": sid, "transcript_path": tpath,
            "stop_hook_active": active, "last_assistant_message": text}


@pytest.mark.parametrize("broken, code", [
    (OK_REPLY.replace("✅終わった\n", "", 1) + "\n作り物の続き。", "card"),         # 1 行目の札が無い
    (OK_REPLY.replace("あなたがやること: なし。この窓は閉じて大丈夫です。", ""), "close"),  # 締めの 2 行が無い
    (OK_REPLY.replace("この窓は閉じて大丈夫です。", ""), "close"),                    # なしで閉じてよいかが無い
])
def test_返事の形を崩すと_AI_へ差し戻す(tmp_path, broken, code):
    reason = sw.stop(stop_data(broken), stop_env(tmp_path))
    assert reason and ("- %s:" % code) in reason and "書き直す" in reason
    assert reason.strip().splitlines()[-1] == sw.ROOT_CAUSE, "差し戻しが書き直しだけを促す形に戻った"


def test_型どおりの返事と一言の返事は差し戻さない(tmp_path):
    assert sw.stop(stop_data(OK_REPLY), stop_env(tmp_path)) is None
    assert sw.stop(stop_data("作り物は 3 つです。"), stop_env(tmp_path)) is None


def test_題の印の崩れも差し戻し_過ぎた事は差し戻さない(tmp_path):
    bad = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", "作り物の続き")   # 種類の印が無い題
    log = tmp_path / "t.jsonl"
    log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in bad) + "\n", encoding="utf-8")
    reason = sw.stop(stop_data(OK_REPLY, str(log)), stop_env(tmp_path))
    assert reason and "- title:" in reason
    good = tmp_path / "g.jsonl"
    good.write_text((LOGS / "owner_ok.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
    assert sw.stop(stop_data(OK_REPLY, str(good)), stop_env(tmp_path)) is None


def test_差し戻しは同じターンで上限まで_新しい締めでは数え直す(tmp_path):
    e, bad = stop_env(tmp_path), "作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"
    assert sw.stop(stop_data(bad), e)
    assert sw.stop(stop_data(bad, active=True), e)
    assert sw.stop(stop_data(bad, active=True), e) is None       # 上限を越えたら通して届ける
    assert sw.stop(stop_data(bad, active=False), e)               # 次のターンは 0 から


def test_差し戻しは環境変数で切れる(tmp_path):
    bad = "作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"
    assert sw.stop(stop_data(bad), stop_env(tmp_path, AF_SESSION_WATCH_STOP="0")) is None


def test_差し戻した後は書き直した返事だけを締めとして見る():
    rs = rows("owner_ok.jsonl")
    rs.append({"type": "assistant", "message": {"content": [{"type": "text", "text": "作り物を直した。\n崩れた返事。\nあ。\nい。"}]}})
    rs.append({"type": "user", "isMeta": True, "message": {"content": "[session-watch] 返事の形が崩れている"}})
    rs.append({"type": "assistant", "message": {"content": [{"type": "text", "text": OK_REPLY}]}})
    assert sw.Log(rs).closing_text() == OK_REPLY


def test_差し戻す口は_decision_block_で返し壊れた入力では黙る(tmp_path):
    import os
    run = lambda body: subprocess.run([sys.executable, str(SCRIPT), "--stop"], input=body, capture_output=True, text=True,
                                      env=dict({k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE"},
                                               AF_SESSION_WATCH_TMP=str(tmp_path / "sw")))
    out = run(json.dumps(stop_data("作り物を直した。\n根拠は 2 つ。\n1 つ目。\n2 つ目。"), ensure_ascii=False))
    assert out.returncode == 0 and json.loads(out.stdout)["decision"] == "block"
    assert run(json.dumps(stop_data(OK_REPLY), ensure_ascii=False)).stdout == ""
    bad = run("壊れた")
    assert bad.returncode == 0 and bad.stdout == ""


def test_問いの前に題を問いの印にしなかった過ぎた事は差し戻さない(tmp_path):
    """手で回す点検は拾うが、今の題を直しても消えない事なので、差し戻すと回り続ける＝差し戻さない。"""
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
    assert "session_watch.reply_exempt" in reason and "guard.ask_term_allow" in reason


def test_誤って止まる行は値の表で外せる(tmp_path, monkeypatch):
    table = tmp_path / "values.json"
    table.write_text(json.dumps({"session_watch": {"reply_exempt": ["^元の記録:"]},
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
    table.write_text(json.dumps({"session_watch": {"reply_exempt": ["(", "^元の記録:"]},
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
