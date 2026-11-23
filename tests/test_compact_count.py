"""1 窓あたりの要約（compact）の回数を数える（plugin session-watch の --compacts・目標は 0）。印の形は実物の Claude Code の
会話ログ: system 行 subtype compact_boundary と、その後の要約の文の user 行 isCompactSummary。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
spec = importlib.util.spec_from_file_location("session_watch_cc", SCRIPT)
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(sw)

BOUNDARY = {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted",
            "compactMetadata": {"trigger": "auto", "preTokens": 190000}}
SUMMARY = {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
           "message": {"role": "user", "content": "This session is being continued from a previous conversation..."}}
TALK = [{"type": "user", "message": {"role": "user", "content": "直して"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "はい"}}]


def test_要約の無い窓は_0():
    assert sw.compacts(TALK) == 0


def test_印と要約の文の組は_1_回():
    """注入: 印と要約の文を別々に数えて 2 にしたら赤。"""
    assert sw.compacts(TALK + [BOUNDARY, SUMMARY] + TALK) == 1
    assert sw.compacts(TALK + [BOUNDARY, SUMMARY] + TALK + [BOUNDARY, SUMMARY]) == 2


def test_片方の形だけでも落とさない():
    """注入: 印だけ・要約の文だけの窓を 0 と数えたら赤（要約の印を見落とさない）。"""
    assert sw.compacts(TALK + [BOUNDARY] + TALK) == 1
    assert sw.compacts(TALK + [SUMMARY] + TALK) == 1
    assert sw.compacts([BOUNDARY, BOUNDARY, SUMMARY]) == 2


def test_助手の会話の印は数えない():
    assert sw.compacts([dict(BOUNDARY, isSidechain=True)]) == 0


def _w(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def test_dir_を渡すと窓ごとの回数を出す(tmp_path):
    _w(tmp_path / "a.jsonl", TALK)
    _w(tmp_path / "b.jsonl", TALK + [BOUNDARY, SUMMARY])
    _w(tmp_path / "b" / "subagents" / "x.jsonl", [BOUNDARY])
    r = subprocess.run([sys.executable, str(SCRIPT), "--compacts", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert "0\t%s" % (tmp_path / "a.jsonl") in lines
    assert "1\t%s" % (tmp_path / "b.jsonl") in lines
    assert "要約の起きた窓: 1 / 2（目標 0）" in lines


def test_読めない_無い時は黙って緑にしない(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "--compacts", str(tmp_path / "none.jsonl")], capture_output=True, text=True)
    assert r.returncode == 2
    r = subprocess.run([sys.executable, str(SCRIPT), "--compacts", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 2
