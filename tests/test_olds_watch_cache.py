"""古い形の見張りは、起動の時間の上限で打ち切っても、裏で最後まで照らして次の起動で結果を出す（打ち切りが続いて照らし終えない形にしない）。

意図: 起動の古い形の見張りが、repo が大きくなっても照らし終える。
課題: WATCH_BUDGET で毎回打ち切ると、照らしの重さが上限を越えた repo では古い形を一度も名指さない（既定で通す）。
原因: 打ち切った照らしの続きを持つ所が無く、毎回 0 から上限の中で照らし直していた。
"""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KAKU = ROOT / "plugins" / "core" / "scripts" / "kaku.py"


def _load():
    spec = importlib.util.spec_from_file_location("kaku_cache_t", KAKU)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _repo(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    (p / "a.md").write_text("ふるいかたち\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(p), "add", "."], check=True)
    subprocess.run(["git", "-C", str(p), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-qm", "x"], check=True)
    return p




@pytest.fixture
def kaku(tmp_path, monkeypatch):
    monkeypatch.setenv("AF_KAKU_OLDS_CACHE", str(tmp_path / "cache"))
    return _load()




def test_打ち切った照らしは裏で最後まで回り_次の呼び出しで結果を出す(kaku, tmp_path, monkeypatch):
    p = _repo(tmp_path)
    # 打ち切りをわざと起こす: 最初の照らしは時間の上限 0.01 秒
    with pytest.raises(TimeoutError) as e:
        kaku.find_olds_bounded(p, budget=0.01)
    assert "裏で最後まで照らしていて" in str(e.value)
    assert "古い形 0 と決まったのではない" in str(e.value)
    key = kaku._olds_key(p, kaku.OLDS, 10)
    out = Path(tmp_path / "cache") / f"{key}.json"
    for _ in range(600):
        if out.exists():
            break
        time.sleep(0.1)
    assert out.exists(), "裏の照らしが結果を取って置かなかった"
    # 次の起動は上限が短くても、取って置いた結果を出す（打ち切らない）
    got = kaku.find_olds_bounded(p, budget=0.01)
    assert "ref" in got and "unread" in got


def test_取って置いた結果は作業の木が変わると使わない(kaku, tmp_path):
    p = _repo(tmp_path)
    k1 = kaku._olds_key(p, kaku.OLDS, 10)
    (p / "b.md").write_text("新しい file\n", encoding="utf-8")
    k2 = kaku._olds_key(p, kaku.OLDS, 10)
    assert k1 and k2 and k1 != k2
    (p / "a.md").write_text("書き換え\n", encoding="utf-8")
    assert kaku._olds_key(p, kaku.OLDS, 10) not in (k1, k2)


def test_取って置いた結果は表が変わると使わない(kaku, tmp_path):
    p = _repo(tmp_path)
    t = tmp_path / "t.json"
    t.write_text(Path(kaku.OLDS).read_text(encoding="utf-8"), encoding="utf-8")
    k1 = kaku._olds_key(p, t, 10)
    t.write_text(Path(kaku.OLDS).read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert kaku._olds_key(p, t, 10) != k1


def test_壊れた取り置きは使わず照らし直す(kaku, tmp_path):
    p = _repo(tmp_path)
    key = kaku._olds_key(p, kaku.OLDS, 10)
    d = tmp_path / "cache"
    d.mkdir()
    (d / f"{key}.json").write_text("{こわれた", encoding="utf-8")
    got = kaku.find_olds_bounded(p, budget=60)
    assert "ref" in got
    assert json.loads((d / f"{key}.json").read_text(encoding="utf-8"))["ref"] == got["ref"]


def test_git_の外では取って置かず_打ち切りは今まで通り名指す(kaku, tmp_path):
    p = tmp_path / "plain"
    p.mkdir()
    (p / "a.md").write_text("x\n", encoding="utf-8")
    assert kaku._olds_key(p, kaku.OLDS, 10) is None
    with pytest.raises(TimeoutError) as e:
        kaku.find_olds_bounded(p, budget=0.01)
    assert "裏で最後まで照らしていて" not in str(e.value)


def test_裏の照らしも上限で切り_取って置かない(kaku, tmp_path, monkeypatch):
    p = _repo(tmp_path)
    out = tmp_path / "cache" / "x.json"
    out.parent.mkdir()
    assert kaku.olds_cache(p, kaku.OLDS, out, budget=0.01) == 0
    assert not out.exists()
