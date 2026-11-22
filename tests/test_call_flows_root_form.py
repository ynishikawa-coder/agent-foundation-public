"""scripts/call_flows.py: 手順の文が plugin の根を `<名>/…` と置いて道具を呼ぶ形も、流れとして拾うか（注入の試験）。"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("_call_flows_base", Path(__file__).resolve().parent / "test_call_flows.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)
put, git, run = _base.put, _base.git, _base.run
fake = pytest.fixture(_base.fake.__wrapped__ if hasattr(_base.fake, "__wrapped__") else _base.fake)


def test_plugin_の根を置き換えて書いた_path_も拾う(fake, tmp_path):
    """手順の文が `<beta>/scripts/x.py` と plugin の根を置いた形で道具を呼ぶのを拾い漏らさない（拾い漏らすと絵から流れが漏れる）。"""
    put(fake, "plugins/beta/scripts/scan.py", "print(1)\n")
    put(fake, "scripts/scan.py", "x = 3\n")                    # 外にも同じ名＝名だけでは拾わない
    put(fake, "plugins/alpha/skills/s/SKILL.md", "1. 呼ばない。\n")       # 拾う流れをこの 1 本だけにする
    put(fake, "plugins/alpha/skills/t/SKILL.md", "1. `python3 <beta>/scripts/scan.py check` を回す。\n")
    git(fake, "add", "-A")
    res = run("list", "--repo", str(fake))
    assert "plugins/alpha/skills/t/SKILL.md:1 scan.py" in res.stdout, res.stdout
