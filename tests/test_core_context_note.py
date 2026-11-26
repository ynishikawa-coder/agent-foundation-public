"""器の量の知らせ（plugin core の kaku.py fresh・UserPromptSubmit）: 前の返事の器の量（usage の入力＋キャッシュ作成＋キャッシュ読み）が
線 CONTEXT_LINE を越えたら、細目 §8 の参照を窓に 1 回だけ知らせる。作業は止めない。"""
import io
import json

import pytest

from test_core_plugin import PLUGIN, kaku

LINE = kaku.CONTEXT_LINE


def _reply(n, **extra):
    u = {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": n - 10}
    return dict({"type": "assistant", "message": {"role": "assistant", "content": "はい", "usage": u}}, **extra)


ASK = {"type": "user", "message": {"role": "user", "content": "続けて"}}
BOUNDARY = {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"}
SUMMARY = {"type": "user", "isCompactSummary": True, "message": {"role": "user", "content": "This session is being continued"}}


@pytest.fixture
def ask(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(kaku, "_fresh_text", lambda data: None)  # 土台の新しさの見張りはこの試験の外

    def run(rows, sid="s1", path=None):
        log = tmp_path / f"{sid}.jsonl"
        if rows is not None:
            log.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        data = {"session_id": sid, "transcript_path": str(path or log)}
        monkeypatch.setattr(kaku.sys, "stdin", io.StringIO(json.dumps(data)))
        assert kaku.fresh() == 0
        out = capsys.readouterr().out
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
    return run


def test_線の_1_手前では出ず_越えたら出る(ask):
    """注入: 線の手前で知らせる・越えても知らせない、のどちらも赤。"""
    assert ask([ASK, _reply(LINE)], sid="a") == ""
    text = ask([ASK, _reply(LINE + 1)], sid="b")
    assert text == kaku.CONTEXT_NOTE.format(n=LINE + 1)
    assert "細目 §8" in text and "新しい窓" not in text and "助手" not in text


def test_同じ窓で_2_回出さない(ask):
    assert ask([ASK, _reply(LINE + 1)]) != ""
    assert ask([ASK, _reply(LINE + 1), ASK, _reply(LINE + 5000)]) == ""


@pytest.mark.parametrize("mark", [[BOUNDARY], [SUMMARY], [BOUNDARY, SUMMARY]])
def test_要約の後に返事がまだ無ければ出さない(ask, mark):
    """注入: 要約の前の量で知らせたら赤。"""
    assert ask([ASK, _reply(LINE + 1)] + mark + [ASK]) == ""


def test_助手の行は数えない(ask):
    assert ask([ASK, _reply(1000), _reply(LINE + 1, isSidechain=True)]) == ""


def test_読めない時は黙って_0(ask, tmp_path):
    assert ask(None, path=tmp_path / "無い.jsonl") == ""
    assert ask(None, path=tmp_path) == ""  # dir は読めない
    (tmp_path / "s1.jsonl").write_text("壊れた行\n", encoding="utf-8")
    assert ask(None) == ""


def test_新しい_hook_の口を足さない():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert sorted(hooks) == ["SessionStart", "UserPromptSubmit"]
