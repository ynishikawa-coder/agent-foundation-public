"""Python の file の名（関数・変数・引数・属性）に、CI の Python では名に使えない字が無いかを照らす。

意図: 手元で緑の試験が CI でも同じく読める事。
課題: 手元（Python 3.13・Unicode 15.1）は名の中の「・」を通すが、CI（.github/workflows/ci.yml の python-version）の
  3.12 は構文の誤りで試験の file ごと読めず、check と plugin-smoke が赤になった。
原因: 名に使える字の表が Python の版で違い（Unicode 15.1 で ID_Continue に 4 字が足された）、手元では誤りが見えない。
"""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Unicode 15.1 で ID_Continue に足された字（3.12 以前の Python は名に使えない）
新しい字 = {"‌", "‍", "・", "･"}
SKIP = {".git", ".claude", "node_modules", ".venv"}


def CI_の版():
    wf = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    vs = {tuple(map(int, v.split("."))) for v in re.findall(r'python-version:\s*"([\d.]+)"', wf)}
    assert vs, "ci.yml に python-version が無い"
    return min(vs)


def 名の外れ(src: str, where: str = "") -> list[str]:
    """src の名のうち、新しい字を含む物。構文で読めない時も外れ。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"{where}: 構文で読めない（{e.msg}・{e.lineno} 行）"]
    out = []
    for n in ast.walk(tree):
        for name in (getattr(n, a, None) for a in ("name", "id", "arg", "attr")):
            if isinstance(name, str) and 新しい字 & set(name):
                out.append(f"{where}:{getattr(n, 'lineno', '?')}: 名「{name}」に CI の Python が読めない字")
    return out


def _files():
    for p in ROOT.rglob("*.py"):
        if not SKIP & set(p.relative_to(ROOT).parts):
            yield p


def test_名に_CI_の_Python_が読めない字が無い():
    if CI_の版() >= (3, 13):
        return
    bad = [x for p in _files() for x in 名の外れ(p.read_text(encoding="utf-8"), p.relative_to(ROOT).as_posix())]
    assert bad == [], "\n".join(bad)


def test_注入_名に中黒を入れると赤_文字列の中なら緑():
    assert 名の外れ("def test_注記・囲い():\n    pass\n") != []
    assert 名の外れ("x = '注記・囲い'\n") == []
    assert 名の外れ("def test_注記や囲い(a・b=1):\n    pass\n") != []
