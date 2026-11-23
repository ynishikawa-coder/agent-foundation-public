"""急ぎの安全の直しを数える urgent_since（plugins/core/scripts/kaku.py）が浅い clone の歴史を段に足して取り、取れない時は
名指す約束と、開いている窓への 2 回目の知らせが届けた後の物だけを挙げる約束。

意図: 開いている窓へは、その窓が最後に取った先端の後に入った急ぎの安全の直しだけを、変わった plugin と一緒に届ける。
課題: (1) 目録の clone は浅い（先端だけ）。窓が取った先端が深い所に在る時、歴史を段に足して取る道と、取れない時に
      「急ぎは無い」と黙らず名指す道を、どの試験も通していなかった（試験の clone は全部浅くない）。
      (2) 2 回目の知らせの「変わった plugin」が窓の立った時の先端から数えられ、1 回目に届けた plugin をまた挙げた。
原因: (1) 試験の作り物の土台が浅くない clone しか作らず、浅い場合の道が試験の外だった。
      (2) fresh が変わった plugin を立った時の先端（start_main）から、急ぎを最後に取った先端（told.main）から数え、
      同じ知らせの 2 つの欄の起点が別だった。
ここでは誤りの類（深い所の急ぎを見落とす・取れないのに空を返す・届けた plugin をまた挙げる）をわざと入れ、拒むかを見る。
"""
from __future__ import annotations

import subprocess

import pytest

from test_core_plugin import Foundation, _commit, _git, kaku
from test_isogi_dake_todoku import _with_entry


def _history(tmp_path, after):
    """remote: 始め（base）→ 急ぎの直し → plugins/ の直し after 本。先端だけの浅い clone を返す。"""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    (work / "a.md").write_text("始め\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "始め")
    base = _git(work, "rev-parse", "HEAD")
    (work / "plugins/guard").mkdir(parents=True)
    (work / "plugins/guard/a.py").write_text("a\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "急ぎの安全: 深い所の穴を塞ぐ")
    for i in range(after):
        (work / "plugins/checker").mkdir(parents=True, exist_ok=True)
        (work / "plugins/checker/b.py").write_text(f"{i}\n", encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-qm", f"直し {i}")
    _git(work, "push", "-q", "origin", "HEAD:main")
    tip = _git(work, "rev-parse", "HEAD")
    loc = tmp_path / "loc"
    subprocess.run(["git", "clone", "-q", "--depth=1", f"file://{remote}", str(loc)], check=True, capture_output=True)
    assert _git(loc, "rev-parse", "--is-shallow-repository") == "true"
    return remote, loc, base, tip


def _catalog(monkeypatch, loc):
    monkeypatch.setattr(kaku, "catalog_source", lambda: ({"installLocation": str(loc)}, None))


def test_浅い_clone_で深い所の急ぎも段に足して見つける(tmp_path, monkeypatch):
    """注入: 窓が取った先端が浅い clone の 60 本下（1 段目の --deepen=50 では届かない）→ 2 段目で届き、急ぎを返す。"""
    _remote, loc, base, tip = _history(tmp_path, after=60)
    _catalog(monkeypatch, loc)
    assert kaku.urgent_since(base, tip) == ["急ぎの安全: 深い所の穴を塞ぐ"]


def test_浅い_clone_で歴史を取れない時は急ぎ無しと言わず名指す(tmp_path, monkeypatch):
    """注入: 出所を無い場所へ向ける → 空（急ぎ無し）でなく Incomparable で、どの先端からどの先端かを名指す。"""
    _remote, loc, base, tip = _history(tmp_path, after=3)
    _git(loc, "remote", "set-url", "origin", f"file://{tmp_path / '無い.git'}")
    _catalog(monkeypatch, loc)
    with pytest.raises(kaku.Incomparable) as e:
        kaku.urgent_since(base, tip)
    assert base[:12] in str(e.value) and tip[:12] in str(e.value) and "取って来られない" in str(e.value)


def test_窓が取った先端が今の先端の祖先に無ければ名指す(tmp_path, monkeypatch):
    _remote, loc, _base, tip = _history(tmp_path, after=1)
    other = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    (other / "x").write_text("x\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-qm", "別の歴史")
    stray = _git(other, "rev-parse", "HEAD")
    _git(loc, "fetch", "-q", str(other), stray)
    _catalog(monkeypatch, loc)
    with pytest.raises(kaku.Incomparable, match="祖先に無い"):
        kaku.urgent_since(stray, tip)


def _plugins_line(text):
    return next(line for line in text.splitlines() if "変わった plugin:" in line)


def test_2_回目の知らせは届けた後に変わった_plugin_だけを挙げる(tmp_path):
    """注入: 1 回目に guard の急ぎを届けた後、checker と核の急ぎを入れる → 2 回目の「変わった plugin」に guard を挙げない。"""
    f = Foundation(tmp_path)
    _with_entry(f)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/a.py": "a\n", "plugins/core/核.md": "核 3\n"}, "急ぎの安全: 守りを塞ぐ")
    first = f.hook("fresh")
    assert "guard" in _plugins_line(first)
    _commit(f.work, {"plugins/checker/b.py": "b\n", "plugins/core/核.md": "核 4\n"}, "急ぎの安全: 照らしを塞ぐ")
    second = f.hook("fresh")
    line = _plugins_line(second)
    assert "checker" in line and "core" in line and "guard" not in line, line
