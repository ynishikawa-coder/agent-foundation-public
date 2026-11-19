"""形の細目（細目.md）も、毎回差し込む物と同じく main より増えたら赤（オーナー同意 2026-11-19）。
核から押し出した物が細目で膨らみ続けるのを止める。新しい試験は新しい file に置く。"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)


def _repo(tmp_path):
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@example.invalid")
    g("config", "user.name", "t")
    files = {}
    for name in ("核.md", "細目.md"):
        f = tmp_path / name
        f.write_text(f"元の{name}\n", encoding="utf-8")
        files[name] = f
    g("add", "-A")
    g("commit", "-q", "-m", "元")
    return files


def test_細目は増やさない物の一覧に在り_差し込む物の全部も在る():
    assert kaku.SAIMOKU in kaku.guarded()
    assert set(kaku.injected()) <= set(kaku.guarded())
    assert kaku.SAIMOKU not in kaku.injected(), "細目は毎回差し込まない（迷った時に Read する）"


def test_細目だけ増えても赤_同じか減れば緑(monkeypatch, tmp_path, capsys):
    """注入: 核は同じまま細目に 1 字足すと赤。guarded が細目を落とす（古い形）と緑になり、この試験が赤になる。"""
    f = _repo(tmp_path)
    monkeypatch.setattr(kaku, "injected", lambda: (f["核.md"],))
    monkeypatch.setattr(kaku, "SAIMOKU", f["細目.md"])
    assert kaku.grow("HEAD") == 0
    f["細目.md"].write_text("元の細目.md\n足\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 1
    assert "細目.md が HEAD より増えた" in capsys.readouterr().out
    f["細目.md"].write_text("細目\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 0
