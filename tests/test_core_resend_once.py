"""核と振る舞いの既定は、窓が読んだ本文から変わった物だけを 1 回送る（2026-11-22 のトークンの食い過ぎの誤りの類）。

plugin のどこかが main で動くたびに同じ核の全文を送り直すと、窓の文脈に同じ核が何枚も積もる。
"""
from test_core_plugin import PLUGIN, Foundation, _commit, _git


def test_核の本文が変わらない土台の変更では核を送り直さない(tmp_path):
    """注入（2026-11-22 の誤りの類）: 窓が読んだ核と同じ本文の先端を、plugin が動くたびに送り直す形を戻すと赤。
    守りだけの変更が何本 main へ入っても、核と振る舞いの既定の全文は文脈に 1 枚だけ。"""
    f = Foundation(tmp_path)
    _commit(f.work, {"plugins/core/核.md": (PLUGIN / "核.md").read_text(encoding="utf-8"),
                     "plugins/core/振る舞い.md": (PLUGIN / "振る舞い.md").read_text(encoding="utf-8")}, "本物の核")
    f.installed = _git(f.work, "rev-parse", "HEAD")
    f.install()
    f.hook("inject")
    for i in range(5):
        _commit(f.work, {f"plugins/guard/x{i}.py": "x\n"}, f"急ぎの安全: 守りを変える {i}")
        assert f.hook("fresh") == "", i
    again = f.hook("inject", source="compact")
    assert again.count("# 振る舞いの核") == 1 and again.count("# 振る舞いの既定") == 1


# ── 起動の道と問いの道で、核の本文の読み・入れ直しが壊れても落ちず、読めない file を 1 回だけ名指す ──
import io  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402

from test_core_plugin import kaku  # noqa: E402

TIP = "e" * 40


@pytest.fixture
def box(tmp_path, monkeypatch):
    """作り物の窓（hook を同じ process で呼ぶ）。起動の時から先端（TIP）が入った版より新しく、守りだけが動いた。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("AF_FRESH_INTERVAL", "0")
    (tmp_path / ".claude" / "af-foundation").mkdir(parents=True)
    f = {"installed": "a" * 40, "main": TIP, "ref": "main", "shas": {"core": "a" * 40}, "plugins": ["guard"]}
    monkeypatch.setattr(kaku, "freshness", lambda: f)
    monkeypatch.setattr(kaku, "start_cause", lambda f: "after")
    monkeypatch.setattr(kaku, "setup_text", lambda: None)
    monkeypatch.setattr(kaku, "start_refresh", lambda tip: True)
    monkeypatch.setattr(kaku, "refresh_failed_text", lambda state: None)

    def hook(name, capsys):
        monkeypatch.setattr(kaku.sys, "stdin", io.StringIO(json.dumps({"session_id": "s1", "source": "startup"})))
        assert getattr(kaku, name)() == 0
        out = capsys.readouterr().out
        return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""
    return hook


def _moved(monkeypatch, tip):
    """起動の後に先端が tip へ進み、守りだけが動いた形。"""
    monkeypatch.setattr(kaku, "freshness", lambda: {"installed": "a" * 40, "main": tip, "ref": "main",
                                                    "shas": {"core": "a" * 40}, "plugins": ["guard"]})
    monkeypatch.setattr(kaku, "moved_since", lambda base, t: ["guard"])
    monkeypatch.setattr(kaku, "urgent_since", lambda base, t: ["急ぎの安全: 守りを変える"])


def test_核の本文が変わらない時に裏の入れ直しが壊れても_fresh_は落ちず名指す(box, monkeypatch, capsys):
    """注入: 送る核が無い（text が None）時に入れ直しの壊れを足す所で落ちる形を戻すと赤。"""
    names = [p.name for p in kaku.injected()]
    monkeypatch.setattr(kaku, "tip_texts", lambda main: {n: f"{n} の本文\n" for n in names})
    box("inject", capsys)
    _moved(monkeypatch, "f" * 40)

    def broken(tip):
        raise RuntimeError("入れ直しを始められない")
    monkeypatch.setattr(kaku, "start_refresh", broken)
    text = box("fresh", capsys)
    assert "裏の入れ直し" in text and "入れ直しを始められない" in text and "### main の先端" not in text
    state = json.loads((kaku._state_path("s1")).read_text(encoding="utf-8"))
    assert state["told"]["main"] == "f" * 40  # 記録まで届いた（同じ先端を問いのたびに見直さない）


def test_起動の時に先端で読めなかった_file_を名指し_fresh_では名指し直さない(box, monkeypatch, capsys):
    """注入: 起動の道で読めなかった file を黙って入っている版へ差し替える形を戻すと赤。"""
    head, *rest = [p.name for p in kaku.injected()]
    monkeypatch.setattr(kaku, "tip_texts", lambda main: {head: "先端の核\n", **{n: None for n in rest}})
    text = box("inject", capsys)
    assert text.startswith("先端の核")
    for n in rest:
        assert text.count(f"main の先端の {n} を読めなかった") == 1
    _moved(monkeypatch, "f" * 40)
    assert box("fresh", capsys) == ""


def test_fresh_で先端の核を読めなくても落ちず名指し_次の問いで読み直す(box, monkeypatch, capsys):
    """注入: fresh の中の先端の読みに守りが無い形を戻すと赤。"""
    names = [p.name for p in kaku.injected()]
    monkeypatch.setattr(kaku, "tip_texts", lambda main: {n: f"{n} の本文\n" for n in names})
    box("inject", capsys)
    _moved(monkeypatch, "f" * 40)

    def broken(main):
        raise RuntimeError("目録の一覧が壊れている")
    monkeypatch.setattr(kaku, "tip_texts", broken)
    text = box("fresh", capsys)
    assert "先端の核の読み" in text and "目録の一覧が壊れている" in text
    monkeypatch.setattr(kaku, "tip_texts", lambda main: {n: f"{n} の新しい本文\n" for n in names})
    again = box("fresh", capsys)
    assert all(f"{n} の新しい本文" in again for n in names)


def test_先端の空の本文は読めない物と読む(monkeypatch):
    """注入: 空の本文を差し込みでは入っている版へ替え、印では空の本文として持つ（選び方が揃わない）形を戻すと赤。"""
    monkeypatch.setattr(kaku, "catalog_source", lambda: ({"installLocation": "/x"}, None))
    monkeypatch.setattr(kaku, "_git", lambda loc, *args, **kw: "")
    assert set(kaku.tip_texts(TIP).values()) == {None}
