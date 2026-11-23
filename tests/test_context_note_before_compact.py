"""器の量の知らせ（plugin session-watch の --remind）: 自動の要約の線より手前で 1 回だけ、区切って新しい窓へ渡す・読むだけの
調べは助手へと知らせる。線は値の表 session-watch.watch-log.context_note_tokens（既定は schema）だけから読む。止めない。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
spec = importlib.util.spec_from_file_location("session_watch_ctx", SCRIPT)
sw = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(sw)
sp = importlib.util.spec_from_file_location("setup_plugins_ctx", ROOT / "scripts" / "setup_plugins.py")
setup = importlib.util.module_from_spec(sp)
sp.loader.exec_module(setup)
SCHEMA = json.loads((ROOT / "skill-values" / "schema.json").read_text(encoding="utf-8"))


def _log(tmp_path, used, extra=()):
    rows = [{"type": "user", "message": {"role": "user", "content": "直して"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "はい"}],
                                              "usage": {"input_tokens": 10, "cache_creation_input_tokens": 0,
                                                        "cache_read_input_tokens": used - 10, "output_tokens": 5}}},
            *extra]
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return p


def _env(tmp_path):
    return {"AF_SESSION_WATCH_TMP": str(tmp_path / "sw")}


def _remind(tmp_path, log, sid="s1"):
    return sw.remind({"transcript_path": str(log), "session_id": sid}, _env(tmp_path)) or ""


def test_既定の線は要約の線より手前で_schema_に在る():
    keys = SCHEMA["sections"]["session-watch"]["skills"]["watch-log"]["keys"]
    assert keys["context_note_tokens"]["type"] == "int"
    assert 0 < keys["context_note_tokens"]["default"] < setup.COMPACT_WINDOW
    assert sw.load_values({})["context_note_tokens"] == keys["context_note_tokens"]["default"]


def test_線の手前では知らせない(tmp_path, monkeypatch):
    """注入: 線より 1 token 手前で知らせたら赤。"""
    monkeypatch.delenv("SKILL_VALUES", raising=False)
    line = sw.load_values({})["context_note_tokens"]
    assert "[session-watch] この窓の器が" not in _remind(tmp_path, _log(tmp_path, line - 1))


def test_線を越えたら引き継ぎと助手を知らせる(tmp_path):
    line = sw.load_values({})["context_note_tokens"]
    text = _remind(tmp_path, _log(tmp_path, line + 5))
    assert sw.CONTEXT_NOTE % (line + 5) in text
    assert "引き継ぎ" in text and "新しい窓" in text and "助手" in text


def test_同じ窓で_2_度は知らせない_別の窓には知らせる(tmp_path):
    """注入: 同じ窓の次の頼みで 2 度出したら赤。"""
    log = _log(tmp_path, 190_000)
    assert "この窓の器が" in _remind(tmp_path, log)
    assert "この窓の器が" not in _remind(tmp_path, log)
    assert "この窓の器が" in _remind(tmp_path, log, sid="s2")


def test_線は値の表から読む(tmp_path, monkeypatch):
    """注入: 値の表の線を下げたのに既定の線で照らしたら赤。整数でない値は既定のまま。"""
    tbl = tmp_path / "skill-values.json"
    tbl.write_text(json.dumps({"session-watch": {"watch-log": {"context_note_tokens": 1000}}}), encoding="utf-8")
    monkeypatch.setenv("SKILL_VALUES", str(tbl))
    assert sw.load_values({})["context_note_tokens"] == 1000
    assert "この窓の器が" in _remind(tmp_path, _log(tmp_path, 1500))
    tbl.write_text(json.dumps({"session-watch": {"watch-log": {"context_note_tokens": "1000"}}}), encoding="utf-8")
    assert sw.load_values({})["context_note_tokens"] == SCHEMA["sections"]["session-watch"]["skills"]["watch-log"]["keys"][
        "context_note_tokens"]["default"]


def test_値の表の正本が無ければ線を写して持たず知らせない(tmp_path, monkeypatch):
    """注入: 隣の値の表の口が無いのに、手で持った線で知らせたら赤（線は 1 か所）。"""
    monkeypatch.setattr(sw, "neighbor", lambda name: None)
    assert sw.load_values({}) == {}
    assert "この窓の器が" not in _remind(tmp_path, _log(tmp_path, 199_000))


def test_要約の後まだ返事が無ければ要約の前の量で知らせない(tmp_path):
    mark = {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"}
    assert "この窓の器が" not in _remind(tmp_path, _log(tmp_path, 199_000, [mark]))


def test_助手の会話の量は数えない():
    row = {"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 999_999}}}
    assert sw.used_tokens(row) is None


def test_hook_は止めない(tmp_path):
    """--remind は知らせを足すだけ（decision の block を出さない・exit 0）。"""
    log = _log(tmp_path, 199_000)
    r = subprocess.run([sys.executable, str(SCRIPT), "--remind"], input=json.dumps({"transcript_path": str(log), "session_id": "h"}),
                       capture_output=True, text=True, env={"AF_SESSION_WATCH_TMP": str(tmp_path / "h"), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "decision" not in out and "この窓の器が" in out["hookSpecificOutput"]["additionalContext"]
