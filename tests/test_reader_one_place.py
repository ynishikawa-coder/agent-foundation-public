"""構造の読み方（コードの囲み・注記・注釈）は core の kaku.py の「使う形の読み口」の 1 か所だけが持つ。

防ぐ故障: 照らす道具や試験が囲み・注記・注釈を自分で読むと、所ごとに読み方がずれ、ある所では命令を説明の文に読んで
見落とす。前の試験は名を挙げた 5 か所の字の在る無しだけを見ていて、6 か所目や字を変えた写しを見つけなかった。
見る所: core の plugin・tests・scripts の .py 全部（kaku.py を除く）を構文で読み、
- tokenize を import する（注釈を自分で読む）
- 字の値の正規表現が、囲み・注記・注釈の印（``` ~~~ <!-- // /* と行頭の > の引用）を印ごと拾い、地の文や `…` の 1 語は拾わない
- startswith／endswith にその印を渡す（assert の中の照らしは読み方でないので外す）
を写しとして名指す。guard などの別の plugin は plugin を跨いで import しない作りのため対象の外（kaku の節の頭に書いた）。
注入の試験: 作り物の源に写しを入れると名指す・字を変えた写しも名指す。
"""
import ast
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("kaku_one_place", ROOT / "plugins/core/scripts/kaku.py")
kaku = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kaku)

# 印ごとに、その印を拾う読み方なら当たる例と、読み方でない正規表現も当たる例（地の文・`…` の 1 語）。
PROBES = {"```": "```bash", "~~~": "~~~md", "<!--": "<!-- 注 -->", "//": "x // 注", "/*": "x /* 注 */", ">": "> 引用"}
PLAIN = "前の文。`ab` と c/d と a > b"
MARKS = set(PROBES)
RE_FUNCS = {"compile", "search", "match", "fullmatch", "sub", "subn", "findall", "finditer", "split"}


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def readers(src: str) -> list[str]:
    """源の中で構造を自分で読む所（行・形）。"""
    tree = ast.parse(src)
    in_assert = {id(x) for a in ast.walk(tree) if isinstance(a, ast.Assert) for x in ast.walk(a)}
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in n.names] + ([n.module] if isinstance(n, ast.ImportFrom) and n.module else [])
            if "tokenize" in names:
                out.append(f"{n.lineno}: tokenize")
        if not isinstance(n, ast.Call) or id(n) in in_assert:
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        arg = _const_str(n.args[0]) if n.args else None
        if arg is None:
            continue
        if name in RE_FUNCS and getattr(getattr(f, "value", None), "id", "") == "re":
            try:
                rx = re.compile(arg, re.M | re.S)
            except re.error:
                continue
            if rx.search(PLAIN):
                continue
            got = [k for k, p in PROBES.items() if (m := rx.search(p)) and k in m.group(0)]
            if got:
                out.append(f"{n.lineno}: re {arg[:40]!r} が {got} を拾う")
        if name in ("startswith", "endswith") and arg in MARKS:
            out.append(f"{n.lineno}: {name}({arg!r})")
    return out


def _targets():
    files = list((ROOT / "plugins/core").rglob("*.py")) + list((ROOT / "tests").glob("*.py")) \
        + list((ROOT / "scripts").rglob("*.py"))
    return sorted(p for p in files if p.name != "kaku.py" and "__pycache__" not in p.parts)


def test_core_と試験と_scripts_は構造の読み方を写さない():
    bad = {}
    for p in _targets():
        found = readers(p.read_text(encoding="utf-8"))
        if found:
            bad[str(p.relative_to(ROOT))] = found
    assert not bad, f"構造の読み方を自分で書いている（kaku の読み口を呼ぶ）: {bad}"


def test_照らす相手が空でない():
    assert len(_targets()) >= 50


# ---- 注入の試験 ----
import pytest  # noqa: E402


@pytest.mark.parametrize("src", [
    'import tokenize\n',
    'from tokenize import COMMENT\n',
    'import re\nFENCE = re.compile(r"^```")\n',
    'import re\nFENCE = re.compile(r"^`{3,}")\n',                 # 字を変えた写し
    'import re\nNOTE = re.compile(r"<!--.*?-->", re.S)\n',
    'import re\nx = re.sub(r"<!-{2}[\\s\\S]*?-{2}>", "", t)\n',     # 字を変えた写し
    'def f(ln):\n    return ln.startswith("~~~")\n',
    'import re\nC = re.compile(r"//[^\\n]*")\n',
    'import re\nQ = re.compile(r"^[ \\t]{0,3}>")\n',
    'def f(ln):\n    return ln.lstrip().startswith(">")\n',
])
def test_注入_写しを入れると名指す(src):
    assert readers(src), src


@pytest.mark.parametrize("src", [
    'import re\nP = re.compile(r"`[\\x20-\\x7e]*`")\n',            # `…` の 1 語（地の文の語）を拾う
    'import re\nS = re.compile(r"[\\s`*]+")\n',
    'def t(x):\n    assert x.startswith("```")\n',                 # 照らしの assert は読み方でない
])
def test_読み方でない物は名指さない(src):
    assert not readers(src), src


# ── common.rules の指し（test_skill_values_no_rule_copy.pointing）は禁じる語で説明と指示を分けない ──
def test_指し_禁じる語を添えて名を挙げても赤():
    from test_skill_values_no_rule_copy import RULE_BUCKET, pointing
    for line in ("`common.rules` は写さない。", "前の `common.rules.no_confirm` は畳んだ。"):
        assert RULE_BUCKET.search(pointing(".md", line)), line
    assert not RULE_BUCKET.search(pointing(".md", "<!-- common.rules -->")), "注記は指しでない"


# ── js_code は /…/ の正規表現の中の引用符・// を字の値や注釈と読まない ──
@pytest.mark.parametrize("src,keep", [
    ('const r = /"/; run("x"); // 注\n', 'run("x")'),
    ("const r = /[/']/g; go(); // 注\n", "go()"),
    ("if (/'/.test(s)) go(); // 注\n", "go()"),
    ("return /`/.test(s) || go() // 注\n", "go()"),
])
def test_js_正規表現の中の引用符で後の命令を注釈にしない(src, keep):
    got = kaku.js_code(src)
    assert keep in got and "注" not in got, got


def test_js_割り算の_slash_は正規表現でない():
    got = kaku.js_code("a = b / c; // 注\nd = e / 2 // 注2\n")
    assert "注" not in got and "b / c" in got and "e / 2" in got
