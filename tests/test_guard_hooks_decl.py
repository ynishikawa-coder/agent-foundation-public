"""guard の入口は見張りの一覧を持たず、各見張りの頭の HOOKS を読んで回すか（注入の試験）。

並ぶ PR が入口の 1 行（見張りの一覧）へ足して 2 回続けて衝突した。見張りを足す PR は自分の file だけを足す形にする。
"""
import shutil
import subprocess
import sys
import json
from pathlib import Path

import pytest

from test_guard import env  # noqa: F401  （fixture）
from uses import py_code

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"
HELPERS = {"guard", "guard_common", "ask_basis"}  # ask_basis は ask_shape の知らせから呼ぶ部品（守りの数に入れない）


def test_見張りの_file_は全部_HOOKS_を宣言する():
    import ast
    missing = []
    for p in sorted(SCRIPTS.glob("*.py")):
        if p.stem in HELPERS:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        if not any(isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HOOKS" for t in n.targets) for n in tree.body):
            missing.append(p.name)
    assert not missing, f"HOOKS の無い見張り（宣言が無いと回らない）: {missing}"


def test_入口に見張りの一覧を写さない():
    text = py_code((SCRIPTS / "guard.py").read_text(encoding="utf-8"))   # 注釈で前の形の名を挙げるのは写しでない
    assert "WATCHERS" not in text and '("irreversible", "check")' not in text


@pytest.fixture
def copy(tmp_path):
    # scripts と隣の lib（値の表の 1 本の口・正本への symlink は実体で写る＝入れた plugin と同じ形）を写す
    shutil.copytree(SCRIPTS, tmp_path / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(SCRIPTS.parent / "lib", tmp_path / "lib", ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path / "scripts"


def pre(env, scripts, cmd):
    p = subprocess.run([sys.executable, "-B", str(scripts / "guard.py"), "pre"], capture_output=True, text=True, env=env,
                       input=json.dumps({"tool_name": "Bash", "session_id": "s1", "tool_input": {"command": cmd}}))
    return p.stdout


def test_HOOKS_を書いた見張りの_file_を足すだけで回り_宣言を消すと回らない(env, copy):
    (copy / "zz_sakumono.py").write_text(
        'HOOKS = {"pre": "check"}\n\n\ndef check(data, vals):\n'
        '    return "作り物の見張り" if "sakumono" in str(data.get("tool_input")) else ""\n', encoding="utf-8")
    assert "作り物の見張り" in pre(env, copy, "echo sakumono")
    (copy / "zz_sakumono.py").write_text(
        'def check(data, vals):\n    return "作り物の見張り"\n', encoding="utf-8")
    assert "作り物の見張り" not in pre(env, copy, "echo sakumono")


def test_宣言の壊れた見張りは他を巻き込まない(env, copy):
    (copy / "zz_broken.py").write_text("HOOKS = {'pre': check_func_not_literal}\n", encoding="utf-8")
    assert "seal.py" in pre(env, copy, "python3 型/check_spec_doc.py 設計書 --lock")
