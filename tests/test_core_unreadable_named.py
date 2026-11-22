"""plugin core の見張りは、読めない物を「無い」「古くない」「0 件」と読まず名指す（git の失敗・壊れた目録・壊れた台帳）。

意図: 照らす元（git の答え・目録の一覧・入った台帳・名簿・CLAUDE.md・照らす file）が在るのに読めない時、
      見張りは「欠けが無い」「古くない」と黙らず、どれがなぜ読めないかを名指す（止める道具は 2 で止まる）。
課題: git が失敗した・目録の行が壊れた・台帳の形が違う・名簿を引けない時、見張りは「無い」「古くない」「0 件」と読んだ。
原因: 読む口が「無い」と「読めない」を 1 つの値（None・{}・[]・0）に畳んでいた（git の失敗を空の出力と同じに返す口・
      形の違う行を黙って落とす読み方）。
どの試験も、読めない物の類をわざと入れて、見張りが名指す（黙って緑にしない）かを見る。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_core_plugin import PLUGIN, Foundation, _commit, _installed_home, kaku

ROOT = PLUGIN.parent.parent
SCRIPTS = PLUGIN / "scripts"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / ".claude" / "plugins").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    return h


def _put(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


# ── CLAUDE.md の量: 読めない CLAUDE.md を「上限の内」と読まない ──

@pytest.mark.parametrize("kind", ["UTF-8 でない", "開けない"])
def test_注入_読めない_CLAUDE_md_を上限の内と読まず名指す(tmp_path, kind):
    path = tmp_path / "CLAUDE.md"
    if kind == "UTF-8 でない":
        path.write_bytes(b"\xff\xfe broken")
    else:
        path.mkdir()
    text = kaku.claude_md_text(tmp_path)
    assert text and "CLAUDE.md が読めず" in text and "上限の内と決まったのではない" in text


def test_CLAUDE_md_が無い_repo_は照らす物が無い(tmp_path):
    assert kaku.claude_md_text(tmp_path) is None


# ── 新しさ: git が失敗した時に「古くない」と読まない ──

def test_注入_出所に出られない時は先端を聞けないと名指す(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    loc = str(f.home / ".claude" / "plugins" / "marketplaces" / "agent-foundation")
    f.remote.rename(tmp_path / "gone.git")
    with pytest.raises(kaku.Incomparable) as e:
        kaku.source_tip(loc, "main")
    assert "出所（origin）の先端を聞けない" in str(e.value) and "main:" in str(e.value)


def test_注入_出所に枝が無い時は古くないと読まない(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    loc = str(f.home / ".claude" / "plugins" / "marketplaces" / "agent-foundation")
    subprocess.run(["git", "-C", str(f.remote), "update-ref", "-d", "refs/heads/main"], check=True)
    with pytest.raises(kaku.Incomparable) as e:
        kaku.source_tip(loc, "main")
    assert "出所に枝が無い" in str(e.value)


def test_注入_起動の時に比べられない窓は古くないと黙らず名指す(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    f.remote.rename(tmp_path / "gone.git")
    text = f.hook("inject")
    assert "土台の新しさを比べられなかった" in text and "古くないと決まったのではない" in text
    assert "# 振る舞いの核" in text                       # 核の差し込みは止めない
    state = json.loads((f.home / ".claude" / "af-foundation" / "s1.json").read_text(encoding="utf-8"))
    assert state["comparable"] is True                    # 次の問いの時にもう一度比べる


def test_注入_先端を目録の_clone_へ取って来られない時は名指す(tmp_path, monkeypatch):
    f = Foundation(tmp_path)
    f.install()
    _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    monkeypatch.setenv("HOME", str(f.home))
    real = kaku._git_run

    def fetch_fails(loc, *args, **kw):
        if args[0] == "fetch":
            raise kaku.GitFailed("git fetch が 128 で失敗した: 注入")
        return real(loc, *args, **kw)
    monkeypatch.setattr(kaku, "_git_run", fetch_fails)
    with pytest.raises(kaku.Incomparable) as e:
        kaku.freshness()
    assert "取って来られない" in str(e.value) and "注入" in str(e.value)


def test_注入_差分を読めない時は変わっていないと読まない(tmp_path, monkeypatch):
    f = Foundation(tmp_path)
    f.install()
    tip = _commit(f.work, {"plugins/core/核.md": "核 2\n"}, "核を変える")
    monkeypatch.setenv("HOME", str(f.home))
    real = kaku._git_run

    def diff_fails(loc, *args, **kw):
        if args[0] == "diff":
            raise kaku.GitFailed("git diff が 128 で失敗した: 注入")
        return real(loc, *args, **kw)
    monkeypatch.setattr(kaku, "_git_run", diff_fails)
    with pytest.raises(kaku.Incomparable) as e:
        kaku.moved_since(f.installed, tip)
    assert "差分を読めない" in str(e.value)


# ── 目録の一覧・入った台帳・settings・名簿: 形の違う物を「無い」と読まない ──

BAD_ROWS = {
    "行が dict でない": [1],
    "出所が無い": {"installLocation": "/x"},
    "出所の形が違う": {"source": "github", "installLocation": "/x"},
    "入れた所が無い": {"source": {"source": "github", "repo": kaku.UPSTREAM}},
}


@pytest.mark.parametrize("kind", list(BAD_ROWS))
def test_注入_目録の行が壊れていれば目録が無いと読まない(home, kind):
    _put(home / ".claude" / "plugins" / "known_marketplaces.json", {kaku.MARKET: BAD_ROWS[kind]})
    with pytest.raises(kaku.Unreadable):
        kaku.catalog_source()
    text = kaku.setup_text()
    assert text and "土台の入れ方を照らせない" in text and "known_marketplaces.json" in text


BAD_LEDGERS = {
    "plugins が dict でない": {"plugins": []},
    "行の並びが list でない": {"plugins": {"core@agent-foundation": {"scope": "user"}}},
    "行が dict でない": {"plugins": {"core@agent-foundation": ["user"]}},
}


@pytest.mark.parametrize("kind", list(BAD_LEDGERS))
def test_注入_形の違う台帳を空の台帳と読まない(home, kind):
    _put(home / ".claude" / "plugins" / "installed_plugins.json", BAD_LEDGERS[kind])
    for fn in (kaku.user_rows, kaku.installed_sha):
        with pytest.raises(kaku.Unreadable) as e:
            fn()
        assert "installed_plugins.json" in str(e.value)


def test_台帳が無いのは空の台帳(home):
    assert kaku.user_rows() == {} and kaku.installed_sha() is None


def test_注入_形の違う_enabledPlugins_をどれも_enabled_でないと読まない(home):
    _put(home / ".claude" / "settings.json", {"enabledPlugins": ["core@agent-foundation"]})
    with pytest.raises(kaku.Unreadable):
        kaku._enabled()


@pytest.mark.parametrize("kind", ["git が引けない", "壊れた JSON", "形が違う"])
def test_注入_入った版の名簿が読めなければ名指す(tmp_path, kind):
    loc = tmp_path / "loc"
    (loc / ".claude-plugin").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(loc)], check=True)
    body = {"壊れた JSON": "{", "形が違う": "[1]"}.get(kind, "{}")
    (loc / ".claude-plugin" / "marketplace.json").write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(loc), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(loc), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "x"],
                   check=True)
    sha = "0" * 40 if kind == "git が引けない" else subprocess.run(
        ["git", "-C", str(loc), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    with pytest.raises(kaku.Unreadable) as e:
        kaku.catalog_at(str(loc), sha)
    assert "marketplace.json" in str(e.value)


def test_注入_窓の起動で壊れた台帳を入れ方に欠けが無いと読まない(tmp_path):
    home = _installed_home(tmp_path, ["core", "guard"], ["core", "guard"], entry=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text('{"plugins": []}', encoding="utf-8")
    from test_core_plugin import _ctx, run
    ctx = _ctx(run("inject", project=tmp_path / "proj", home=home))
    assert "土台の入れ方を照らせない" in ctx and "installed_plugins.json" in ctx


# ── 古い形の見張り: 読めない file を「古い形 0」と読まない ──

def test_注入_上限を越えた_file_は古い形_0_と言わず照らせないで止まる(tmp_path, capsys):
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / "CLAUDE.md").write_text("x" * (kaku.TEXT_LIMIT + 1), encoding="utf-8")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    assert kaku.olds([d]) == 2
    out = capsys.readouterr().out
    assert "照らせない" in out and "CLAUDE.md" in out and "古い形 0" not in out


def test_注入_git_の_repo_で一覧を引けない時は名で書いた_file_に縮めて古い形_0_と言わない(tmp_path, capsys, monkeypatch):
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    (d / "CLAUDE.md").write_text("古い形の無い文\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    real = kaku._git_run

    def broken(cwd, *args, **kw):
        if "ls-files" in args:
            raise kaku.GitFailed("git ls-files が終わり方 128 で失敗（わざと）")
        return real(cwd, *args, **kw)
    monkeypatch.setattr(kaku, "_git_run", broken)
    assert kaku.olds([d]) == 2
    out = capsys.readouterr().out
    assert "git ls-files）を読めない" in out and "わざと" in out and "古い形 0" not in out


# ── refs・copies: 土台の文書と台帳が読めない時に「照らせない」と名指す ──

def _installed_copy(tmp_path: Path, scripts=("kaku.py", "refs.py", "copies.py"), docs=False) -> Path:
    """入れた形（cache/<目録>/core/<版>/）の作り物。docs=False なら核・振る舞い・細目を置かない（欠けた版）。"""
    d = tmp_path / "cache" / "agent-foundation" / "core" / "v1"
    (d / "scripts").mkdir(parents=True)
    for s in scripts:
        shutil.copy2(SCRIPTS / s, d / "scripts" / s)
    if docs:
        for n in ("核.md", "振る舞い.md"):
            shutil.copy2(PLUGIN / n, d / n)
        shutil.copytree(PLUGIN / "細目", d / "細目")
    return d


def _tool(d: Path, name: str, *args, home: Path):
    return subprocess.run([sys.executable, str(d / "scripts" / name), *map(str, args)], capture_output=True, text=True,
                          timeout=60, env=dict(os.environ, HOME=str(home)))


def test_注入_copies_は土台の文が欠けた版で黙って緑にしない(tmp_path):
    d = _installed_copy(tmp_path)
    target = tmp_path / "x.md"
    target.write_text("何か\n", encoding="utf-8")
    r = _tool(d, "copies.py", target, home=tmp_path / "home")
    assert r.returncode == 2 and "照らせない" in r.stdout and "土台の文が欠けている" in r.stdout and "核.md" in r.stdout


def test_注入_copies_は壊れた台帳で照らせないと止まる(tmp_path):
    d = _installed_copy(tmp_path, docs=True)
    home = tmp_path / "home"
    _put(home / ".claude" / "plugins" / "installed_plugins.json", {"plugins": []})
    target = tmp_path / "x.md"
    target.write_text("何か\n", encoding="utf-8")
    r = _tool(d, "copies.py", target, home=home)
    assert r.returncode == 2 and "照らせない" in r.stdout and "installed_plugins.json" in r.stdout


def test_注入_refs_は壊れた台帳で照らせないと止まる(tmp_path):
    d = _installed_copy(tmp_path, docs=True)
    home = tmp_path / "home"
    _put(home / ".claude" / "plugins" / "installed_plugins.json", {"plugins": {"core@agent-foundation": "x"}})
    target = tmp_path / "x.md"
    target.write_text("何か\n", encoding="utf-8")
    r = _tool(d, "refs.py", "check", target, home=home)
    assert r.returncode == 2 and "照らせない" in r.stdout and "installed_plugins.json" in r.stdout


def test_注入_refs_は欠けた土台の文書を訳つきで照らせないと名指す(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("refs_t", SCRIPTS / "refs.py")
    refs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(refs)
    root = tmp_path / "root"
    shutil.copytree(PLUGIN, root / "plugins" / "core")
    (root / "plugins" / "core" / "振る舞い.md").unlink()   # 土台の dir の正本を 1 つ欠かす
    c = refs.contract(root)
    assert "plugins/core/振る舞い.md" in c["unread"] and c["unread_why"]["plugins/core/振る舞い.md"]
    bad, unread = refs.check_all(c, "振る舞い.md「並走」を見る\n")
    assert not bad and unread and "土台の dir" in unread[0][1]


# ── 入口（setup_plugins.py）: 照らせない物を「全部入った」と読まない ──

from test_setup_plugins import foundation as setup_foundation, run as setup_run  # noqa: E402


@pytest.mark.parametrize("kind", ["壊れた JSON", "形が違う"])
def test_注入_入口は壊れた台帳を空と読まず名指す(tmp_path, kind):
    root = setup_foundation(tmp_path, ["core"])
    ledger = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    _put(ledger, "{" if kind == "壊れた JSON" else {"plugins": []})
    r, _, note, _ = setup_run(tmp_path, root)
    # 壊れた台帳で plugin 一覧を引けない（作り物の claude も台帳を読んで落ちる）: 全部入ったと読まず、訳つきで名指す
    assert r.returncode != 0 and "af-plugin-missing" in note
    assert "入ったか・どの版かを照らせない" in note and "plugin list" in note


def test_注入_入口は壊れた目録の一覧で黙って進まない(tmp_path):
    root = setup_foundation(tmp_path, ["core"])
    _put(tmp_path / "home" / ".claude" / "plugins" / "known_marketplaces.json", "{")
    r, log, note, _ = setup_run(tmp_path, root)
    assert r.returncode == 2 and "known_marketplaces.json" in note and "plugin install" not in log


def test_注入_入口は出所の先端を聞けない時に名指す(tmp_path):
    root = setup_foundation(tmp_path, ["core"])
    (tmp_path / "upstream").rename(tmp_path / "gone")   # 出所に出られない
    r, _, note, _ = setup_run(tmp_path, root)
    assert r.returncode != 0 and "main の先端を出所へ聞けなかった" in note


def test_手元の_dir_から入れた目録は出所に聞かず名指しもしない(tmp_path):
    """出所の無い目録（kaku.LOCAL_SOURCES＝手元の dir・file から入れた試し・CI）は比べる先が無い。聞けない訳で赤にしない
    （名指しは「出所が在るのに聞けない」時だけ。起動の hook も比べない）。"""
    root = setup_foundation(tmp_path, ["core"])
    known = tmp_path / "home" / ".claude" / "plugins" / "known_marketplaces.json"
    _put(known, {"agent-foundation": {"source": {"source": "directory", "path": str(root)}, "installLocation": str(root)}})
    bin_dir = tmp_path / "bin"   # 出所に聞く手（ls-remote）だけ必ず失敗する git: 聞けば名指しが出て赤になる
    bin_dir.mkdir()
    (bin_dir / "git").write_text(f'#!/bin/sh\nfor a in "$@"; do [ "$a" = ls-remote ] && exit 128; done\nexec {shutil.which("git")} "$@"\n',
                                 encoding="utf-8")
    (bin_dir / "git").chmod(0o755)
    r, _, note, _ = setup_run(tmp_path, root, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    assert r.returncode == 0 and "出所へ聞けなかった" not in note, r.stdout + note


def test_注入_入った版の名簿が読めなくても入口の記録の名指しを消さない(tmp_path, monkeypatch):
    """1 つの読めない物（名簿）が、ほかに見つけた物（壊れた入口の記録）を覆い隠さない＝並べて名指す。"""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    plugins = home / ".claude" / "plugins"
    sha = "c" * 40
    _put(plugins / "installed_plugins.json", {"version": 2, "plugins": {"core@agent-foundation": [
        {"installPath": str(PLUGIN), "gitCommitSha": sha, "scope": "user", "lastUpdated": "2026-11-19T10:00:00.000Z"}]}})
    _put(plugins / "known_marketplaces.json", {"agent-foundation": {
        "installLocation": str(home), "source": {"source": "github", "repo": kaku.UPSTREAM}}})   # git でない＝名簿を引けない
    rec = home / ".claude" / "af-foundation" / "setup.json"
    rec.parent.mkdir(parents=True)
    rec.write_text("{", encoding="utf-8")
    text = kaku.setup_text()
    assert "入口の記録が読めない" in text and "入った版の土台の名簿が読めない" in text, text
