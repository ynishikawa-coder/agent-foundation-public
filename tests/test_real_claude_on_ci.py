"""本物の claude を要る試験が CI で 1 度も回らない形が戻らないか（注入の試験）。

前の形: 試験の file ごとに「claude が無ければ飛ばす」を書き、CI の job plugin-smoke の pytest の行に file を手で並べていた。
並べ忘れた試験は claude の無い job check で飛ばされ、どこでも回らなかった。今の形:
- 飛ばす条件は tests/conftest.py の 1 か所（印 real_claude の試験だけ）。試験の file は印を付けるだけ。
- plugin-smoke は `pytest -m real_claude tests/` で印の試験を全部拾う。
- 印を付け忘れた試験は飛ばされず、claude の無い job check で赤になる。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFTEST = ROOT / "tests" / "conftest.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"
OWN_SKIP = re.compile(r"""(?:\bnot\s+shutil\.which|skipif\([^)]*which)\(\s*["']claude["']""")


def own_skips(files):
    """conftest の外で claude の有る無しを見て飛ばす file（並べ忘れると黙って飛ぶ道）を返す。"""
    return [name for name, text in files if name != "conftest.py" and OWN_SKIP.search(text)]


def smoke_pytest_lines(yml):
    """job plugin-smoke の中の pytest の行を返す。"""
    m = re.search(r"(?ms)^  plugin-smoke:\n(.*?)(?=^  \S|\Z)", yml)
    assert m, "ci.yml に job plugin-smoke が無い"
    return [ln.strip() for ln in m.group(1).splitlines() if "pytest" in ln and "run:" in ln]


def ci_problems(yml):
    lines = smoke_pytest_lines(yml)
    if lines != ["run: python3 -m pytest -q -m real_claude tests/"]:
        return [f"plugin-smoke の pytest の行が印で拾う形でない: {lines}"]
    return []


def _tests():
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted((ROOT / "tests").rglob("*.py"))]


def test_試験の_file_は自分で_claude_の有る無しを見て飛ばさない():
    assert own_skips(_tests()) == []


def test_自分で飛ばす_file_を入れると拾う():
    bad = "if not shutil.which('" + "claude'):\n    pytest.skip('x', allow_module_level=True)\n"
    assert own_skips([("test_x_real_claude.py", bad)]) == ["test_x_real_claude.py"]


def test_plugin_smoke_は印で全部拾う():
    assert ci_problems(CI.read_text(encoding="utf-8")) == []


def test_file_を手で並べる行を入れると拾う():
    yml = CI.read_text(encoding="utf-8").replace(
        "-m real_claude tests/", "tests/test_plugin_smoke.py tests/test_setup_plugins_real_claude.py")
    assert ci_problems(yml)


def test_印の試験はどれも_real_claude_の印を持つ():
    named = [n for n, t in _tests() if n.endswith("_real_claude.py") or n == "test_plugin_smoke.py"]
    assert named and all("pytest.mark.real_claude" in t for n, t in _tests() if n in named)


def _run_box(tmp_path, body, require):
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_box.py").write_text(body, encoding="utf-8")
    env = dict(os.environ, PATH=str(tmp_path / "nobin"))  # claude の無い所
    env.pop("AF_REQUIRE_CLAUDE", None)
    if require:
        env["AF_REQUIRE_CLAUDE"] = "1"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    return r.returncode, r.stdout + r.stderr


MARKED = "import pytest\npytestmark = pytest.mark.real_claude\n\ndef test_a():\n    assert True\n"
UNMARKED_NEEDS = "import subprocess\n\ndef test_a():\n    subprocess.run(['clau' + 'de', '--version'], check=True)\n"


def test_claude_の無い所では印の試験だけ飛ばす(tmp_path):
    code, out = _run_box(tmp_path, MARKED, require=False)
    assert code == 0 and "1 skipped" in out, out


def test_AF_REQUIRE_CLAUDE_では印の試験を飛ばさず赤(tmp_path):
    code, out = _run_box(tmp_path, MARKED, require=True)
    assert code != 0 and "claude の命令が無い" in out, out


def test_印を付け忘れた試験は_claude_の無い所で赤(tmp_path):
    code, out = _run_box(tmp_path, UNMARKED_NEEDS, require=False)
    assert code != 0 and "1 failed" in out, out
