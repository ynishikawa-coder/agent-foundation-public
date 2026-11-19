"""小箱で検査の入口を回す試験が、環境を 1 か所（tests/entry_box.py の box_env）から作るか（注入の試験）。

前の形: 小箱で check_all を回す試験のうち GITHUB_* を消すのは一部だけで、test_check_all_sentan・test_pytest_config_teeth・
test_core_plugin は外の環境を受け継いだ。CI（GITHUB_ACTIONS=true）と手元で小箱が違う形で回るのに名指されなかった
（原因の台帳 束 F1）。今の形: 入口（check_all.sh・pytest.sh・scripts/checks/*.sh）を subprocess で回す呼び出しは、
env に box_env(...) か、同じ関数の中で box_env(...) から作った名を渡す。ここが AST で全部の呼び出しを照らす。
"""
import ast
from pathlib import Path

from entry_box import box_env

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ("check_all.sh", "pytest.sh", "scripts/checks", '"checks"')


def _runs_entry(call):
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in ("run", "Popen", "check_output", "call")):
        return False
    return bool(call.args) and any(e in ast.unparse(call.args[0]) for e in ENTRY)


def bad_calls(text, name="x.py"):
    """入口を回すのに環境を box_env から作っていない呼び出し（file:行）。名で渡す時は、呼び出しを囲む関数の中で
    box_env(...) から作った名だけを許す。"""
    tree = ast.parse(text)
    scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    # box_env(...) をそのまま返す関数の名（env = env_without_claude(tmp_path) のような手伝いの関数）
    makers = {"box_env"} | {f.name for f in scopes if any(isinstance(r, ast.Return) and r.value is not None
                                                           and "box_env(" in ast.unparse(r.value) for r in ast.walk(f))}
    made_by = lambda v: isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in makers  # noqa: E731
    out = []
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _runs_entry(call)):
            continue
        env = next((k.value for k in call.keywords if k.arg == "env"), None)
        ok = env is not None and "box_env(" in ast.unparse(env)
        if not ok and isinstance(env, ast.Name):
            inner = [f for f in scopes if f.lineno <= call.lineno <= f.end_lineno]
            scope = max(inner, key=lambda f: f.lineno) if inner else tree
            ok = any(isinstance(a, ast.Assign) and made_by(a.value)
                     and any(isinstance(t, ast.Name) and t.id == env.id for t in a.targets) for a in ast.walk(scope))
        if not ok:
            out.append(f"{name}:{call.lineno}")
    return out


def test_入口を回す試験はどれも_box_env_の環境で回す():
    found = []
    for p in sorted((ROOT / "tests").rglob("*.py")):
        found += bad_calls(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))
    assert found == [], found


def test_注入_外の環境を受け継いで回すと拾う():
    text = ('import subprocess\n\ndef run(root):\n'
            '    return subprocess.run(["bash", "scripts/check_all.sh"], cwd=root, capture_output=True)\n')
    assert bad_calls(text) == ["x.py:4"]
    text2 = ('import os, subprocess\n\ndef run(root):\n    e = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}\n'
             '    return subprocess.run(["bash", "scripts/check_all.sh"], env=e)\n')
    assert bad_calls(text2) == ["x.py:5"]


def test_box_env_は_CI_の印と入口の値を受け継がない(monkeypatch):
    for k in ("GITHUB_ACTIONS", "GITHUB_EVENT_NAME", "PR_BODY", "AF_PYTEST_TALLY", "AF_CHECK_UNCHECKED", "PYTEST_ADDOPTS"):
        monkeypatch.setenv(k, "作り物")
    e = box_env()
    assert not [k for k in e if k.startswith("GITHUB_") or k in ("PR_BODY", "AF_PYTEST_TALLY", "AF_CHECK_UNCHECKED",
                                                                 "PYTEST_ADDOPTS")]
    assert box_env(ci=True)["GITHUB_ACTIONS"] == "true"
