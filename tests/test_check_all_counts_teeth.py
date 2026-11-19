"""check_all が照らしていない・飛ばした・外した・数え損ねた試験を緑に数えないか（注入の試験）。

前の形: check_all は pytest の人に見せる文（-rs の SKIPPED 行・要約の「N deselected」）を正規表現で読み、
飛ばしを数える python の段の終わり方を見なかった。そのため次の物が緑に数えられた（どれも小箱に入れて赤を確かめる）:
- 「待ち: <path>」の path が在りもしない物なら CI でも赤にしない（理由の文の字だけを読む）
- 飛ばす条件の path と理由の文の path が結ばれていない（条件は試験の中の別の値）
- xfail・xpass を数えない
- CI で外した試験を全部「印 real_claude で外した」と数え、本当にその印かを照らさない
- 数える段が落ちる・結果の文の形が変わる（色・fold_skipped）と 0 本として進む
- pytest.exit(returncode=0) で残りを回さず exit 0
（公開の検査が照合の一部を飛ばして exit 0 の類は tests/test_public_guard.py の注入の試験が照らす）
今の形: 入口 scripts/pytest.sh が必ず読む plugin（scripts/pytest_plugin/af_tally.py）が結果を構造で書き、
check_all はそれだけを数える。待つ物の飛ばしは tests/waits.py の wait_for だけが出す（条件と理由が 1 つの path）。
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from entry_box import copy_entry

ROOT = Path(__file__).resolve().parent.parent
OK = "def test_ok():\n    pass\n"


def box(tmp_path, tests, conftest=None, waits="docs/待つ作り物.json  作り物\n"):
    root = copy_entry(tmp_path / "box")
    (root / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "waits.py", root / "tests" / "waits.py")
    (root / "tests" / "waits.txt").write_text(waits, encoding="utf-8")
    (root / "tests" / "test_ok.py").write_text(OK, encoding="utf-8")
    for name, body in tests.items():
        (root / "tests" / name).write_text(body, encoding="utf-8")
    if conftest:
        (root / "tests" / "conftest.py").write_text(conftest, encoding="utf-8")
    return root


def run(root, ci=False, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_") and k != "AF_PYTEST_TALLY"}
    if ci:
        e["GITHUB_ACTIONS"] = "true"
    e.update(env)
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True, text=True, env=e, timeout=300)
    return r.returncode, r.stdout.strip().splitlines()[-1], r.stdout + r.stderr


def wait_test(rel):
    return "from waits import wait_for\n\ndef test_w():\n    wait_for(%r, '作り物')\n" % rel


def test_合格_待つ物の表に在る物を待つ飛ばしは_CI_でも名指すだけ(tmp_path):
    code, last, out = run(box(tmp_path, {"test_w.py": wait_test("docs/待つ作り物.json")}), ci=True)
    assert code == 0 and "pytest で飛ばした 1 本（待ち 1 本）" in last, out


def test_注入_待つ物の表に無い_path_を待つと赤(tmp_path):
    """在りもしない path を待つと書いて、CI で部品が無くて飛ぶ試験を隠す形（台帳の行: 待ちの path が無い限り赤にしない）。"""
    root = box(tmp_path, {"test_w.py": wait_test("docs/無い作り物.json")})
    for ci in (False, True):
        code, last, out = run(root, ci=ci)
        assert code == 1 and "待つ物の表" in out and "docs/無い作り物.json" in out, out


def test_注入_理由の文だけの待ちは待ちと見ない(tmp_path):
    """前の形は理由の文の頭「待ち: 」と path の字を読んだ。条件と結ばれない文だけの待ちは、CI では普通の飛ばし（赤）。"""
    body = "import pytest\n\ndef test_s():\n    pytest.skip('待ち: docs/無い作り物.json（作り物）が無い')\n"
    code, last, out = run(box(tmp_path, {"test_s.py": body}), ci=True)
    assert code == 1 and "CI で飛んだ" in out, out


def test_注入_待つ物が在るのに待ちの印で飛ぶと赤(tmp_path):
    """飛ばす条件が path と結ばれない形（印だけ付けて、在っても飛ぶ）。"""
    body = ("import pytest\n\ndef test_s():\n    e = pytest.skip.Exception('x')\n"
            "    e.af_wait_path = 'docs/待つ作り物.json'\n    raise e\n")
    root = box(tmp_path, {"test_s.py": body})
    (root / "docs").mkdir()
    (root / "docs" / "待つ作り物.json").write_text("{}", encoding="utf-8")
    code, last, out = run(root)
    assert code == 1 and "待つ物 docs/待つ作り物.json が在るのに飛んだ" in out, out


def test_wait_for_は在れば飛ばさない(tmp_path):
    root = box(tmp_path, {"test_w.py": wait_test("docs/待つ作り物.json")})
    (root / "docs").mkdir()
    (root / "docs" / "待つ作り物.json").write_text("{}", encoding="utf-8")
    code, last, out = run(root, ci=True)
    assert code == 0 and "pytest で飛ばした 0 本" in last, out


XFAIL = "import pytest\n\ndef test_x():\n    assert False\n\ntest_x = pytest.mark.xfail(reason='作り物')(test_x)\n"
XPASS = "import pytest\n\ndef test_x():\n    assert True\n\ntest_x = pytest.mark.xfail(reason='作り物')(test_x)\n"


def test_注入_xfail_は数えて名指し_CI_では赤(tmp_path):
    root = box(tmp_path, {"test_x.py": XFAIL})
    code, last, out = run(root)
    assert code == 0 and "xfail 1 本" in last, out
    code, last, out = run(root, ci=True)
    assert code == 1 and "CI でxfail で落ちた" in out, out


def test_注入_xpass_はいつも赤(tmp_path):
    code, last, out = run(box(tmp_path, {"test_x.py": XPASS}))
    assert code == 1 and "落ちる印（xfail）なのに通った" in out, out


DESELECT = ("def pytest_collection_modifyitems(config, items):\n"
            "    drop = [i for i in items if i.name == 'test_drop']\n"
            "    items[:] = [i for i in items if i.name != 'test_drop']\n"
            "    config.hook.pytest_deselected(items=drop)\n")


def test_注入_印の無い試験を_CI_で外すと赤(tmp_path):
    """前の形は CI の deselected を全部「印 real_claude で外した」と数えた。"""
    root = box(tmp_path, {"test_d.py": "def test_drop():\n    assert False\n"}, conftest=DESELECT)
    code, last, out = run(root, ci=True)
    assert code == 1 and "印 real_claude の無い試験を外した" in out, out


def test_合格_印_real_claude_の試験は_CI_で印で数えて外す(tmp_path):
    marked = "import pytest\npytestmark = pytest.mark.real_claude\n\ndef test_c():\n    pass\n"
    conf = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    code, last, out = run(box(tmp_path, {"test_c.py": marked}, conftest=conf), ci=True)
    assert code == 0 and "印 real_claude で外した 1 本" in last, out


def test_注入_数える段が止まると赤(tmp_path):
    """結果を書く plugin が壊れて何も書かない形（前の形は数える段が落ちても 0 本・赤なしで進んだ）。"""
    root = box(tmp_path, {})
    (root / "scripts" / "pytest_plugin" / "af_tally.py").write_text(
        "def pytest_configure(config):\n    pass\n", encoding="utf-8")
    code, last, out = run(root)
    assert code == 1 and "数える段が止まった" in last, out


def test_注入_結果の文の形を変えても飛ばしを数える(tmp_path):
    """色・fold_skipped で SKIPPED の行の形が変わると、前の形は 0 本と数えて CI でも緑にした。"""
    skip = "import pytest\n\ndef test_s():\n    pytest.skip('playwright が無い')\n"
    conf = "def pytest_configure(config):\n    config.option.fold_skipped = False\n"
    code, last, out = run(box(tmp_path, {"test_s.py": skip}, conftest=conf), ci=True, PY_COLORS="1")
    assert code == 1 and "CI で飛んだ（playwright が無い）" in out, out


def test_注入_module_の段の飛ばしも数える(tmp_path):
    body = "import pytest\npytest.skip('作り物', allow_module_level=True)\n\ndef test_a():\n    pass\n"
    code, last, out = run(box(tmp_path, {"test_m.py": body}), ci=True)
    assert code == 1 and "CI で飛んだ" in out, out


def test_注入_途中で_exit_0_して残りを回さないと赤(tmp_path):
    body = "import pytest\n\ndef test_a():\n    pytest.exit('作り物', returncode=0)\n\ndef test_b():\n    pass\n"
    code, last, out = run(box(tmp_path, {"test_e.py": body}))
    assert code == 1 and "回らないまま終わった" in out, out


def test_注入_通った試験が_0_本なら赤(tmp_path):
    root = box(tmp_path, {})
    (root / "tests" / "test_ok.py").write_text(
        "import pytest\n\ndef test_s():\n    pytest.skip('作り物')\n", encoding="utf-8")
    code, last, out = run(root)
    assert code == 1 and "通った試験が 0 本" in out, out


def test_合格_今の形の小箱は緑(tmp_path):
    code, last, out = run(box(tmp_path, {}))
    assert code == 0 and last.startswith("check_all: 緑") and "pytest で飛ばした 0 本" in last, out
