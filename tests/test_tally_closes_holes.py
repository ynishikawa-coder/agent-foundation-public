"""試験の入口と数える plugin が、照らしていない試験・環境の差し替え・結果の書き換えを緑に数えないか（注入の試験）。

原因の台帳 束 F1 の行ごとに、その誤りを小箱に入れて check_all が赤になる（か名指す）のを見る:
- 環境の側（PYTHONPATH の sitecustomize・.pth）と根の pytest.py が本物の代わりに動く → 入口が python3 -I -S で閉じる
- conftest の pytest_plugins・知らない plugin → 読まれた plugin を全部照らして赤
- conftest の hook（logreport の tryfirst・makereport・report_teststatus・集めの絞り）が結果や集めを変える → 赤
- file の名・__test__ = False・__init__ の在る class・collect_ignore・pytest_ignore_collect で試験を集めない → 赤
- 待つ物の表の path を表の外の試験が待つ → 赤
- pytest の版が 1 か所の版と違う → CI で赤・手元で名指す
- 手元の飛ばしは試験の名（node id）で名指す（conftest の 1 行に束ねない）
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from entry_box import box_env, copy_entry

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "pytest_plugin"))
import af_tally  # noqa: E402

OK = "def test_ok():\n    pass\n"


def box(tmp_path, files=None, conftest=None):
    root = copy_entry(tmp_path / "box")
    (root / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "waits.py", root / "tests" / "waits.py")
    (root / "tests" / "test_ok.py").write_text(OK, encoding="utf-8")
    for name, body in (files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")
    if conftest:
        (root / "tests" / "conftest.py").write_text(conftest, encoding="utf-8")
    return root


def check_all(root, ci=False, **env):
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True, text=True,
                       env=box_env(ci=ci, **env), timeout=300)
    return r.returncode, r.stdout.strip().splitlines()[-1], r.stdout + r.stderr


def test_合格_今の形の小箱は緑(tmp_path):
    code, last, out = check_all(box(tmp_path))
    assert code == 0 and last.startswith("check_all: 緑"), out


# ---- 環境の側を閉じる -----------------------------------------------------------------------------

def test_注入_PYTHONPATH_の_sitecustomize_は読まれない(tmp_path):
    side = tmp_path / "side"
    side.mkdir()
    (side / "sitecustomize.py").write_text("import os\nos.environ['AF_HIJACK'] = '1'\n", encoding="utf-8")
    body = ("import os, sys\n\ndef test_閉じている():\n    assert 'AF_HIJACK' not in os.environ\n"
            "    assert sys.flags.no_site == 1 and sys.flags.isolated == 1\n"
            "    assert 'sitecustomize' not in sys.modules\n")
    code, last, out = check_all(box(tmp_path, {"tests/test_env.py": body}), PYTHONPATH=str(side))
    assert code == 0 and last.startswith("check_all: 緑"), out


def test_注入_根の_pytest_py_は本物の代わりに動かない(tmp_path):
    fake = "print('1 passed')\nraise SystemExit(0)\n"
    root = box(tmp_path, {"pytest.py": fake, "tests/test_bad.py": "def test_bad():\n    assert False\n"})
    code, last, out = check_all(root)
    assert code == 1 and "test_bad" in out, out


def test_注入_conftest_の_pytest_plugins_は赤(tmp_path):
    root = box(tmp_path, {"tests/af_extra.py": "def pytest_report_teststatus(report, config):\n    return None\n"},
               conftest="pytest_plugins = ['af_extra']\n")
    code, last, out = check_all(root)
    assert code == 1 and "pytest_plugins" in out and "知らない plugin" in out, out


# ---- conftest の hook が結果・集めを変える ---------------------------------------------------------

LOGREPORT = ("import pytest\n\n@pytest.hookimpl(tryfirst=True)\ndef pytest_runtest_logreport(report):\n"
             "    if report.skipped:\n        report.outcome = 'passed'\n")
MAKEREPORT = ("import pytest\n\n@pytest.hookimpl(hookwrapper=True, tryfirst=True)\ndef pytest_runtest_makereport(item, call):\n"
              "    o = yield\n    r = o.get_result()\n    if r.skipped:\n        r.outcome = 'passed'\n")
TESTSTATUS = "def pytest_report_teststatus(report, config):\n    if report.skipped:\n        return 'passed', '.', 'PASSED'\n"
FOLD = ("def pytest_collection_modifyitems(config, items):\n    items[:] = [i for i in items if 'skip' not in i.name]\n")
IGNORE_HOOK = "def pytest_ignore_collect(collection_path, config):\n    return collection_path.name == 'test_gone.py'\n"


@pytest.mark.parametrize("conf", [LOGREPORT, MAKEREPORT, TESTSTATUS, FOLD, IGNORE_HOOK],
                         ids=["logreport", "makereport", "teststatus", "絞り", "ignore_collect"])
def test_注入_結果や集めを変える_conftest_の_hook_は赤(tmp_path, conf):
    skip = "import pytest\n\ndef test_skip():\n    pytest.skip('作り物')\n"
    root = box(tmp_path, {"tests/test_s.py": skip, "tests/test_gone.py": OK.replace("ok", "gone")}, conftest=conf)
    for ci in (False, True):
        code, last, out = check_all(root, ci=ci)
        assert code == 1 and "conftest が hook" in out, out


def test_注入_hook_を通さず報告の結果を書き換えると名指す(tmp_path):
    """conftest でなくても（hook の照らしの外から）作った後の報告を書き換えれば「書き換えた」と残る。"""
    data = {"finished": True, "results": [{"nodeid": "t::a", "outcome": "passed"}], "deselected": [], "dropped": [],
            "unrun": [], "audit": ["t::b: 報告の結果が作った後に skipped から passed へ書き換えられた"], "unseen": [],
            "pytest": af_tally.pinned_version()}
    n, bad, _ = af_tally.judge(data, str(ROOT), ci=False)
    assert any("書き換えられた" in b for b in bad)


# ---- 書いた試験を集めない ---------------------------------------------------------------------------

@pytest.mark.parametrize("files,conf,missing", [
    ({"tests/check_x.py": OK.replace("ok", "x")}, None, "tests/check_x.py::test_x"),
    ({"tests/test_n.py": "__test__ = False\n\n" + OK.replace("ok", "n")}, None, "tests/test_n.py::test_n"),
    ({"tests/test_c.py": "class TestC:\n    def __init__(self):\n        pass\n\n    def test_c(self):\n        pass\n"},
     None, "tests/test_c.py::TestC::test_c"),
    ({"tests/test_i.py": OK.replace("ok", "i")}, "collect_ignore = ['test_i.py']\n", "collect_ignore"),
], ids=["file の名", "__test__", "__init__", "collect_ignore"])
def test_注入_書いた試験を集めないと赤(tmp_path, files, conf, missing):
    code, last, out = check_all(box(tmp_path, files, conftest=conf))
    assert code == 1 and missing in out, out


# ---- 待つ物の表は待つ試験の file と結ぶ ----------------------------------------------------------------

def test_注入_表の_path_を表の外の試験が待つと赤(tmp_path):
    wait = "from waits import wait_for\n\ndef test_w():\n    wait_for('docs/作り物.json', '作り物')\n"
    root = box(tmp_path, {"tests/test_a.py": wait, "tests/test_b.py": wait})
    (root / "tests" / "waits.txt").write_text("docs/作り物.json  tests/test_a.py  作り物\n", encoding="utf-8")
    code, last, out = check_all(root)
    assert code == 1 and "tests/test_b.py::test_w" in out and "待ってよいのは表の tests/test_a.py だけ" in out, out
    assert "tests/test_a.py::test_w: 待つ物" not in out, out


def test_注入_待つ物の表の行に試験の_file_が無いと止まる(tmp_path):
    root = box(tmp_path)
    (root / "tests" / "waits.txt").write_text("docs/作り物.json  作り物\n", encoding="utf-8")
    code, last, out = check_all(root)
    assert code == 1 and "数える段が止まった" in out, out


# ---- pytest の版 ---------------------------------------------------------------------------------

def _data(version):
    return {"finished": True, "results": [{"nodeid": "t::a", "outcome": "passed"}], "deselected": [], "dropped": [],
            "unrun": [], "audit": [], "unseen": [], "pytest": version}


def test_注入_pytest_の版が違うと_CI_で赤_手元で名指す():
    _, bad, named = af_tally.judge(_data("0.0.1"), str(ROOT), ci=True)
    assert any("pytest の版 0.0.1" in b for b in bad)
    _, bad, named = af_tally.judge(_data("0.0.1"), str(ROOT), ci=False)
    assert not bad and any("pytest の版 0.0.1" in x for x in named)
    assert af_tally.judge(_data(af_tally.pinned_version()), str(ROOT), ci=True)[1] == []


def test_CI_は_pytest_を版の_1_か所から入れる():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip install --quiet pytest " not in ci and "pip install --quiet pytest\n" not in ci
    assert ci.count("-r scripts/pytest_plugin/requirements.txt") == 2   # job check と job plugin-smoke


# ---- 手元の飛ばしを試験の名で名指す --------------------------------------------------------------------

def test_手元の飛ばしは試験の名で名指す(tmp_path):
    conf = ("import pytest\n\ndef pytest_runtest_setup(item):\n    if 'skip' in item.name:\n"
            "        pytest.skip('作り物の条件')\n")
    root = box(tmp_path, {"tests/test_s.py": "def test_skip_a():\n    pass\n\ndef test_skip_b():\n    pass\n"},
               conftest=conf)
    code, last, out = check_all(root)
    assert code == 0, out
    assert "tests/test_s.py::test_skip_a" in out and "tests/test_s.py::test_skip_b" in out, out
