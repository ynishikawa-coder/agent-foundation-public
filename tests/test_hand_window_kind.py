"""手の窓（作業名が `手:` の窓）の種類は返し先によらず 🙋 で、決まりの文と見張りが同じ 1 つの正本を読むかを見る。

なぜ在るか: 決まり（skill title-mark）が「（親窓 session_… の子）と書いた窓は 🤖」と「手の窓は 🙋⏳ 手:」を別々に書き、
見張り（session_watch.py）も返し先だけで種類を決めていた。親窓が手の窓を立てる頼みに（親窓 … の子）と書くと、
Stop の見張りが 🙋 を 🤖 へ替えろと毎回差し戻し、🤖 に替えると今度は title_shape が 🙋 へ戻せと差し戻した。
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
SKILL = ROOT / "plugins" / "session-watch" / "skills" / "title-mark" / "SKILL.md"
DETAIL = ROOT / "plugins" / "core" / "細目.md"

spec = importlib.util.spec_from_file_location("session_watch_hand_kind", SCRIPT)
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(sw)

CHILD = "作り物の手を頼む（親窓 session_PARENT01 の子）。"
TO_WINDOW = "作り物の手を頼む（返し先=session_PARENT01）。"
HAND_REPLY = ("⏳ 待ち\n目的: 作り物の設定を入れる\n手順: 作り物の画面で作り物の値を入れる\n"
              "済んだ目印: 作り物の画面に値が出る\n済んだ後: 頼んだ窓へ返す\n"
              "AI がこの後やること: 済んだ目印を確かめて頼んだ窓へ返す\n"
              "あなたがやること: 上の手順。これが済むまで 作り物の続き に進めません")


def hand_log(tmp_path, first, title):
    rows = [
        {"type": "user", "message": {"role": "user", "content": first}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__claude-code-remote__set_session_title",
             "input": {"session_id": "session_HAND01", "title": title}}]}},
        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                                                  "content": "ok"}]}, "toolUseResult": {"ok": True}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": HAND_REPLY}]}},
    ]
    p = tmp_path / "hand.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def stop_reason(tmp_path, first, title):
    env = {"CLAUDE_CODE_REMOTE": "true", "AF_SESSION_WATCH_TMP": str(tmp_path / "tmp")}
    return sw.stop({"transcript_path": str(hand_log(tmp_path, first, title)), "session_id": "session_HAND01",
                    "last_assistant_message": HAND_REPLY}, env)


def test_親窓の子と書いた手の窓が_人の印_なら_Stop_は通す(tmp_path):
    assert stop_reason(tmp_path, CHILD, "🙋⏳ 手: 作り物の設定") is None


def test_返し先が窓の手の窓も_人の印_なら_Stop_は通す(tmp_path):
    assert stop_reason(tmp_path, TO_WINDOW, "🙋⏳ 手: 作り物の設定") is None


def test_手の窓にわざと_AI_の印_を付けると_Stop_が差し戻す(tmp_path):
    why = stop_reason(tmp_path, CHILD, "🤖⏳ 手: 作り物の設定")
    assert why and "手の窓の題は `🙋⏳ 手: <何を>`" in why
    assert "🤖 へ" not in why and "この窓の種類は 🤖" not in why   # 逆向き（🤖 へ替えろ）の差し戻しを出さない


def test_種類の正本は手の窓を返し先より先に見る():
    assert sw.window_kind(CHILD, "🙋⏳ 手: 作り物") == sw.HUMAN
    assert sw.window_kind(CHILD, "🤖⏳ 手: 作り物") == sw.HUMAN
    assert sw.window_kind(CHILD, "🤖 作り物の作業") == sw.AI
    assert sw.window_kind("返し先=オーナー", None) == sw.HUMAN
    assert sw.window_kind("作り物を直して", None) is None


def test_手の窓でない子の窓に_人の印_を付けると今までどおり差し戻す(tmp_path):
    why = stop_reason(tmp_path, CHILD, "🙋 作り物の作業")
    assert why and "この窓の種類は 🤖" in why


def test_決まりの文は見張りの正本と同じ文():
    assert "- " + sw.KIND_RULE in SKILL.read_text(encoding="utf-8")


def test_細目は手の窓の種類を書き正本を指す():
    text = DETAIL.read_text(encoding="utf-8")
    assert ("種類は `🙋`＝オーナー／`🤖`＝別の窓か仕組み（手の窓は返し先によらず `🙋`・"
            "決め方は skill `session-watch:title-mark`）。") in text


def test_細目は手の窓の作業名の形を書く():
    assert "役は作業名に書く（手の窓は `手: <何を>`）。" in DETAIL.read_text(encoding="utf-8")
