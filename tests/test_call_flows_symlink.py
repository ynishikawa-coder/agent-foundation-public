"""scripts/call_flows.py: plugin の外の実体を指す symlink（例: plugins/<名>/lib/skill_values.py → skill-values/）の中身を、
symlink を置いた plugin の呼び出しとして拾わないか（注入の試験）。

なぜ在るか: 値の表の読み口を 1 本にした直しで、各 plugin の lib/ に土台の skill-values/ への symlink が置かれた。
call_flows は file の置き場所で持ち主を決めていたので、共通の口の説明文に出る道具の名（check.mjs・codex_pack.py・kaku.py）を
symlink を置いた plugin からの呼び出しと数え、無い流れ 4 本で赤になった。
"""
import importlib.util
import os
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base_link", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run = _base.put, _base.git, _base.run
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)

SHARED_TEXT = "# 共通の口。使う道具の例: judge.py\n"


def _link(repo, rel, target):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(repo / target, p.parent), p)


def test_外の実体を指す_symlink_の中身は置いた_plugin_の流れにしない(fake):
    put(fake, "shared/reader.py", SHARED_TEXT)
    _link(fake, "plugins/alpha/lib/reader.py", "shared/reader.py")
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert "plugins/alpha/lib/reader.py" not in res.stdout, res.stdout


def test_同じ中身を_plugin_の実体に置けば流れとして拾う(fake):
    """直しを外した時の形（symlink でなく plugin の file）は拾う＝拾う力は落ちていない。"""
    put(fake, "plugins/alpha/lib/reader.py", SHARED_TEXT)
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert "alpha → beta  plugins/alpha/lib/reader.py:1 judge.py" in res.stdout, res.stdout


def test_plugin_の中を指す_symlink_は今までどおり拾う(fake):
    put(fake, "plugins/alpha/scripts/real.py", SHARED_TEXT)
    _link(fake, "plugins/alpha/lib/reader.py", "plugins/alpha/scripts/real.py")
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert "alpha → beta  plugins/alpha/lib/reader.py:1 judge.py" in res.stdout, res.stdout
