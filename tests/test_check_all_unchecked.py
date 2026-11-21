"""照らしていない検査と飛ばした試験を、check_all が緑に数えないか（注入の試験）。

前の形: scripts/checks の「照らしていない」分岐（PR の外の pr_writer・main や人の枝の pr_shape・CI の public_guard）は
exit 0 で終わり、check_all は緑の本数に数えた。pytest の飛ばした試験は数も理由も出さず、前提が満ちた後も
飛ばす条件が残り（marketplace.json が在るのに「まだ無い」）、CI に部品（playwright）が無くて飛ぶ試験も緑のままだった。
今の形: 照らしていない検査は exit 3 で check_all が名指して緑に数えない。飛ばした試験は理由ごとに数え、
「待ち: <path>」の前提が在るのに飛べば赤、CI では印 real_claude の外の飛ばしを赤にする。
"""
import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from entry_box import box_env, copy_entry

ROOT = Path(__file__).resolve().parent.parent
REAL_CLAUDE_REASON = "claude の命令が無い所では飛ばす（CI の job plugin-smoke が -m real_claude で回す）"


def box(tmp_path, tests=None, checks=None):
    """check_all を写した小箱（試験と検査は作り物）。"""
    copy_entry(tmp_path)
    (tmp_path / "scripts" / "checks").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    for name, body in (tests or {"test_ok.py": "def test_ok():\n    pass\n"}).items():
        (tmp_path / "tests" / name).write_text(body, encoding="utf-8")
    for name, body in (checks or {}).items():
        (tmp_path / "scripts" / "checks" / name).write_text(body, encoding="utf-8")
    return tmp_path


def run(root, **env):
    e = box_env(**env)
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True, text=True, env=e, timeout=300)
    return r.returncode, r.stdout.strip().splitlines()[-1], r.stdout


def skip_test(reason):
    return {"test_ok.py": "def test_ok():\n    pass\n",
            "test_skip.py": f"import pytest\n\ndef test_s():\n    pytest.skip({reason!r})\n"}


def test_注入_照らさない分岐の検査を緑に数えない(tmp_path):
    """本物の pr_writer.sh を PR の外で回す（照らさない分岐）。前の形（exit 0）なら「緑 2/2 本」と数えた。"""
    root = box(tmp_path)
    shutil.copy2(ROOT / "scripts" / "checks" / "pr_writer.sh", root / "scripts" / "checks" / "pr_writer.sh")
    code, last, out = run(root)
    assert "pr_writer: 照らしていない" in out
    assert code == 0 and last.startswith("check_all: 緑"), last
    assert "緑 1/2 本" in last and "照らしていない 1 本: pr_writer.sh" in last, last


@pytest.mark.parametrize("rel,env", [
    ("scripts/checks/public_guard.sh", {"GITHUB_ACTIONS": "true"}),
    ("scripts/checks/pr_writer.sh", {"GITHUB_EVENT_NAME": "push"}),
])
def test_照らさない分岐はどれも_exit_3(rel, env):
    e = box_env(**env)
    r = subprocess.run(["bash", str(ROOT / rel)], capture_output=True, text=True, env=e, timeout=120)
    assert r.returncode == 3 and "照らしていない" in r.stdout, (rel, r.returncode, r.stdout)


