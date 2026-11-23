"""道具が出す文を写して照らしていた試験（根治の入口の指し・窓の種類の案内・外へ渡す道具の鍵の止め）を、道具の定数と
正本から読んで照らす。

意図: 道具が赤の最後の行で根治の入口を正しく指す事・窓の種類の案内が決まった印だけを挙げる事・外へ渡す入力の鍵で
  止めた事を守り、道具の文の言い回しは縛らない。
課題: 試験が道具の出す文（「細目 §3「まず構造を疑う」」「オーナーと話す窓なら 🙋」「鍵・認証情報の形」など）を写して
  `in` で照らしていたので、細目の節の番号や欄の名を変えると道具は正しく直しても試験の写しが古いまま赤になり、
  道具が古い番号を指したままでも写しと揃っていれば緑だった。
原因: 試験が名と文を、動く物（道具の定数・細目の欄・道具の関数）から読まず写していた。

読み口:
- 入口の名() / 入口の節() / 根治の入口を指す(line): 根治の入口の名は scripts/measure_load.py の COPY_MARK（写しを数える
  道具が持つ名）、節の番号はその名が太字の欄として在る細目の file の番号から読む。
- 種類の案内(text) / 案内の印(text): session_watch の REMIND の型の「種類:」に差した部分と、そこに挙がる種類の印。
- 鍵で止めた文(payload) / 鍵で止めた文の頭(payload): plugins/guard/scripts/outbound.py の check_secret が同じ入力に返す
  止めの文と、その 1 行目。
"""
import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from md_yomi import 欄

ROOT = Path(__file__).resolve().parent.parent
SAIMOKU = ROOT / "plugins" / "core" / "細目"
GUARD_SCRIPTS = ROOT / "plugins" / "guard" / "scripts"
SW_PATH = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = _load("af_measure_load_for_okiba", ROOT / "scripts" / "measure_load.py")
SW = _load("af_session_watch_for_okiba", SW_PATH)


# ── 根治の入口（細目「直すは根治」の「まず構造を疑う」の欄）──
def 入口の節(name=None, saimoku=SAIMOKU) -> int | None:
    """name が太字の欄として在る細目の file の番号（file 名の頭の数）。無い・2 つの file に在る時は None。"""
    name = name or ML.COPY_MARK
    hits = [p for p in sorted(saimoku.glob("*.md")) if 欄(p.read_text(encoding="utf-8"), name) is not None]
    if len(hits) != 1:
        return None
    m = re.match(r"(\d+)-", hits[0].name)
    return int(m.group(1)) if m else None


def 入口の名() -> str:
    """根治の入口の名（写しを数える道具の定数）。細目のどこかに太字の欄として在る事を確かめてから返す。"""
    name = ML.COPY_MARK
    assert 入口の節(name) is not None, "根治の入口の名 %r が細目の欄に 1 つだけ在る形でない" % name
    return name


def 根治の入口を指す(line: str, name=None, num=None) -> bool:
    """line が「細目 §<入口の節>「<入口の名>」」か「細目「<入口の名>」」（節を名で指す形）で根治の入口を指すか。
    番号の違う指し・細目と言わない名だけの指しは外れ。"""
    name = name or 入口の名()
    num = 入口の節(name) if num is None else num
    hits = list(re.finditer(r"細目(?:\s*§\s*(\d+))?\s*「%s」" % re.escape(name), line))
    return bool(hits) and all(m.group(1) is None or int(m.group(1)) == num for m in hits)


