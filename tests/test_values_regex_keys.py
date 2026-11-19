"""値の表の正規表現の鍵（型 regex／regex_why）の注入の試験: 読めない形を入れると、その鍵だけ既定に倒れ、問題に名が出る。"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SV = ROOT / "skill-values" / "skill_values.py"


def test_正規表現の鍵に読めない形を入れるとその鍵は既定に倒れ名指しされる(tmp_path):
    """注入: 値の表の正規表現の並びに壊れた形を入れる→見張りが re.error で黙って通さず、その鍵だけ既定で動き、問題に名が出る。"""
    spec = importlib.util.spec_from_file_location("sv_inj", SV)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = tmp_path / "config"
    cfg.mkdir()
    (tmp_path / ".git").mkdir()
    (cfg / "skill-values.json").write_text(json.dumps({"guard": {"qa_page_exempt": ["docs/(", "ok/"],
        "irreversible_bash_extra": [["[", "x"]], "number_request_exempt": ["^見本"]},
        "session-watch": {"watch-log": {"reply_exempt": ["("]}}}), encoding="utf-8")
    got, problems = mod.section("guard", strict=False, starts=[str(tmp_path)], env={})
    assert "qa_page_exempt" not in got and "irreversible_bash_extra" not in got
    assert got["number_request_exempt"] == ["^見本"]
    assert any("qa_page_exempt" in p for p in problems) and any("irreversible_bash_extra" in p for p in problems)
    got2, problems2 = mod.section("session-watch", "watch-log", strict=False, starts=[str(tmp_path)], env={})
    assert "reply_exempt" not in got2 and any("reply_exempt" in p for p in problems2)
