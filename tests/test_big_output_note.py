"""大きな出力の知らせ（plugin session-watch の --remind・止めない）: 前の番の道具の出力が値の表の線
session-watch.watch-log.big_output_chars 以上なら、file へ書いて要る所だけ読む・読むだけの調べは助手へと窓に 1 回だけ知らせる。
新しい hook の口は足さない（既にある UserPromptSubmit の口に乗せる）。"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "session-watch"
spec = importlib.util.spec_from_file_location("session_watch_big", PLUGIN / "scripts" / "session_watch.py")
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(sw)
SCHEMA = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))


def _turn(prompt, size, as_list=False):
    body = "x" * size
    content = [{"type": "text", "text": body}] if as_list else body
    return [{"type": "user", "message": {"role": "user", "content": prompt}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat big"}}], "usage": {"input_tokens": 100}}},
            {"type": "user", "toolUseResult": {}, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": content}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "読んだ"}],
                                              "usage": {"input_tokens": 200}}}]


def _remind(tmp_path, rows, sid="s"):
    p = tmp_path / ("%s.jsonl" % sid)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return sw.remind({"transcript_path": str(p), "session_id": sid}, {"AF_SESSION_WATCH_TMP": str(tmp_path / "sw")}) or ""


def test_線は_schema_の既定と値の表から読む(tmp_path, monkeypatch):
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    spec_ = SCHEMA["sections"]["session-watch"]["skills"]["watch-log"]["keys"]["big_output_chars"]
    assert spec_["type"] == "int" and sw.load_values({})["big_output_chars"] == spec_["default"]
    tbl = tmp_path / "v.json"
    tbl.write_text(json.dumps({"session-watch": {"watch-log": {"big_output_chars": 50}}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(tbl))
    assert sw.load_values({})["big_output_chars"] == 50
    assert "道具の出力が 1 つで 60 字" in _remind(tmp_path, _turn("読んで", 60))


def test_線の手前では知らせず_越えたら_1_回だけ(tmp_path, monkeypatch):
    """注入: 線の手前で知らせる・同じ窓で 2 度知らせる、のどちらも赤。"""
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    line = sw.load_values({})["big_output_chars"]
    assert "道具の出力が" not in _remind(tmp_path, _turn("読んで", line - 1), sid="a")
    text = _remind(tmp_path, _turn("読んで", line, as_list=True), sid="b")
    assert sw.BIG_NOTE % line in text and "file" in text and "助手" in text
    assert "道具の出力が" not in _remind(tmp_path, _turn("読んで", line), sid="b")


def test_前の番だけを見る(tmp_path, monkeypatch):
    """注入: 前の前の番の大きな出力でまた知らせたら赤（知らせは今の動きに合わせる）。"""
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    line = sw.load_values({})["big_output_chars"]
    assert "道具の出力が" not in _remind(tmp_path, _turn("一", line + 1) + _turn("二", 10), sid="c")


def test_新しい_hook_の口を足さない():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert sorted(hooks) == ["Stop", "UserPromptSubmit"]
