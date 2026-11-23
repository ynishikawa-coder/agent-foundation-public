"""離席の印・台帳の置き場・次の頼みの知らせは、読めない・書けない時に黙って通す側へ落ちない（注入の試験）。

前の形: 離席の印が在るのに壊れていると在席と読み、戻せない操作が通った。git が失敗すると台帳の置き場を cwd の根で
決め、作業部屋では本体と別の冊を読んだ。session-watch は次の頼みの時の知らせ・知らせた印を書けなくても黙った。
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
import unanswered as UQ  # noqa: E402

spec = importlib.util.spec_from_file_location("session_watch_fc", ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


def test_注入_壊れた離席の印は離席として扱う(monkeypatch, tmp_path):
    monkeypatch.setenv("AF_GUARD_TMP", str(tmp_path))
    p = Path(UQ.away_path("s1"))
    p.parent.mkdir(parents=True)
    p.write_text("{壊れた", encoding="utf-8")
    win = UQ.read_away("s1")
    assert win and win.get("broken") and win.get("since"), win


def test_注入_since_の無い離席の印も離席として扱い時刻は印の時刻(monkeypatch, tmp_path):
    monkeypatch.setenv("AF_GUARD_TMP", str(tmp_path))
    p = Path(UQ.away_path("s1"))
    p.parent.mkdir(parents=True)
    p.write_text("[]", encoding="utf-8")
    win = UQ.read_away("s1")
    assert win and win.get("since"), win


def test_印が無ければ在席(monkeypatch, tmp_path):
    monkeypatch.setenv("AF_GUARD_TMP", str(tmp_path))
    assert UQ.read_away("s1") is None


def test_注入_git_が失敗したら台帳の置き場を_cwd_の根で決めない(monkeypatch, tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    class Fail:
        returncode, stdout, stderr = 1, "", "fatal: 何かが壊れた"
    monkeypatch.setattr(UQ.subprocess, "run", lambda *a, **k: Fail())
    assert UQ.repo_home(str(repo)) == ""
    monkeypatch.setattr(UQ.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("git が無い")))
    assert UQ.repo_home(str(repo)) == ""


def test_作業部屋は本体と同じ根(tmp_path):
    repo = tmp_path / "main"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(tmp_path / "wt")], check=True)
    assert UQ.repo_home(str(tmp_path / "wt")) == os.path.realpath(repo)


def test_注入_知らせを置けない時は黙らず名指す(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    env = {"AF_SESSION_WATCH_TMP": str(blocker / "sub")}   # file の下には dir を作れない
    assert sw.put_note(env, "s1", "知らせの本文") is False
    err = capsys.readouterr().err
    assert "置けなかった" in err and "知らせの本文" in err


def test_注入_知らせた印を置けない時は黙らず名指す(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    env = {"AF_SESSION_WATCH_TMP": str(blocker / "sub")}
    assert sw._seen(env, "s1", "broken") is False
    assert "印を置けなかった" in capsys.readouterr().err


def test_知らせを置ければ次の頼みで取り出せる(tmp_path):
    env = {"AF_SESSION_WATCH_TMP": str(tmp_path)}
    assert sw.put_note(env, "s1", "本文") is True
    assert sw.take_note(env, "s1") == "本文"
