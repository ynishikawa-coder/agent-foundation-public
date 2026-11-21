"""部品が無くて飛ばす条件と理由が、同じ 1 か所（tests/needs.py）から出るか（注入の試験）。

原因の台帳 束 F1: 集める時に subprocess や import を走らせる skipif・例外の 1 行目を理由にする飛ばし・本体の中ほどの
飛ばしは、飛ばす理由が条件と結ばれない。ここでは needs の関数が条件どおりに飛ぶか・飛ばないかと、試験の file に
その形（集める時に走る skipif の条件・except の中で例外の文を理由に飛ばす）が戻らないかを照らす。
"""
import ast
from pathlib import Path

import needs
import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_node_が無ければ_node_の名で飛ぶ(monkeypatch):
    monkeypatch.setattr(needs.shutil, "which", lambda name: None)
    with pytest.raises(pytest.skip.Exception, match="node が無い"):
        needs.node()


def test_ブラウザは_file_の有る無しだけで飛び_在れば飛ばさない(tmp_path, monkeypatch):
    monkeypatch.delenv("QA_CHROMIUM", raising=False)

    class P:
        class chromium:
            executable_path = str(tmp_path / "無い")
    with pytest.raises(pytest.skip.Exception, match="ブラウザの file が無い"):
        needs.chromium(P)
    exe = tmp_path / "chrome"
    exe.write_text("", encoding="utf-8")
    P.chromium.executable_path = str(exe)
    assert needs.chromium(P) == str(exe)


def bad_skips(text, name="x.py"):
    tree = ast.parse(text)
    out = []
    for node in ast.walk(tree):
        # 集める時に走る skipif の条件（shutil.which の外の呼び出し）
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("mark.skipif") and node.args:
            calls = [c for c in ast.walk(node.args[0]) if isinstance(c, ast.Call)]
            if any(not ast.unparse(c.func).endswith("which") for c in calls):
                out.append(f"{name}:{node.lineno}: skipif の条件が集める時に走る")
        # except の中で例外の文を理由に飛ばす
        if isinstance(node, ast.ExceptHandler) and node.name:
            for c in ast.walk(node):
                if (isinstance(c, ast.Call) and ast.unparse(c.func).endswith("skip")
                        and any(isinstance(n, ast.Name) and n.id == node.name for a in c.args for n in ast.walk(a))):
                    out.append(f"{name}:{c.lineno}: 例外の文を理由に飛ばす")
    return out


def test_試験の_file_に条件と結ばれない飛ばしが無い():
    found = []
    for p in sorted((ROOT / "tests").rglob("*.py")):
        found += bad_skips(p.read_text(encoding="utf-8"), str(p.relative_to(ROOT)))
    assert found == [], found


def test_注入_集める時に走る_skipif_と例外の文の飛ばしを拾う():
    a = "import pytest\n\n" "@pytest.mark.skipif(not _probe(), reason='x')\ndef test_a():\n    pass\n"
    b = ("import pytest\n\ndef test_b():\n    try:\n        go()\n    except Exception as e:\n"
         "        pytest.skip(f'起こせない: {e}')\n")
    assert bad_skips(a) == ["x.py:3: skipif の条件が集める時に走る"]
    assert bad_skips(b) == ["x.py:7: 例外の文を理由に飛ばす"]
