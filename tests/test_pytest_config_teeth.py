"""pytest の設定の file や PYTEST_ADDOPTS で試験を黙って減らしても、check_all が緑にならないか（注入の試験）。

前の形: check_all・scripts/checks/conftest_teeth.sh・CI の job plugin-smoke は `python3 -m pytest` を直に呼び、
pytest は repo の pytest.ini・pyproject.toml・tox.ini・setup.cfg の addopts と PYTEST_ADDOPTS を足して回した。
addopts に `--co`（集めるだけ）を置くと 1 本も回らず exit 0 で「緑」、`--deselect`・`--ignore`・`-k` は黙って減らす。
conftest_teeth の --noconftest は conftest だけを外すので、この道は照らしの外だった。
今の形: 試験はどこからも 1 つの入口 scripts/pytest.sh で回し、入口が設定の file と PYTEST_ADDOPTS を読まない
（`-c /dev/null`）。設定で減らす道そのものが無い。
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "scripts/pytest.sh"

# 落ちる試験 1 本だけの小箱に置く設定。どれも直す前は check_all を緑にした（1 本も回さない・回す物を減らす）。
CONFIGS = {
    "pytest.ini": "[pytest]\naddopts = --co\n",
    ".pytest.ini": "[pytest]\naddopts = --co\n",
    "pyproject.toml": "[tool.pytest.ini_options]\naddopts = \"--co\"\n",
    "tox.ini": "[pytest]\naddopts = --co\n",
    "setup.cfg": "[tool:pytest]\naddopts = --co\n",
}


def box(tmp_path, config=None):
    for rel in ["scripts/check_all.sh", ENTRY]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_box.py").write_text(
        "def test_回れば落ちる():\n    assert False\n\ndef test_回れば通る():\n    pass\n", encoding="utf-8")
    if config:
        name, text = config
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def check_all(root, **env):
    e = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    e.update(env)
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True, text=True, env=e, timeout=120)
    return r.returncode, r.stdout + r.stderr


def test_合格_設定の無い小箱では落ちる試験で赤(tmp_path):
    code, out = check_all(box(tmp_path))
    assert code != 0 and "1 failed, 1 passed" in out, out


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_注入_設定の_file_の_addopts_で回さない形は効かず赤のまま(tmp_path, name):
    code, out = check_all(box(tmp_path, (name, CONFIGS[name])))
    assert code != 0 and "1 failed, 1 passed" in out, out


@pytest.mark.parametrize("opts", ["--co", "--deselect tests/test_box.py::test_回れば落ちる", "-k 通る",
                                  "--ignore=tests/test_box.py"])
def test_注入_PYTEST_ADDOPTS_で減らす形は効かず赤のまま(tmp_path, opts):
    code, out = check_all(box(tmp_path), PYTEST_ADDOPTS=opts)
    assert code != 0 and "1 failed, 1 passed" in out, out


def test_注入_設定の_file_の_addopts_で減らす形も効かない(tmp_path):
    code, out = check_all(box(tmp_path, ("pytest.ini", "[pytest]\naddopts = -k 通る\n")))
    assert code != 0 and "deselected" not in out, out


DIRECT = re.compile(r"python3? -m pytest|[\"']-m[\"'],\s*[\"']pytest[\"']|^\s*(run:\s*)?pytest\s", re.M)


def direct_callers():
    """入口を通らず pytest を直に呼ぶ検査・CI の定義（試験の中の小箱の回し方は除く）。"""
    files = [*ROOT.glob("scripts/**/*.sh"), *ROOT.glob("scripts/**/*.py"), *ROOT.glob(".github/workflows/*.yml")]
    return sorted(str(p.relative_to(ROOT)) for p in files
                  if p.relative_to(ROOT).as_posix() != ENTRY and DIRECT.search(p.read_text(encoding="utf-8")))


def test_検査と_CI_は入口を通して試験を回す():
    assert direct_callers() == []


def test_注入_直に呼ぶ行を拾う():
    for text in ["out=$(python3 -m pytest -q tests/)\n", "        run: pytest -q tests/\n",
                 "subprocess.run([sys.executable, '-m', 'pytest', 'tests'])\n"]:
        assert DIRECT.search(text), text
