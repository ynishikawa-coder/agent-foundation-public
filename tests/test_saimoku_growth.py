"""形の細目（細目/ の節ごとの file）も、毎回差し込む物と同じく main より増えたら赤（オーナー同意 2026-11-19）。
核から押し出した物が細目で膨らみ続けるのを止める。細目は節ごとの file に割ってあり、量は全部の file をつないだ全文で照らす
（節の間で文を移すだけなら増えない）。新しい試験は新しい file に置く。"""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)


def _g(tmp_path, *a):
    return subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)


def _repo(tmp_path, one_file=False):
    """作り物の git repo（核.md と細目）。one_file なら細目は割る前の 1 枚（細目.md）で commit する。"""
    _g(tmp_path, "init", "-q")
    _g(tmp_path, "config", "user.email", "t@example.invalid")
    _g(tmp_path, "config", "user.name", "t")
    (tmp_path / "核.md").write_text("元の核\n", encoding="utf-8")
    d = tmp_path / "細目"
    if one_file:
        (tmp_path / "細目.md").write_text("## 1. 甲\n\n- 甲の文。\n\n## 2. 乙\n\n- 乙の文。\n", encoding="utf-8")
    else:
        d.mkdir()
        (d / "01-甲.md").write_text("## 1. 甲\n\n- 甲の文。\n", encoding="utf-8")
        (d / "02-乙.md").write_text("## 2. 乙\n\n- 乙の文。\n", encoding="utf-8")
    _g(tmp_path, "add", "-A")
    _g(tmp_path, "commit", "-q", "-m", "元")
    return tmp_path / "核.md", d



def test_細目は増やさない物の一覧に在り_差し込む物の全部も在る():
    assert kaku.SAIMOKU in kaku.guarded()
    assert set(kaku.injected()) <= set(kaku.guarded())
    assert kaku.SAIMOKU not in kaku.injected(), "細目は毎回差し込まない（迷った時に Read する）"


def test_細目だけ増えても赤_同じか減れば緑(monkeypatch, tmp_path, capsys):
    """注入: 核は同じまま細目の 1 つの節に 1 字足すと赤。guarded が細目を落とす（古い形）と緑になり、この試験が赤になる。"""
    kaku_md, d = _repo(tmp_path)
    monkeypatch.setattr(kaku, "injected", lambda: (kaku_md,))
    monkeypatch.setattr(kaku, "SAIMOKU", d)
    assert kaku.grow("HEAD") == 0
    (d / "02-乙.md").write_text("## 2. 乙\n\n- 乙の文。足\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 1
    assert "細目 が HEAD より増えた" in capsys.readouterr().out
    (d / "02-乙.md").write_text("## 2. 乙\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 0
