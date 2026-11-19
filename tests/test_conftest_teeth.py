"""tests/conftest.py の飛ばす条件が壊れたら、claude の無い所（手元・CI の job check）でも赤になるか（注入の試験）。

前の形: 飛ばす条件を照らす試験（tests/test_real_claude_on_ci.py）も同じ conftest の下で回るので、条件を
「全部飛ばす」形に壊すと照らす試験ごと飛ばされ、job check は全部 skip のまま緑だった。
今の形: scripts/checks/conftest_teeth.sh が conftest を読まない pytest（--noconftest）で照らす試験を回す。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECK = "scripts/checks/conftest_teeth.sh"
SETUP_GUARD = '    if item.get_closest_marker("real_claude") is None or shutil.which("claude"):\n        return\n'

BROKEN = {
    # 条件を抜いて、どの試験も飛ばす
    "全部飛ばす": lambda t: t.replace(SETUP_GUARD, ""),
    # 条件を逆にして、印の無い試験を飛ばす
    "逆にする": lambda t: t.replace('get_closest_marker("real_claude") is None', 'get_closest_marker("real_claude") is not None'),
    # 集める所で全部に skip の印を付ける
    "集める所で飛ばす": lambda t: t + "\n\ndef pytest_collection_modifyitems(config, items):\n"
                                      "    for i in items:\n        i.add_marker(pytest.mark.skip(reason='x'))\n",
}


def tree(tmp_path, conftest_text):
    """照らす検査・試験の dir・CI の定義を写した小箱（conftest だけ差し替える）。"""
    shutil.copytree(ROOT / "tests", tmp_path / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    for rel in [CHECK, ".github/workflows/ci.yml"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    (tmp_path / "tests" / "conftest.py").write_text(conftest_text, encoding="utf-8")
    return tmp_path


def env_without_claude(tmp_path):
    nobin = tmp_path / "nobin"
    nobin.mkdir(exist_ok=True)
    os.symlink(sys.executable, nobin / "python3")
    for tool in ("bash", "dirname", "grep", "tail"):
        if shutil.which(tool):
            os.symlink(shutil.which(tool), nobin / tool)
    env = dict(os.environ, PATH=str(nobin))
    env.pop("AF_REQUIRE_CLAUDE", None)
    return env


def run_check(root, env):
    r = subprocess.run(["bash", str(root / CHECK)], capture_output=True, text=True, env=env, cwd=root, timeout=300)
    return r.returncode, r.stdout + r.stderr


def test_合格_今の_conftest_では緑(tmp_path):
    root = tree(tmp_path / "box", (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    code, out = run_check(root, env_without_claude(tmp_path))
    assert code == 0 and "conftest_teeth: 緑" in out, out


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_注入_飛ばす条件を壊すと赤(tmp_path, name):
    text = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    broken = BROKEN[name](text)
    assert broken != text, "注入が当たっていない（conftest の形が変わった）"
    root = tree(tmp_path / "box", broken)
    env = env_without_claude(tmp_path)
    # 穴の再現: conftest の下の pytest だけでは照らす試験ごと飛ばされ、緑（または全部飛ばし）になる
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_real_claude_on_ci.py"],
                       capture_output=True, text=True, env=env, cwd=root, timeout=300)
    hole = r.returncode == 0
    code, out = run_check(root, env)
    assert code == 1 and "飛ばす条件が壊れている" in out, out
    if name == "全部飛ばす":
        assert hole and "skipped" in r.stdout, r.stdout


def test_注入_照らす試験が回らないと赤(tmp_path):
    """照らす試験の file が全部飛ばす印を持つ形も、回った本数 0 で赤（照らしていないのに緑と言わない）。"""
    root = tree(tmp_path / "box", (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    p = root / "tests" / "test_real_claude_on_ci.py"
    p.write_text(p.read_text(encoding="utf-8") + "\npytestmark = __import__('pytest').mark.skip(reason='x')\n",
                 encoding="utf-8")
    code, out = run_check(root, env_without_claude(tmp_path))
    assert code == 1, out
