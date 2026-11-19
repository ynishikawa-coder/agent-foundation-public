"""scripts/call_flows.py: plugin が plugin の外の土台の部品（例 public-guard）の道具を借りる流れも拾い、
絵に箱か矢印が無ければ赤にするか（注入の試験）。

なぜ在るか: call_flows が plugin どうしの呼び出ししか拾わず、guard・session-watch が public-guard/guard.py の
秘密の形を借りる流れを、レビューの窓が人の目で見つけるまで絵から漏らしていた（原因の台帳の行）。
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base_out", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run, picture = _base.put, _base.git, _base.run, _base.picture
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)


@pytest.fixture
def outside(fake):
    put(fake, "gate/check.py", "print(1)\n")                         # plugin の外の土台の部品
    put(fake, "plugins/alpha/scripts/c.py", "PATH = 'gate/check.py'\n")
    put(fake, "docs/tool.py", "x = 1\n")                             # docs は部品でない
    put(fake, "plugins/alpha/scripts/d.py", "P = 'docs/tool.py'\n")
    git(fake, "add", "-A")
    return fake


def test_外の部品の道具を_path_で借りる流れを拾う(outside):
    res = run("list", "--repo", str(outside))
    assert "alpha → gate  plugins/alpha/scripts/c.py:1 check.py" in res.stdout, res.stdout
    assert "→ docs" not in res.stdout


def test_外の部品の箱が無ければ_絵に無い箱で赤(outside, tmp_path):
    res = run("check", str(picture(tmp_path, [("x0", "x1")])), "--repo", str(outside))
    assert res.returncode == 1, res.stdout
    assert "絵に無い箱: gate" in res.stdout
    assert "絵に無い流れ: alpha → gate" in res.stdout


def test_外の部品の箱は在るが矢印が無ければ赤_在れば緑(outside, tmp_path):
    boxes = ("alpha", "beta", "gate")
    res = run("check", str(picture(tmp_path, [("x0", "x1")], boxes)), "--repo", str(outside))
    assert res.returncode == 1 and "絵に無い流れ: alpha → gate（x0 → x2）" in res.stdout, res.stdout
    res = run("check", str(picture(tmp_path, [("x0", "x1"), ("x0", "x2")], boxes)), "--repo", str(outside))
    assert res.returncode == 0, res.stdout
