"""guard の見張りは、壊れた・数えられない時に通す側へ黙って倒れない（注入の試験）。

前の形:
- qa_page: 壊れた JSON の問いのページを「問いのページでない」と見て、qa-html の検査（check.mjs）を飛ばして publish が通った。
- prior_ask: 止めた数の印を残せないと大きい数を返し、数えた振りをして通した。
- outbound: 窓の題・番号だけの頼みの見分けが例外で壊れると stderr に書くだけで、入力はそのまま外へ出た。
"""
import sys
from pathlib import Path

import pytest

GUARD_SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"


def _mod(monkeypatch, name):
    monkeypatch.syspath_prepend(str(GUARD_SCRIPTS))
    sys.modules.pop(name, None)
    return __import__(name)


# ── qa_page ──
@pytest.mark.parametrize("path,raw", [
    ("q.json", '{"questions": [{"question": "作り物", "options": ["a", "b"],}'),
    ("q.html", '<script type="application/json">{"qs": [{"options": ["a"]</script>'),
])
def test_注入_壊れた_JSON_の問いのページは問いのページとして検査へ回す(monkeypatch, path, raw):
    qp = _mod(monkeypatch, "qa_page")
    assert qp.why_question_page(path, raw)


def test_問いの鍵の無い壊れた_JSON_は問いのページでない(monkeypatch):
    qp = _mod(monkeypatch, "qa_page")
    assert qp.why_question_page("x.json", '{"name": ') == ""


# ── prior_ask ──
def test_注入_止めた数の印を残せない時は数えた振りをせず止める(monkeypatch, tmp_path):
    pa = _mod(monkeypatch, "prior_ask")
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("AF_GUARD_TMP", str(blocker))   # 一時 dir が file＝印を書けない
    assert pa._bump("deny", "k") is None
    log = tmp_path / "t.jsonl"
    log.write_text("", encoding="utf-8")
    data = {"tool_name": pa.ASK_TOOL, "session_id": "s1", "transcript_path": str(log),
            "tool_input": {"questions": [{"question": "会議を回数で別に数えますか", "options": [{"label": "a"}]}]}}
    monkeypatch.setattr(pa.G, "patterns", lambda vals, key, flags=0: [])   # 引く先が無い（1 回だけ止める道）
    for _ in range(3):   # 数えられないので、2 回目からも通さない
        assert "数えた振りをせず止めた" in pa.check(data, {})


# ── outbound ──
@pytest.mark.parametrize("broken", ["check_number", "check_title"])
def test_注入_見分けが壊れたら止めて名指す(monkeypatch, broken):
    ob = _mod(monkeypatch, "outbound")
    monkeypatch.setattr(ob, "check_secret", lambda data, vals: "")

    def boom(data, vals):
        raise RuntimeError("作り物の故障")
    for name in ("check_number", "check_title"):
        monkeypatch.setattr(ob, name, boom if name == broken else (lambda data, vals: ""))
    out = ob.check({"tool_name": "x", "tool_input": {}}, {})
    assert "出す前に止めた" in out and broken in out, out
