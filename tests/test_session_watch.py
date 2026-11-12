"""会話ログの見張り（plugins/session-watch）が、作り物の会話ログで拾う／拾わないが合うかを見る。"""
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


def test_引き継ぎでオーナーへ渡す窓はオーナーの窓で何も拾わない():
    assert codes(rows("handoff_owner.jsonl")) == []


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
    first = rows("handoff_owner.jsonl")[0]
    assert sw.kind_of(sw.text_of(first)) == sw.HUMAN
    assert sw.kind_of("あなたは後継の窓です（前の窓 session_X・返し先=session_Y）。") == sw.AI
    assert sw.kind_of("あなたは書く窓です（親窓 session_X の子）。") == sw.AI
    assert sw.kind_of("作り物を直して") is None


def test_parent_session_id_が在っても返し先がオーナーなら_AI_の題を拾う():
    rs = set_title(rows("handoff_owner.jsonl"), "🙋 作り物の続き", "🤖 作り物の続き")
    found = sw.check(sw.Log(rs))
    assert [c for c, _ in found] == ["title"]


def test_オーナーの窓のアーカイブの申し出は拾い_AI_の窓の申し出は任意():
    h = set_last_text(rows("handoff_owner.jsonl"), "✅ 終わった\nこの窓: 残りなし → アーカイブしてよい")
    assert "close" in codes(h)
    c = set_last_text(rows("child_ok.jsonl"), "✅終わった\nこの窓: 残りなし")   # 申し出を足すかは各側が決める（核 §5）
    assert codes(c) == []


def test_題の目印の誤りを拾う():
    base = rows("child_ok.jsonl")
    assert codes(set_title(base, "🤖✅ 作り物の作業", "作り物の作業")) == ["title"]       # 種類が無い
    assert codes(set_title(base, "🤖✅ 作り物の作業", "🤖 作り物の作業")) == ["title"]   # 残りなしなのに ✅ が無い
    q = set_title(rows("plain_unanswered.jsonl"), "🤖❓ 作り物の置き場", "🤖 作り物の置き場")
    assert any("❓" in m for c, m in sw.check(sw.Log(q[:5])) if c == "title")             # 問いの前に ❓ が無い


def test_締めの型と1行目の札を拾う():
    c = set_last_text(rows("child_ok.jsonl"), "終わりました。\nこの窓: 残りなし → アーカイブしてよい")
    assert codes(c) == ["card"]
    c = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\n以上です。")
    assert "close" in codes(c)


# ── hook の口 ──
def run_hook(payload):
    return subprocess.run([sys.executable, str(SCRIPT), "--hook"], input=json.dumps(payload),
                          capture_output=True, text=True)


def test_hook_は拾えば1回だけ止め_続きでは止めない():
    path = str(LOGS / "plain_unanswered.jsonl")
    res = run_hook({"transcript_path": path, "stop_hook_active": False})
    assert res.returncode == 0
    out = json.loads(res.stdout)
    assert out["decision"] == "block" and "plain" in out["reason"]
    again = run_hook({"transcript_path": path, "stop_hook_active": True})
    assert again.returncode == 0 and again.stdout == ""


def test_hook_は型どおりの窓と読めない記録では黙る():
    assert run_hook({"transcript_path": str(LOGS / "child_ok.jsonl")}).stdout == ""
    assert run_hook({"transcript_path": str(LOGS / "無い.jsonl")}).stdout == ""


def test_プラグインの_hook_が見張りを指す():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for e in hooks["hooks"]["Stop"] for h in e["hooks"]]
    assert cmds == ['python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_watch.py" --hook']
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"] == "session-watch"


# ── 頼み方（細目 §4「オーナーに手を頼む」・Javis 側 #568 から移した）──
WAIT_CLOSE = "この窓: 残りあり → 待つ（オーナー・今日中）"


def test_AI_に打てる手をオーナーに頼んだ締めを拾う():
    for text, frag in (("新しい窓を立ててください。", "窓を立て"), ("PR #5 を合流しといてください。", "合流し"),
                       ("終わったら main にマージしておいてください", "マージし")):
        rs = set_last_text(rows("handoff_owner.jsonl"), "⏳待ち（オーナー・今日中）\n%s\n%s" % (text, WAIT_CLOSE))
        found = sw.check(sw.Log(rs))
        assert [c for c, _ in found] == ["chore"], (text, found)
        assert frag in found[0][1]


def test_人にしか打てない手や自分で打った報告は頼みすぎにしない():
    for text in ("下の手順で GitHub の画面の Merge pull request を押してください。",
                 "窓を立てて PR を合流しました。",
                 "```\n窓を立ててください\n```",
                 "| 窓を立ててください | 表の中 |",
                 "「窓を立ててください」「合流しといてください」と頼む締めに印を付けます。",
                 "何のため: 新しい許しで動く窓を立ててください。\n手順: 1. 開く\n済んだ目印: 窓が一覧に出る"):
        rs = set_last_text(rows("handoff_owner.jsonl"), "⏳待ち（オーナー・今日中）\n%s\n%s" % (text, WAIT_CLOSE))
        assert "chore" not in codes(rs), text


def test_返し先が別の窓の窓は頼みすぎを見ない():
    rs = set_last_text(rows("child_ok.jsonl"), "✅ 終わった\n親窓で合流してください。\nこの窓: 残りなし → アーカイブしてよい")
    assert codes(rs) == []


def test_題を待ちにしたのに頼み方の型が無ければ拾う():
    rs = set_title(rows("handoff_owner.jsonl"), "🙋 作り物の続き", "🙋⏳ 作り物の続き")
    bad = set_last_text(rs, "⏳待ち（オーナー・今日中）\n作り物の設定を直してください。\n" + WAIT_CLOSE)
    found = sw.check(sw.Log(bad))
    assert [c for c, _ in found] == ["wait"]
    assert "済んだ目印" in found[0][1] and "合流" in found[0][1]
    good = set_last_text(rs, "⏳待ち（オーナー・今日中）\n何のため: 作り物の設定が動く。\n手順:\n1. 作り物の画面を開く\n"
                             "2. `保存` を押す\n済んだ目印: 画面に「保存しました」が出る\n済んだ後: AI が続きを打つ。\n" + WAIT_CLOSE)
    assert codes(good) == []
