"""完了の 4 状態と返事の 1 行目の札の対応は細目 §7 の表の 1 か所（返事の見張りも直に読む・注入の試験）。"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAIMOKU = ROOT / "plugins" / "core" / "細目.md"
SW_PATH = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("sw_state_cards", SW_PATH)
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


def test_細目の表に_4_状態の_1_行目が在る():
    rows = sw.state_lines(str(SAIMOKU))
    assert rows == {"終わった": "✅終わった", "一部": "✅終わった（一部）", "止めた": "🛑止まった",
                    "続けられない": "🛑止まった（続けられない）"}
    text = SAIMOKU.read_text(encoding="utf-8")
    assert "- **4 状態と 1 行目の札** — 上の表の右の欄が、完了の 4 状態を返事の 1 行目（核 §5 の 4 札）でどう書くかの正本。道具（返事の見張り）もこの欄を直に読む（形を自分で持たない）。" in text


def test_見張りは表の形を写さない():
    code = SW_PATH.read_text(encoding="utf-8")
    assert "終わった\\s*[（(]\\s*一部" not in code and "DONE_LINE" not in code


def test_表を替えると見張りが従う(tmp_path):
    t = SAIMOKU.read_text(encoding="utf-8").replace("| `✅終わった（一部）` |", "| `⏳待ち（一部）` |")
    alt = tmp_path / "細目.md"
    alt.write_text(t, encoding="utf-8")
    rows = sw.state_lines(str(alt))
    done = sw.done_line(rows)
    assert done.match("✅終わった（一部）") and rows["一部"] == "⏳待ち（一部）"
    orig = sw.done_line(sw.state_lines(str(SAIMOKU)))
    assert orig.match("✅ 終わった") and not orig.match("✅終わった（一部）")


def test_表が崩れたら照らさずに通さない(tmp_path):
    alt = tmp_path / "細目.md"
    alt.write_text(re.sub(r"^\| 一部 .*\n", "", SAIMOKU.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
    assert sw.state_lines(str(alt)) is None
    assert sw.state_lines(str(tmp_path / "無い.md")) is None


def test_見張りの文は表を指し_別の対応を持たない():
    for rel in ("plugins/session-watch/skills/watch-log/SKILL.md", "plugins/session-watch/skills/title-mark/SKILL.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "細目 §7 の表の「返事の 1 行目」" in text, rel
        assert "札を ⏳／🛑 にし" not in text and "`🛑止まった`・一部で締める時" not in text, rel
    assert "細目 §7 の表の「返事の 1 行目」（一部・止めた・続けられない）の形にし" in SW_PATH.read_text(encoding="utf-8")
