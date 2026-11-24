"""窓の題の知らせ（plugin core の title.py・UserPromptSubmit）。

問題: 窓の見張り（session-watch）を畳んだ後、人が立てた窓の題に種類と状態の印が付かなくなった（決まりは細目 §4 にだけ在り、
知らせる口が無かった）。ここは作り物の会話の記録で、題が無い窓・前の返事の札と題の状態が食い違う窓に知らせが出て、
合っている窓・手の窓・クラウドでない窓には出ないことを、hooks.json の命令そのものを回して照らす。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "core"
SET = "mcp__claude-code-remote__set_session_title"


def human(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def say(*texts):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": t} for t in texts]}}


def tool(name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t", "name": name, "input": inp}]}}


def result():
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}


def run(tmp_path, log, remote="true"):
    p = tmp_path / "log.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in log), encoding="utf-8")
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    cmd = next(h["command"] for g in hooks["UserPromptSubmit"] for h in g["hooks"] if "/scripts/title.py" in h["command"])
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), HOME=str(tmp_path), CLAUDE_CODE_REMOTE=remote)
    r = subprocess.run(["bash", "-c", cmd], input=json.dumps({"transcript_path": str(p), "prompt": "次"}),
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else None


def titled(title, reply):
    return [human("直して"), tool(SET, {"session_id": "s", "title": title}), result(),
            say("見ます。"), tool("Bash", {"command": "ls"}), result(), say(reply), human("次")]


def test_題をまだ付けていない窓には付けるよう知らせる(tmp_path):
    out = run(tmp_path, [human("pixel-office を付けた")])
    assert out and SET in out and "🙋" in out


def test_立てた時に題が付いた窓は今の題を読んで1回付け直せば知らせが止まる(tmp_path):
    first = [{"type": "user", "message": {"role": "user", "content": "親から: PR を見て"}}]
    out = run(tmp_path, first)
    assert out and "get_session" in out and "同じ題で 1 回" in out
    again = first + [tool(SET, {"title": "🤖 レビュー: x"}), result(), say("見ています。"), human("続けて")]
    assert run(tmp_path, again) is None


def test_前の返事の札と題の状態が食い違えば付け替えるよう知らせる(tmp_path):
    out = run(tmp_path, titled("🙋 題の直し", "✅終わった\n\n直しました。"))
    assert out and "✅" in out and "🙋 題の直し" in out


def test_札と題の状態が合っていれば何も出さない(tmp_path):
    assert run(tmp_path, titled("🙋✅ 題の直し", "✅終わった\n\n直しました。")) is None
    assert run(tmp_path, titled("🤖💤 合流待ち", "💤待ち\n\nCI を待つ。")) is None


def test_途中の実況でなく最後の道具の後の本文の札を見る(tmp_path):
    log = [human("直して"), tool(SET, {"title": "🙋❓ 題の直し"}), result(),
           say("❓答えて ではなく途中の文"), tool("Bash", {}), result(), say("❓答えて\n\nどちらにしますか"), human("A")]
    assert run(tmp_path, log) is None


def test_手の窓と札の無い一言の返事とクラウドでない窓は照らさない(tmp_path):
    assert run(tmp_path, titled("✋ 鍵を入れる", "✅終わった")) is None
    assert run(tmp_path, titled("🙋 題の直し", "はい、そうです。")) is None
    assert run(tmp_path, [human("x")], remote="") is None


def test_読めない記録でも窓を止めない(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text("{壊れた\n", encoding="utf-8")
    env = dict(os.environ, CLAUDE_CODE_REMOTE="true")
    r = subprocess.run(["python3", str(PLUGIN / "scripts" / "title.py")], input=json.dumps({"transcript_path": str(p)}),
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0 and "set_session_title" in r.stdout   # 題が読めない＝付けていない側へ倒して知らせる
