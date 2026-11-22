"""plugin core の記録の読み口が「無い」と「読めない」を分ける（読めない物を黙って飛ばさない）。

意図: 窓の記録（~/.claude/af-foundation/<session>.json）と入口の記録（setup.json）が在るのに読めない時、
      名と訳を窓に知らせ、記録を今の値で書き直さない（止めずに知らせる）。
課題: 前の形は 1 本の読み口が壊れた file も無い file も None で返し、inject は起動の時の記録（start_main・told）を
      書き直し、fresh は黙って 0 を返し、setup_record は「記録が無い」と言って setup の走らせ直しへ導いた。
原因: 読み口が「無い」と「読めない」を 1 つの値に畳んでいた（呼ぶ側が分けられない形）。
どの試験も、読めない記録の類（壊れた JSON・UTF-8 でない中身・開けない file・形の違う中身）をわざと入れて拒むかを見る。
"""
from __future__ import annotations

import io
import json

import pytest

from test_core_plugin import PLUGIN, kaku

SHA = "c" * 40


def _break(path, kind):
    """記録の場所に、読めない類の物を置く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "壊れた JSON":
        path.write_text('{"start_main": ', encoding="utf-8")
    elif kind == "UTF-8 でない":
        path.write_bytes(b"\xff\xfe\x00broken")
    elif kind == "開けない":
        path.mkdir()                      # file の所に dir＝開けない（root でも読めない）
    elif kind == "形が違う":
        path.write_text("[1, 2]", encoding="utf-8")


def _snap(path):
    return "dir" if path.is_dir() else path.read_bytes()


KINDS = ["壊れた JSON", "UTF-8 でない", "開けない", "形が違う"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(proj))
    return h


def _run(monkeypatch, capsys, fn, stdin):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    assert fn() == 0
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


# ── 読み口: 無い＝None・読めない＝名と訳つきの Unreadable ──

def test_読み口は無い記録を_None_で返す(tmp_path):
    assert kaku._read_json(tmp_path / "無い.json", dict) is None


@pytest.mark.parametrize("kind", KINDS)
def test_注入_読み口は読めない記録を無いと返さず名と訳を出す(tmp_path, kind):
    path = tmp_path / "rec.json"
    _break(path, kind)
    with pytest.raises(kaku.Unreadable) as e:
        kaku._read_json(path, dict)
    assert str(path) in str(e.value) and e.value.why


# ── inject: 読めない窓の記録を書き直さず知らせる ──

@pytest.mark.parametrize("kind", KINDS)
def test_注入_inject_は読めない窓の記録を書き直さず名指す(home, monkeypatch, capsys, kind):
    path = kaku._state_path("s1")
    _break(path, kind)
    before = _snap(path)
    ctx = _run(monkeypatch, capsys, kaku.inject, json.dumps({"session_id": "s1"}))
    assert _snap(path) == before, "読めない記録を今の値で書き直した"
    assert "この窓の土台の記録が読めない" in ctx and str(path) in ctx and "start_main・told" in ctx


def test_inject_は無い窓の記録を書き読めないとは言わない(home, monkeypatch, capsys):
    ctx = _run(monkeypatch, capsys, kaku.inject, json.dumps({"session_id": "s1"}))
    assert isinstance(kaku._read_json(kaku._state_path("s1"), dict), dict)
    assert "読めない" not in ctx.split("（この核と振る舞いの既定は")[1]


def test_注入_inject_は新しさの見張りが壊れたら名指す(home, monkeypatch, capsys):
    def boom():
        raise kaku.Unreadable(home / "x.json", "わざと")
    monkeypatch.setattr(kaku, "freshness", boom)
    ctx = _run(monkeypatch, capsys, kaku.inject, json.dumps({"session_id": "s2"}))
    assert "土台の見張り（新しさ）が動かなかった" in ctx and "わざと" in ctx


def test_注入_inject_は壊れた_hook_の入力を名指す(home, monkeypatch, capsys):
    ctx = _run(monkeypatch, capsys, kaku.inject, "{壊れた")
    assert "土台の見張り（hook の入力）が動かなかった" in ctx


# ── fresh: 読めない窓の記録で黙って 0 を返さない ──

@pytest.mark.parametrize("kind", KINDS)
def test_注入_fresh_は読めない窓の記録で黙らず書き直さない(home, monkeypatch, capsys, kind):
    path = kaku._state_path("s1")
    _break(path, kind)
    before = _snap(path)
    ctx = _run(monkeypatch, capsys, kaku.fresh, json.dumps({"session_id": "s1"}))
    assert _snap(path) == before
    assert "この窓の土台の記録が読めない" in ctx and str(path) in ctx


def test_fresh_は無い窓の記録では黙る(home, monkeypatch, capsys):
    assert _run(monkeypatch, capsys, kaku.fresh, json.dumps({"session_id": "無い"})) == ""


def test_注入_fresh_は新しさの見張りが壊れたら名指す(home, monkeypatch, capsys):
    kaku._save_state("s3", {"checked": 0, "comparable": True, "start_main": None})
    monkeypatch.setattr(kaku, "freshness", lambda: 1 / 0)
    ctx = _run(monkeypatch, capsys, kaku.fresh, json.dumps({"session_id": "s3"}))
    assert "土台の見張り（新しさ）が動かなかった" in ctx and "ZeroDivisionError" in ctx


# ── setup_record: 壊れた入口の記録を「記録が無い」と言わない ──

def _installed(home, loc):
    plugins = home / ".claude" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "core@agent-foundation": [{"installPath": str(PLUGIN), "gitCommitSha": SHA, "scope": "user",
                                   "lastUpdated": "2026-11-19T10:00:00.000Z"}]}}), encoding="utf-8")
    (plugins / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "installLocation": str(loc), "source": {"source": "github", "repo": kaku.UPSTREAM}}}), encoding="utf-8")


def test_setup_record_は無い記録を無いと言う(home):
    _installed(home, home)
    state, why = kaku.setup_record()
    assert state is None and "が無い" in why


@pytest.mark.parametrize("name", ["setup.json", f"setup-{SHA}.json"])
@pytest.mark.parametrize("kind", KINDS)
def test_注入_setup_record_は壊れた記録を無いと言わず名指す(home, kind, name):
    _installed(home, home)
    path = home / ".claude" / "af-foundation" / name
    _break(path, kind)
    with pytest.raises(kaku.Unreadable) as e:
        kaku.setup_record()
    assert str(path) in str(e.value)
    text = kaku.setup_text()
    assert "入口の記録が読めない" in text and str(path) in text
    assert "記録（~/.claude/af-foundation/setup.json）が無い" not in text
    assert "環境の setup script が古い形" not in text, "読めない記録で setup の走らせ直しへ導いた"


@pytest.mark.parametrize("kind", KINDS)
def test_注入_起動の時から古い知らせは壊れた入口の記録で落ちず名指す(home, kind):
    """2 回目の起動で told を差し直す時に入口の記録が壊れていても、hook ごと落ちて核の差し込みを消さない。"""
    _installed(home, home)
    path = home / ".claude" / "af-foundation" / "setup.json"
    _break(path, kind)
    f = {"installed": SHA, "main": "d" * 40, "ref": "main", "shas": {"core": SHA}, "plugins": ["guard"]}
    text = kaku.stale_at_start_text(f)
    assert "読めない" in text and str(path) in text
