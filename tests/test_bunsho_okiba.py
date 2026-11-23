"""直す人の決まり（CONTRIBUTING）と skill の文を、字の有無でなく置き場（節・欄・後へ回す行）で照らす。

意図: PR の冒頭の欄・変更の記録の置き場・spec-doc と big-picture の上下・後へ回す言葉の外の表が、決まった節・欄・行に在る事を守り、
  言い回しは縛らない。
課題: 試験が句を CONTRIBUTING・SKILL の全体から `in` で探し、外の表の鍵をどの行からでも拾っていたので、別の節や注記・
  別の行へ移しても緑だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名（型の file・冒頭の欄の鍵・記録の置き場・skill の名）も動く物から読まずに写していた。
"""
from pathlib import Path

from md_yomi import 地の行, 欄, 節, 置き場
from test_big_picture import SKILL as _BIGPIC_SKILL
from test_changelog import cl
from test_deferral_ledger import 後へ回す言葉, 後へ回す言葉の外, 台帳を指す

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ".github/pull_request_template.md"
PR_NODE = "1. 枝と PR"
SPEC = ROOT / "plugins" / "dev-flow" / "skills" / "spec-doc"
BIGPIC = _BIGPIC_SKILL   # 置き場は big-picture の試験が持つ


def _read(p):
    return Path(p).read_text(encoding="utf-8")


def 冒頭の鍵() -> str:
    """PR の型の 1 行目（`job: <…>`）の鍵。"""
    return _read(ROOT / TEMPLATE).splitlines()[0].split(":")[0].strip()


def 冒頭の欄の外れ(contributing: str, key: str) -> list[str]:
    """「枝と PR」の節の地の行に、PR の型を指し冒頭の欄が型の 1 行目の鍵の 1 行だけと書く行が在るか。"""
    body = 節(contributing, PR_NODE)
    if body is None:
        return [f"CONTRIBUTING に「{PR_NODE}」の節が 1 つでない"]
    ok = [l for l in 地の行(body) if f"`{TEMPLATE}`" in l and "冒頭" in l and f"{key} の 1 行" in l]
    return [] if ok else [f"「{PR_NODE}」の節に冒頭の欄が {key} の 1 行と書く行が無い"]


def 記録の置き場の外れ(contributing: str) -> list[str]:
    """変更の記録の置き場（`CHANGELOG.d/`）を指す行が、地の行の「配り方」の節に在るか。"""
    where = 置き場(contributing, cl.DIR_NAME + "/")
    return [] if any("配り方" in h for h in where) else [f"{cl.DIR_NAME}/ を指す行が配り方の節に無い: {where}"]


def 外の表の外れ(root: Path, table: dict) -> list[str]:
    """後へ回す言葉の外の表の行ごとに、鍵を持つ行が今も後へ回す言葉を使い台帳を指さない行か（外す訳の在る行か）。"""
    bad = []
    for rel, key in table:
        lines = [ln for ln in (root / rel).read_text(encoding="utf-8").splitlines() if key in ln]
        if not any(後へ回す言葉.search(ln) and not 台帳を指す(ln) for ln in lines):
            bad.append(f"外の表の行が後へ回す行を指さない: {rel}: {key}")
    return bad


def 上下の外れ(spec_doc: str, bigpic: str) -> list[str]:
    """spec-doc と big-picture の「上下」の欄が互いの skill の名を指し、spec-doc が全体の絵の下と書くか。"""
    bad = []
    s, b = 欄(spec_doc, "上下"), 欄(bigpic, "上下")
    if s is None:
        bad.append("spec-doc に「上下」の欄が 1 つでない")
    elif f"`{BIGPIC.name}`" not in s or "全体の絵の下" not in s:
        bad.append(f"spec-doc の「上下」の欄が {BIGPIC.name} の下と書かない")
    if b is None:
        bad.append("big-picture に「上下」の欄が 1 つでない")
    elif f"`{SPEC.name}`" not in b:
        bad.append(f"big-picture の「上下」の欄が {SPEC.name} を指さない")
    return bad


