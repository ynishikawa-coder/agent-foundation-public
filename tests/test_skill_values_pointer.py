"""SKILL.md の「repo ごとの値」の節が、値の表の読み方を写さず 1 行で正本を指し、その指し先が生きているかを見る。

意図: 値の表の探し方・既定・知らない鍵の扱いを skill-values/skill_values.py の 1 か所で持ち、skill は指すだけにする。
課題: 12 の SKILL.md が同じ説明の段落を写し、毎回読まれる量を増やし、正本を直すと写しが古くなりうる。
原因: 指す先の決まりが無く、skill を足すたびに前の skill の段落を真似た。
入力の注入は作り物。
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
POINTER = re.compile(r"正本は土台の `([^`]+)` の冒頭（((?:「[^」]+」)+)）")
COPIED = ("黙って捨てない", "git rev-parse --show-toplevel")
SECTION = re.compile(r"^## repo ごとの値（config/skill-values.json）\n\n(.+)\n", re.M)


def dead(text, root=ROOT):
    """指し先の file が無い・見出しが無い物を返す。指しが無ければ「指しが無い」。"""
    m = POINTER.search(text)
    if not m:
        return ["指しが無い"]
    f = root / m.group(1)
    if not f.is_file():
        return ["file が無い: " + m.group(1)]
    body = f.read_text(encoding="utf-8")
    return ["見出しが無い: " + h for h in re.findall(r"「([^」]+)」", m.group(2))
            if not re.search(r"^%s[^\n]*:" % re.escape(h), body, re.M)]


def skills():
    for f in sorted((ROOT / "plugins").glob("*/skills/*/SKILL.md")):
        m = SECTION.search(f.read_text(encoding="utf-8"))
        if m and not m.group(1).startswith("|"):
            yield f, m.group(1)


def test_値の節は正本を指し写さない():
    seen = list(skills())
    assert len(seen) >= 12
    for f, para in seen:
        rel = f.relative_to(ROOT)
        assert not dead(para), (str(rel), dead(para))
        assert not any(w in para for w in COPIED), f"{rel}: 読み方の説明を写さず指す"


def test_注入_死んだ指しを拒む():
    ok = "正本は土台の `skill-values/skill_values.py` の冒頭（「探し方」「照らし」）。"
    assert not dead(ok)
    assert dead(ok.replace("skill_values.py", "gone.py")) == ["file が無い: skill-values/gone.py"]
    assert dead(ok.replace("「照らし」", "「消えた見出し」")) == ["見出しが無い: 消えた見出し"]
    assert dead("鍵は表から読む。") == ["指しが無い"]
