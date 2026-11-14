"""会話ログの点検（plugins/session-watch）が、作り物の会話ログで拾う／拾わないが合うかを見る。"""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

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

def test_手で回す口は拾えば_exit_1_型どおりなら_exit_0():
    run = lambda name: subprocess.run([sys.executable, str(SCRIPT), str(LOGS / name)], capture_output=True, text=True)
    bad = run("plain_unanswered.jsonl")
    assert bad.returncode == 1 and "plain:" in bad.stdout
    assert run("child_ok.jsonl").returncode == 0


def test_返事を止める_hook_を持たず_知らせる_hook_だけを持つ():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert list(hooks) == ["UserPromptSubmit"]
    assert hooks["UserPromptSubmit"][0]["hooks"][0]["command"].endswith("session_watch.py\" --remind")
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


def test_返し先が別の窓の子窓には題の知らせを出さない():
    assert sw.remind({"prompt": "作り物を見て（親窓 session_X の子）"}, CLOUD) is None


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
