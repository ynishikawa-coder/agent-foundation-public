"""入れて起動する試験の照らし core_problems に、核の部の頭だけを比べる弱い道が戻らないか（注入の試験）。

前の形: expected（正本の差し込む口が同じ材料で出した文脈の全体）を省けると、核の部の頭だけを比べ、節の切れ目の後ろに
足された節を見逃す比べに黙って戻った。今の形: expected は必須で、比べ方は文脈の全体を一字違わず比べる 1 本だけ。
"""
import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import plugin_smoke as S  # noqa: E402


def _real_inject(tmp_path):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp_path))
    p = subprocess.run([sys.executable, str(ROOT / "plugins/core/scripts/kaku.py"), "inject"], input="{}",
                       capture_output=True, text=True, env=env, timeout=60)
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def test_核の部の頭だけを比べる弱い道は無い_expected_を渡さない呼びは落ちる(tmp_path):
    """注入: expected を渡さずに呼ぶと（前の形では核の部の頭だけを比べ、節の切れ目の後ろに足した節を通した）呼べない。"""
    want = S.expected(ROOT)
    ctx = _real_inject(tmp_path)
    assert inspect.signature(S.core_problems).parameters["expected"].default is inspect.Parameter.empty
    call = S.core_problems  # 下の「repo のどこにも無い」の照らしに数えない別名で、呼べない事そのものを見る
    with pytest.raises(TypeError):
        call([ctx], want)
    added = ctx + "\n## 次の節\n本文"
    assert S.core_problems([added], want, ctx) != []  # 前の弱い道は「節の切れ目の後ろは見ない」で緑にしていた


def _calls_without_expected(src: str) -> list[int]:
    """src の中の core_problems の呼びのうち、expected（3 つ目の引数か名の付いた引数）を渡さない物の行。"""
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) == "core_problems":
            if len(node.args) < 3 and not any(k.arg == "expected" for k in node.keywords):
                bad.append(node.lineno)
    return bad


def test_expected_を渡さない_core_problems_の呼びは_repo_のどこにも無い():
    files = [ROOT / "scripts" / "plugin_smoke.py", *sorted((ROOT / "tests").glob("*.py"))]
    found = {str(f.relative_to(ROOT)): b for f in files if (b := _calls_without_expected(f.read_text(encoding="utf-8")))}
    assert found == {}


def test_注入_expected_を渡さない呼びを入れると拾う():
    src = (ROOT / "scripts" / "plugin_smoke.py").read_text(encoding="utf-8")
    assert _calls_without_expected(src) == []
    assert _calls_without_expected(src.replace("core_problems(ctx, want, expect)", "core_problems(ctx, want)")) != []
    # 弱い道の既定値を戻すと、署名の照らし（expected に既定値が無い）が赤になる
    weak = src.replace("expected: str) -> list[str]:", "expected: str | None = None) -> list[str]:")
    assert _expected_has_default(src) is False and _expected_has_default(weak) is True


def _expected_has_default(src: str) -> bool:
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "core_problems")
    names = [a.arg for a in fn.args.args]
    return names.index("expected") >= len(names) - len(fn.args.defaults)