def test_pr_shape_の照らさない分岐は_exit_3():
    spec = importlib.util.spec_from_file_location("af_pr_shape_for_unchecked", ROOT / "scripts" / "pr_shape.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for branch in ("main", "HEAD", "patch-1"):
        assert mod.main(["--branch", branch, "--base", "origin/main"]) == 3, branch


def test_検査の終わり方_0_でも_3_でもなければ赤(tmp_path):
    root = box(tmp_path, checks={"x.sh": "exit 1\n"})
    code, last, _ = run(root)
    assert code == 1 and last.startswith("check_all: 赤") and "scripts/checks/x.sh" in last


def test_飛ばした試験を数えて名指す_手元は緑(tmp_path):
    root = box(tmp_path, tests=skip_test("playwright が無い"))
    code, last, _ = run(root)
    assert code == 0 and "pytest で飛ばした 1 本" in last, last


def test_注入_待つ物が在るのに飛ぶと赤(tmp_path):
    """前提が満ちた後も飛ばす条件が残る形（marketplace.json が在るのに「まだ無い」）。待つ物は印 af_wait_path で照らす。"""
    body = ("import pytest\n\ndef test_s():\n    e = pytest.skip.Exception('作り物')\n"
            "    e.af_wait_path = 'here.json'\n    raise e\n")
    root = box(tmp_path, tests={"test_ok.py": "def test_ok():\n    pass\n", "test_skip.py": body})
    (root / "tests" / "waits.txt").write_text("here.json  tests/test_skip.py  作り物\n", encoding="utf-8")
    code, last, _ = run(root)
    assert code == 0, last  # 待つ物が無い間は名指すだけ
    (root / "here.json").write_text("{}", encoding="utf-8")
    code, last, out = run(root)
    assert code == 1 and last.startswith("check_all: 赤") and "待つ物 here.json が在るのに飛んだ" in out, out


def test_注入_CI_で部品が無くて飛ぶと赤(tmp_path):
    root = box(tmp_path, tests=skip_test("playwright が無い"))
    code, last, out = run(root, GITHUB_ACTIONS="true")
    assert code == 1 and "CI で飛んだ（playwright が無い）" in out, out


def test_CI_では印_real_claude_の試験を印で外し飛ばしに数えない(tmp_path):
    """job plugin-smoke が回す印 real_claude の試験は、CI の job check では印の選びで外す（飛ばした理由の文で見分けない）。"""
    marked = "import pytest\npytestmark = pytest.mark.real_claude\n\ndef test_c():\n    pytest.skip('x')\n"
    root = box(tmp_path, tests={"test_ok.py": "def test_ok():\n    pass\n", "test_c_real_claude.py": marked})
    shutil.copy2(ROOT / "tests" / "conftest.py", root / "tests" / "conftest.py")
    code, last, out = run(root, GITHUB_ACTIONS="true")
    assert code == 0 and "pytest で飛ばした 0 本" in last and "印 real_claude で外した 1 本" in last, out


def test_注入_印の無い試験が_conftest_と同じ理由の文で飛んでも_CI_では赤(tmp_path):
    """前の形は理由の文の頭で印 real_claude の飛ばしを見分けたので、印の無い試験が同じ文で飛ぶと CI で通った。"""
    root = box(tmp_path, tests=skip_test(REAL_CLAUDE_REASON))
    shutil.copy2(ROOT / "tests" / "conftest.py", root / "tests" / "conftest.py")
    code, last, out = run(root, GITHUB_ACTIONS="true")
    assert code == 1 and "CI で飛んだ" in out, out
    assert REAL_CLAUDE_REASON.split("（")[0] not in (ROOT / "scripts" / "check_all.sh").read_text(encoding="utf-8")


def test_この_repo_の飛ばす理由は_待ち_か_部品の名を書く():
    """tests/ の skip のうち前提の file を待つ物は tests/waits.py の wait_for で書く（check_all が印の path を照らす）。"""
    text = (ROOT / "tests" / "test_call_flows.py").read_text(encoding="utf-8")
    assert 'wait_for(PICTURE' in text and 'PICTURE = "docs/全体の絵.json"' in text
    assert "がまだ無い" not in (ROOT / "tests" / "test_plugins_list.py").read_text(encoding="utf-8")


def test_CI_の_job_check_は_node_と_playwright_を入れる():
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = yml.split("\n  check:\n", 1)[1].split("\n  overlap:", 1)[0]
    assert "actions/setup-node@" in job
    py = re.search(r"pip install[^\n]*playwright==([\d.]+)", job)
    js = re.search(r"npm install -g[^\n]*playwright@([\d.]+)", job)
    assert py and js and py.group(1) == js.group(1), "python と node の playwright の版が揃わない"
    assert "playwright install --with-deps chromium" in job and "NODE_PATH" in job


def test_注入_出した_plugin_の行が_0_なら何も照らさずに通らない(monkeypatch):
    spec = importlib.util.spec_from_file_location("af_plugins_list_for_unchecked", ROOT / "tests" / "test_plugins_list.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "read_rows", lambda: [])
    with pytest.raises(AssertionError, match="「出した」plugin の行が 0"):
        mod.test_出した_plugin_は中身と_skills_が一致()