def _py_定数(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.endswith("ROOT_CAUSE"):
                    out.append(("%s:%s" % (path.relative_to(ROOT), t.id), node.value.value))
    return out


_MJS = re.compile(r'^const (\w*ROOT_CAUSE) = "((?:[^"\\]|\\.)*)";', re.M)


def 道具の入口の定数() -> list[tuple[str, str]]:
    """repo の道具（plugins・scripts・public-guard）が持つ *ROOT_CAUSE の定数（場所, 文）の一覧。"""
    out = []
    for base in ("plugins", "scripts", "public-guard"):
        for p in sorted((ROOT / base).rglob("*.py")):
            if "ROOT_CAUSE" in p.read_text(encoding="utf-8"):
                out += _py_定数(p)
        for p in sorted((ROOT / base).rglob("*.mjs")):
            out += [("%s:%s" % (p.relative_to(ROOT), m.group(1)), m.group(2)) for m in _MJS.finditer(p.read_text(encoding="utf-8"))]
    return out


def test_根治の入口の名は細目の欄に在り_節の番号が読める():
    assert isinstance(入口の節(), int)


def test_道具の根治の入口の定数は全部_今の細目の節と名を指す():
    found = 道具の入口の定数()
    assert len(found) >= 10, found       # 読み口が空振りして緑にならない
    bad = [where for where, text in found if 入口の名() in text and not 根治の入口を指す(text)]
    assert bad == [], bad


# 注入: 指しを外す・番号を違える・名を変える → 外れ。指しの前後の言い回しを変える → 当たる。
@pytest.mark.parametrize("line,ok", [
    ("直し: 意図とのずれから入り、細目 §3「まず構造を疑う」で原因を探す。", True),
    ("直し: 原因から直す。細目 §3「まず構造を疑う」。", True),
    ("直し: 意図とのずれから入り、原因を探す。", False),
    ("直し: 細目 §4「まず構造を疑う」で原因を探す。", False),
    ("直し: 細目 §3「構造を疑う」で原因を探す。", False),
    ("直し: まず構造を疑う。", False),
    ("直し: 原因は細目「まず構造を疑う」で探す。", True),
])
def test_注入_根治の入口の指し(line, ok):
    assert 根治の入口を指す(line, name="まず構造を疑う", num=3) is ok


def test_注入_欄を別の細目へ移すと節の番号が付いてくる_消すと読めない(tmp_path):
    for p in SAIMOKU.glob("*.md"):
        (tmp_path / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    num = 入口の節(saimoku=tmp_path)
    src = next(p for p in tmp_path.glob("*.md") if p.name.startswith("%02d-" % num))
    field = "- **%s** — 作り物の欄。\n" % ML.COPY_MARK
    text = src.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines(keepends=True) if l.startswith("- **%s**" % ML.COPY_MARK))
    src.write_text(text.replace(line, ""), encoding="utf-8")
    assert 入口の節(saimoku=tmp_path) is None
    other = next(p for p in sorted(tmp_path.glob("*.md")) if not p.name.startswith("%02d-" % num))
    other.write_text(other.read_text(encoding="utf-8") + "\n" + field, encoding="utf-8")
    assert 入口の節(saimoku=tmp_path) == int(other.name.split("-")[0])


# ── 窓の種類の案内（session_watch の REMIND の「種類:」の部分）──
def 種類の案内(text: str) -> str | None:
    """text の中の REMIND の型に差した「種類」の部分。型が見つからなければ None。"""
    pre, post = (SW.REMIND % (SW.HUMAN, SW.HAND, SW.AI, SW.REMOTE_PREFIX.rstrip("_"), "\0")).split("\0")
    i = text.find(pre)
    if i < 0:
        return None
    j = text.find(post, i + len(pre))
    return text[i + len(pre):j] if j >= 0 else None


def 案内の印(text: str) -> list[str] | None:
    which = 種類の案内(text)
    return None if which is None else [k for k in SW.KINDS if k in which]


def test_注入_種類の案内の印():
    tail = SW.REMIND % (SW.HUMAN, SW.HAND, SW.AI, SW.REMOTE_PREFIX.rstrip("_"), "%s")
    assert 案内の印(tail % ("作り物の言い回し %s" % SW.HUMAN)) == [SW.HUMAN]
    assert 案内の印(tail % "・".join(SW.KINDS)) == list(SW.KINDS)
    assert 案内の印(tail % "印なし") == []
    assert 案内の印("[session-watch] 型の外の作り物の文 %s" % SW.HUMAN) is None


# ── 外へ渡す道具の鍵の止め（outbound.check_secret の文）──
def 鍵で止めた文(payload: dict) -> str:
    """outbound.check_secret が payload に返す止めの文（止めなければ空）。"""
    sys.path.insert(0, str(GUARD_SCRIPTS))           # outbound は呼ばれた時にも同じ dir の部品を読む
    try:
        return _load("af_outbound_for_okiba", GUARD_SCRIPTS / "outbound.py").check_secret(payload, {})
    finally:
        sys.path.remove(str(GUARD_SCRIPTS))


def 鍵で止めた文の頭(payload: dict) -> str:
    """鍵で止めた文の 1 行目（止めなければ空）。どこに何の形が在ったかの行は入力で変わるので、頭だけで照らす時に使う。"""
    text = 鍵で止めた文(payload)
    return text.splitlines()[0] if text else ""


def test_注入_鍵で止めた文の頭():
    key = "gh" + "p_" + "A1b2" * 10
    send = {"tool_name": "mcp__x__send_message", "tool_input": {"message": "作り物 %s" % key}}
    head = 鍵で止めた文の頭(send)
    assert head and key not in head
    assert 鍵で止めた文(send).startswith(head) and "\n- " in 鍵で止めた文(send)     # 何の形が在ったかの行が続く
    assert 鍵で止めた文の頭(dict(send, tool_input={"message": "作り物"})) == ""
    assert 鍵で止めた文の頭(dict(send, tool_name="Bash")) == ""
