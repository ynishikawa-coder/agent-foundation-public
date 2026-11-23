"""GitHub の手の決まりを、字の有無でなく置き場（細目の「手の窓」の欄・CONTRIBUTING の「main の守りの設定」の節）と、
名の正本（workflow・scripts/ruleset_apply.py）から読んだ値で照らす。

意図: 決まりが決めた欄・節に在り、名（environment・鍵・正本の file）が動く物と揃う事を守り、言い回しは縛らない。
課題: 試験が文を丸ごと細目・CONTRIBUTING の全体から `in` で探していたので、別の節や注記・コードの囲いへ移しても緑、
  言い回しを少し直すと赤だった。
原因: 試験が構造を読む口（tests/md_yomi.py）を使わず、名も動く物から読まずに写していた。
"""
import importlib.util
import pathlib
import re

from md_yomi import 欄, 節
from saimoku import 全文 as 細目の全文

ROOT = pathlib.Path(__file__).resolve().parents[1]
NODE = "main の守りの設定"


def _apply():
    spec = importlib.util.spec_from_file_location("ruleset_apply_okiba", ROOT / "scripts/ruleset_apply.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def 守りの名():
    """動く物から読む名: 正本の file・environment の名・鍵の名（workflow が secrets から読む名）。"""
    m = _apply()
    wf = (ROOT / ".github/workflows/rulesets.yml").read_text(encoding="utf-8")
    keys = re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", wf)
    assert len(keys) == 1, keys
    return {"正本": m.RULESET.relative_to(ROOT).as_posix(), "env": m.ENV, "鍵": keys[0], "wf": wf}


def 手の窓の外れ(saimoku: str) -> list[str]:
    """細目の「手の窓」の欄が、自分で打つ・付いていない repo は add_repo で付ける・拒まれた時だけ人へ・人にしか打てない手だけ
    ✋ の窓、を持つか。欄が無い・2 つ在る（注記や囲いの中の物は数えない）時も外れ。"""
    body = 欄(saimoku, "手の窓")
    if body is None:
        return ["細目に「手の窓」の欄が 1 つでない"]
    need = ["自分で打つ", "`add_repo`", "拒", "人にしか打てない手", "✋"]
    return [f"「手の窓」の欄に無い: {w}" for w in need if w not in body]


def 守りの設定の外れ(contributing: str, names: dict) -> list[str]:
    """CONTRIBUTING の「main の守りの設定」の節が、動く物の名（正本の file・鍵・environment）と main だけの枝の制限を持つか。"""
    body = 節(contributing, NODE)
    if body is None:
        return [f"CONTRIBUTING に「{NODE}」の節が 1 つでない"]
    need = [f"`{names['正本']}`", f"`{names['鍵']}`", f"environment `{names['env']}`", "`main` だけ", "PR"]
    return [f"「{NODE}」の節に無い: {w}" for w in need if w not in body]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_注入_手の窓の欄の字を注記へ_別の欄へ移すと赤_言い回しを変えても緑():
    t = 細目の全文()
    assert 手の窓の外れ(t) == []
    body = 欄(t, "手の窓")
    # 欄の中の add_repo を消し、同じ字を注記の中に置く（全文には字が残る）
    commented = t.replace("`add_repo`", "それ", 1) + "\n<!-- - **手の窓** — `add_repo` -->\n"
    assert "`add_repo`" in commented and any("add_repo" in x for x in 手の窓の外れ(commented))
    # 「人にしか打てない手」を別の欄の行へ移す
    moved = t.replace("人にしか打てない手", "人の手", 1).replace("- **秘密**", "- **秘密** — 人にしか打てない手。", 1)
    assert any("人にしか打てない手" in x for x in 手の窓の外れ(moved))
    # 欄そのものをコードの囲いへ入れると、欄が無い
    first = next(l for l in t.splitlines() if l.startswith("- **手の窓**"))
    fenced = t.replace(first, "```\n" + first + "\n```", 1)
    assert 手の窓の外れ(fenced) == ["細目に「手の窓」の欄が 1 つでない"]
    # 言い回しを変えても形（欄と要の語）が在れば緑
    reworded = t.replace(body, body.replace("拒まれた時だけ", "拒まれた場合に限り"), 1)
    assert 手の窓の外れ(reworded) == []


def test_注入_守りの設定を別の節_注記_囲いへ移すと赤_名を変えると赤():
    c, n = _read("CONTRIBUTING.md"), 守りの名()
    assert 守りの設定の外れ(c, n) == []
    body = 節(c, NODE)
    # 節の本文を「## 4. 置かない物」の下へ移す（全文に字は残る）
    moved = c.replace(body, "\n", 1).replace("## 4. 置かない物\n", "## 4. 置かない物\n" + body + "\n", 1)
    assert n["鍵"] in moved and len(守りの設定の外れ(moved, n)) >= 3
    # 鍵の名を注記へ・囲いへ
    for wrap in (lambda s: f"<!-- {s} -->", lambda s: f"\n```\n{s}\n```\n"):
        para = next(l for l in body.splitlines() if n["鍵"] in l)
        hidden = c.replace(para, wrap(para), 1)
        assert any(n["鍵"] in x for x in 守りの設定の外れ(hidden, n))
    # 動く物の名が変わったら（workflow の鍵を変えた）文書が古いので赤
    assert any("OTHER_TOKEN" in x for x in 守りの設定の外れ(c, {**n, "鍵": "OTHER_TOKEN"}))
    # 言い回しを変えても名と枝の制限が節に在れば緑
    assert 守りの設定の外れ(c.replace("直す時は AI がこの file を", "AI がこの file を", 1), n) == []
