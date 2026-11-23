"""道具と試験の頭の説明は 意図・課題・原因 の 3 欄で書く。

意図: 道具（script・hook）と試験の頭を読む人が、何のために在るか・何がずれたか・何が悪かったかを分けて読めるようにする
（根治の 5 段＝細目「直すは根治」）。
課題: 頭の説明が 1 つの欄に起きた事・原因・意図を混ぜて書き、本来の意図が読み取れない file が約 27 に広がっていた。
原因: 頭の説明の形に決まりが無く、前例の 1 欄の形が真似で広がった。
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = "なぜ" + "在るか:"  # この file 自身が拾われないよう字を分ける
HEAD_LINES = 40
欄 = re.compile(r"^\s*(?:#\s*|//\s*)?(意図|課題|原因):", re.M)


def 頭の形の誤り(text):
    """頭の説明の形の誤りを返す（空なら合格）。"""
    errs = []
    if OLD in text:
        errs.append(f"「{OLD}」の 1 欄が在る（意図・課題・原因の 3 欄に分ける）")
    head = "\n".join(text.split("\n")[:HEAD_LINES])
    names = [m.group(1) for m in 欄.finditer(head)]
    if ("課題" in names or "原因" in names) and ("意図" not in names or names.index("意図") > min(
            names.index(n) for n in ("課題", "原因") if n in names)):
        errs.append("頭に 課題: か 原因: が在るのに、その前に 意図: が無い")
    return errs


def _tools():
    out = subprocess.run(["git", "ls-files", "plugins", "scripts", "public-guard", "tests"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split()
    return [r for r in out if r.endswith((".py", ".sh", ".mjs", ".js"))]


def test_道具と試験の頭は意図から書き_なぜ在るかの1欄が無い():
    bad = {r: e for r in _tools() if (e := 頭の形の誤り((ROOT / r).read_text(encoding="utf-8", errors="ignore")))}
    assert not bad, bad


def test_注入_なぜ在るかの1欄と意図の抜けを拒む():
    good = '"""x\n\n意図: 守る物。\n課題: ずれ。\n原因: 仕組み。\n"""\n'
    assert 頭の形の誤り(good) == []
    assert 頭の形の誤り(good.replace("意図: 守る物。\n", "")), "意図の抜けを通した"
    assert 頭の形の誤り('"""x\n\n' + OLD + ' 起きた事と原因。\n"""\n'), "1 欄の形を通した"
    assert 頭の形の誤り(good.replace("意図: 守る物。\n課題: ずれ。\n", "課題: ずれ。\n意図: 守る物。\n")), "意図が後の形を通した"
