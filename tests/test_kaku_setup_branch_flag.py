"""kaku.setup_text: 名簿を読めない訳を名指したかを、出す文の字でなく印で見分けるか（注入の試験）。

原因の台帳: 「名簿が読めない」の字を含む行が在るかで分かれ道を決めていた＝言い回しを変えると黙って分かれ道が変わる。
ほかの行（ここでは読めない訳の文）がたまたまその字を含むと、名簿の名指しを落としたのと同じに黙った。
"""
from pathlib import Path

from test_core_unreadable_named import PLUGIN, _put, kaku


def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    plugins = home / ".claude" / "plugins"
    _put(plugins / "installed_plugins.json", {"version": 2, "plugins": {"core@agent-foundation": [
        {"installPath": str(PLUGIN), "gitCommitSha": "c" * 40, "scope": "user", "lastUpdated": "2026-11-19T10:00:00.000Z"}]}})
    _put(plugins / "known_marketplaces.json", {"agent-foundation": {
        "installLocation": str(home), "source": {"source": "github", "repo": kaku.UPSTREAM}}})
    return home


def test_名簿の名指しの言い回しが変わっても分かれ道は変わらない(tmp_path, monkeypatch):
    """読めない訳の名指しの字を言い換えても、名簿を照らしていない事は 1 回だけ名指す（2 回にも 0 回にもならない）。"""
    _home(tmp_path, monkeypatch)

    def unreadable(*_a, **_k):
        raise kaku.Unreadable(Path("marketplace.json"), "目録の clone が git でない")
    monkeypatch.setattr(kaku, "catalog_at", unreadable)
    text = kaku.setup_text()
    assert text.count("入っていない plugin を照らしていない") == 1, text


def test_注入_ほかの行に同じ字が在っても名簿の名指しを落とさない(tmp_path, monkeypatch):
    """名簿は読めて中身が無い（want が None）時、入口の記録の訳がたまたま「名簿が読めない」の字を含んでも名簿の名指しを出す。"""
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(kaku, "catalog_at", lambda *_a, **_k: None)

    def record():
        raise kaku.Unreadable(Path("setup.json"), "名簿が読めない形の記録")
    monkeypatch.setattr(kaku, "setup_record", record)
    text = kaku.setup_text()
    assert "入った版の土台の名簿（.claude-plugin/marketplace.json）が目録の clone から読めず" in text, text
