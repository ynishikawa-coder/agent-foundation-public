"""guard の入口は見張りの一覧を持たず、各見張りの頭の HOOKS を読んで回すか（注入の試験）。

並ぶ PR が入口の 1 行（見張りの一覧）へ足して 2 回続けて衝突した。見張りを足す PR は自分の file だけを足す形にする。
"""
import shutil
import subprocess
import sys
import json
import re
from pathlib import Path

import pytest

from test_guard import env  # noqa: F401  （fixture）

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "guard" / "scripts"
HELPERS = {"guard", "guard_common"}


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


def watcher_names(scripts=SCRIPTS):
    """HOOKS を宣言した見張りの名（file の名）の集合。見張りの名は字で並べず、宣言から読む。"""
    import ast
    out = set()
    for p in sorted(scripts.glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HOOKS" for t in n.targets) for n in tree.body):
            out.add(p.stem)
    return out


def entry_copies(source, names):
    """入口の Python を ast で読み、見張りの名を持つ字の値・見張りの import（＝入口に写した一覧）の並び。
    空白・引用符・並びの形（list・tuple・dict）・変数の名（WATCHERS でも HOOK_TABLE でも）を問わない。説明の字（docstring）は外す。"""
    import ast
    tree = ast.parse(source)
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs \
                and any(w == n.value or w in re.split(r"[^\w]+", n.value) for w in names):
            out.append(f"{n.lineno} 行目の字 {n.value!r}")
        elif isinstance(n, ast.Import) and any(a.name in names for a in n.names):
            out.append(f"{n.lineno} 行目の import")
        elif isinstance(n, ast.ImportFrom) and n.module in names:
            out.append(f"{n.lineno} 行目の from import")
    return out


def test_入口に見張りの一覧を写さない():
    names = watcher_names()
    assert len(names) >= 3, names   # 照らす相手が空のまま緑にしない
    assert entry_copies((SCRIPTS / "guard.py").read_text(encoding="utf-8"), names) == []


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