def test_注入_冒頭の欄の文を別の節_注記へ移すと赤_鍵を変えると赤_言い回しは緑():
    c, key = _read(ROOT / "CONTRIBUTING.md"), 冒頭の鍵()
    assert key == "job" and 冒頭の欄の外れ(c, key) == []
    line = next(l for l in 節(c, PR_NODE).splitlines() if "冒頭" in l and TEMPLATE in l)
    moved = c.replace(line + "\n", "", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n\n" + line + "\n", 1)
    assert "冒頭の欄は job の 1 行" in moved and 冒頭の欄の外れ(moved, key)
    assert 冒頭の欄の外れ(c.replace(line, f"<!-- {line} -->", 1), key)
    # 型の鍵が変われば文書が古いので赤
    assert 冒頭の欄の外れ(c, "task")
    assert 冒頭の欄の外れ(c.replace("冒頭の欄は job の 1 行", "冒頭の欄は job の 1 行だけ", 1), key) == []


def test_注入_記録の置き場を別の節_注記へ移すと赤_言い回しは緑():
    c = _read(ROOT / "CONTRIBUTING.md")
    assert 記録の置き場の外れ(c) == []
    line = next(l for l in 節(c, "8. 配り方と「壊れる:」変更").splitlines() if cl.DIR_NAME + "/" in l)
    moved = c.replace(line, "- 記録は決まりの file に足す。", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n\n" + line + "\n", 1)
    assert cl.DIR_NAME + "/" in moved and 記録の置き場の外れ(moved)
    assert 記録の置き場の外れ(c.replace(line, f"<!-- {line} -->", 1))
    assert 記録の置き場の外れ(c.replace(line, line.replace("PR ごとに", "PR 1 本ごとに"), 1)) == []


def test_注入_外の表の鍵を別の行へ移すと赤_言い回しは緑(tmp_path):
    assert 外の表の外れ(ROOT, 後へ回す言葉の外) == []
    rel = "plugins/x/skills/y/SKILL.md"
    (tmp_path / rel).parent.mkdir(parents=True)
    table = {(rel, "鍵の語"): "作り物"}
    # 鍵を後へ回す行に置く＝緑。言い回しを変えても後へ回す言葉が残れば緑
    for text in ("- 鍵の語は後で拾う。\n", "- 鍵の語は後回しにする。\n"):
        (tmp_path / rel).write_text("# 作り物\n" + text, encoding="utf-8")
        assert 外の表の外れ(tmp_path, table) == []
    # 鍵を別の表の行（後へ回さない行）へ移す＝全体には字が残るが赤
    (tmp_path / rel).write_text("# 作り物\n- 後で拾う。\n\n| 鍵の語 | 別の表 |\n", encoding="utf-8")
    assert 外の表の外れ(tmp_path, table)
    # 台帳を指す行になった（外す訳が無くなった）時も赤
    (tmp_path / rel).write_text("# 作り物\n- 鍵の語は後で原因の台帳の行にする。\n", encoding="utf-8")
    assert 外の表の外れ(tmp_path, table)


def test_注入_上下の欄の名を注記_別の欄へ移すと赤_言い回しは緑():
    s, b = _read(SPEC / "SKILL.md"), _read(BIGPIC / "SKILL.md")
    assert 上下の外れ(s, b) == []
    field = 欄(s, "上下")
    # 欄の中の big-picture を消し、同じ字を注記に置く（全体＝説明の行にも字が残る）
    hidden = s.replace(field, field.replace(f"`{BIGPIC.name}`", "絵の skill"), 1) + f"\n<!-- `{BIGPIC.name}` -->\n"
    assert BIGPIC.name in hidden and any(BIGPIC.name in x for x in 上下の外れ(hidden, b))
    # 「全体の絵の下」を欄から別の節へ
    moved = s.replace(field, field.replace("全体の絵の下", "絵の下"), 1)
    assert "全体の絵の下" in moved and 上下の外れ(moved, b)
    # big-picture の欄から spec-doc を消し、別の節に置く
    bf = 欄(b, "上下")
    assert any(SPEC.name in x for x in 上下の外れ(s, b.replace(bf, bf.replace(f"`{SPEC.name}`", "設計書の skill"), 1) + f"\n## 外\n`{SPEC.name}`\n"))
    # 言い回しを変えても名と上下が欄に在れば緑
    assert 上下の外れ(s.replace(field, field.replace("仕組みの姿の正は", "仕組みの姿の正本は"), 1), b) == []
