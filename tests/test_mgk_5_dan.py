"""根治は意図→課題→原因→解決→未来の 5 段（呼び名 MGK）。

意図: 根治で本来の意図を独り立ちした段にし、意図そのものも疑い、課題は意図とのずれだけを書いて「なぜ」を原因へ送る
（オーナー決定 2026-11-22）。段の名と順は核 §3 を正本に、細目 §3 の箇条の形で照らす（言い回しは照らさない）。
課題: 4 段（問題→原因→解決→未来）では、本来の意図が「問題」の付け足しに埋もれて意図そのものを疑う段が無く、
原因が問題の段に紛れ込んだ。
原因: 「問題」の語が評価を含み、意図・起きた事・原因を 1 つの段に混ぜる形だった。
"""
import pathlib
import re

from md_yomi import 太字の欄, 箇条の子
from saimoku import 全文 as 細目の全文

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"


def _節(text, n):
    a = text.index(f"## {n}. ")
    b = text.find("\n## ", a + 1)
    return text[a:] if b < 0 else text[a:b]


def 核の段(kaku3):
    """核 §3 の「根治＝a→b→…」の段の名を順に返す（段の名と順の正本）。"""
    m = re.search(r"根治＝([^。（]+?→[^。（]+)", kaku3)
    return m.group(1).split("→") if m else []


# 段どうしの受け渡し: 課題は「なぜ」を原因へ送る／未来は意図が果たされ課題が起きない姿で、言えない時は解決へ戻る
段の受け渡し = {"課題": ["原因"], "未来": ["意図", "課題", "解決"]}
# 段の要（その段の箇条の中に在る事を照らす。別の段へ移すと赤）: 意図そのものを疑う／渡された 1 件の症状で幅を決めない
段の要 = {"意図": ["意図そのもの", "疑う"], "課題": ["症状", "幅"]}


def 段の外れ(saimoku3, kaku3):
    """細目 §3「根治の 5 段」の子の箇条が、核の段をこの順で持つかを照らし、外れを返す（空なら合う）。
    核に無い子は「同じ原因の他の問題」だけで、原因のすぐ後に置く（原因の段の中で別の目が探す物）。
    段どうしの受け渡し（課題の「なぜ」を原因へ送る・未来は意図が果たされた姿）は、本文が段の名を指すかで照らす。"""
    dan = 核の段(kaku3)
    kids = 箇条の子(saimoku3, "根治の 5 段")
    if not dan or kids is None:
        return ["核の段か細目の根治の 5 段の箇条が見つからない"]
    names = [k for k, _ in kids]
    body = dict(kids)
    bad = []
    if [n for n in names if n in dan] != dan:
        bad.append(f"段の順が核と違う: {names} ／ 核: {dan}")
    extra = [n for n in names if n not in dan]
    if extra != ["同じ原因の他の問題"] or "原因" not in names or names.index(extra[0]) != names.index("原因") + 1:
        bad.append(f"核に無い子は「同じ原因の他の問題」1 つだけを原因のすぐ後に置く: {names}")
    for step, refs in 段の受け渡し.items():
        if step in body:
            bad += [f"{step} の段が {r} の段を指さない" for r in refs if r not in body[step]]
    for step, words in 段の要.items():
        if step in body:
            bad += [f"{step} の段に要が無い: {w}" for w in words if w not in body[step]]
    if any(not v.strip() for v in body.values()):
        bad.append("本文の無い段が在る")
    return bad


def _3節():
    return _節(細目の全文(), 3), _節((CORE / "核.md").read_text(encoding="utf-8"), 3)


def test_細目の根治の段は核の段をこの順で持ち_課題はなぜを原因へ送る():
    assert 段の外れ(*_3節()) == []


def test_核の根治は意図から始まる_5_段():
    # 段の名と順はオーナーの決定（2026-11-22）なのでここに名で持つ。文の言い回しは照らさない
    assert 核の段(_3節()[1]) == ["意図", "課題", "原因", "解決", "未来"]


def MGK_の外れ(furumai, saimoku3):
    """振る舞いの既定に MGK の欄が 1 つだけ在り、その中身が細目 §3 に在る段の箇条の名（「根治の 5 段」）を指し、
    説明の頼みにも使うと書くか。細目の段の箇条はその名を MGK と呼ぶか。"""
    fields = [b for n, b in 太字の欄(furumai) if n == "MGK"]
    head = next((l for l in saimoku3.splitlines() if l.startswith("- **根治の 5 段**")), "")
    bad = [] if len(fields) == 1 else [f"振る舞いの既定の MGK の欄が 1 つでない: {len(fields)}"]
    if fields and "根治の 5 段" not in fields[0]:
        bad.append("MGK の欄が細目の根治の 5 段を指さない")
    if fields and "説明" not in fields[0]:
        bad.append("MGK の欄が説明の頼みにも 5 段で答えると書かない")
    if 箇条の子(saimoku3, "根治の 5 段") is None or "MGK" not in head:
        bad.append("細目 §3 の根治の 5 段の箇条が MGK と呼ばない")
    if "振る舞いの既定" not in head:
        bad.append("細目 §3 の根治の 5 段の箇条が、言われた時の答え方の在り処（振る舞いの既定）を指さない")
    return bad


def test_MGK_して_と言われたら_5_段の見出しで答える():
    assert MGK_の外れ((CORE / "振る舞い.md").read_text(encoding="utf-8"), _3節()[0]) == []


def test_古い_4_段と呼び名_MGkm_が決まりと道具に残らない():
    # 古い 4 段の名に加え、意図を持たず起きた事と原因を 1 欄に混ぜる型の字形（tests/test_kata_no_ran.py が形ごと照らす）
    olds = ["問題→原因→解決→未来", "MGkm", "根治の 4 段", "## 1. 問題", "未達は何が・なぜ", "どんな困りごとを",
            "なぜ在る" + "か:", "で原因から直す"]
    hits = []
    for p in list((ROOT / "plugins").rglob("*")) + [ROOT / ".github" / "pull_request_template.md"]:
        if p.is_file() and p.suffix in {".md", ".py", ".json", ".mjs", ".sh"}:
            text = p.read_text(encoding="utf-8", errors="ignore")
            hits += [f"{p.relative_to(ROOT)}: {o}" for o in olds if o in text]
    assert not hits, hits
