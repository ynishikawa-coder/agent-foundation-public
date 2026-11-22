"""根治の 5 段の形を崩した細目と MGK の欄は赤になり、言い回しを変えただけなら緑のまま。

意図: test_mgk_5_dan.py の構造の照らし（段の名と順・段の受け渡し・段の要・MGK の欄）が、わざと崩した入力を拒む事を示す。
課題: 字で照らしていた頃は、段の順を入れ替えても・段を箇条から外して字だけ残しても・注記に入れても緑だった。
原因: 試験が文書の構造を読む口を持たなかった（構造は tests/md_yomi.py で読む）。
"""
from md_yomi import 箇条の子
from test_mgk_5_dan import CORE, MGK_の外れ, 段の外れ, 段の要, _3節


def _段を入れ替える(s3, a, b):
    kids = dict(箇条の子(s3, "根治の 5 段"))
    la, lb = (f"  - **{n}** — {kids[n]}".split("\n")[0] for n in (a, b))
    return s3.replace(la, "\0").replace(lb, la).replace("\0", lb)


def test_注入_段の順を入れ替えると赤():
    s3, k3 = _3節()
    assert any("順" in x for x in 段の外れ(_段を入れ替える(s3, "課題", "原因"), k3))
    assert any("同じ原因の他の問題" in x for x in 段の外れ(_段を入れ替える(s3, "同じ原因の他の問題", "解決"), k3))


def test_注入_段を箇条から外して字だけ残すと赤():
    s3, k3 = _3節()
    broken = s3.replace("  - **課題** — ", "課題も含めて書く。", 1)
    assert "課題" in broken
    assert 段の外れ(broken, k3)


def test_注入_課題が原因の段を指さないと赤_言い回しを変えても形が在れば緑():
    s3, k3 = _3節()
    kadai = dict(箇条の子(s3, "根治の 5 段"))["課題"]
    assert any("課題 の段が 原因" in x for x in 段の外れ(s3.replace(kadai, "起きた事のずれを書く。"), k3))
    kids = 箇条の子(s3, "根治の 5 段")
    reworded = s3
    for name, body in kids:
        keep = [n for n, _ in kids if n in body.split("\n")[0]] + [w for w in 段の要.get(name, []) if w in body.split("\n")[0]]
        reworded = reworded.replace(body.split("\n")[0], "言い換えた文。" + "・".join(keep) + "。", 1)
    assert reworded != s3
    assert 段の外れ(reworded, k3) == []


def test_注入_MGK_の欄を消す_段を指さない_注記に入れると赤():
    furumai, s3 = (CORE / "振る舞い.md").read_text(encoding="utf-8"), _3節()[0]
    assert MGK_の外れ(furumai.replace("- **MGK** —", "- MGK —"), s3)
    assert MGK_の外れ(furumai.replace("根治の 5 段の見出し", "決まった見出し"), s3)
    line = next(l for l in furumai.splitlines() if l.startswith("- **MGK**"))
    assert MGK_の外れ(furumai.replace(line, "<!-- " + line + " -->"), s3)
    assert MGK_の外れ(furumai, s3.replace("（呼び名 MGK。", "（"))


def test_注入_段の要を別の段へ移す_受け渡しを消すと赤():
    s3, k3 = _3節()
    kids = dict(箇条の子(s3, "根治の 5 段"))
    moved = s3.replace("意図そのものの誤りも疑う。", "", 1).replace(kids["課題"].split("\n")[0], kids["課題"].split("\n")[0] + "意図そのものの誤りも疑う。", 1)
    assert "意図そのもの" in moved
    assert any("意図 の段に要が無い" in x for x in 段の外れ(moved, k3))
    assert any("課題 の段に要が無い: 症状" in x for x in 段の外れ(s3.replace("渡された 1 件の症状を課題の幅にしない。", ""), k3))
    assert any("未来 の段が 解決" in x for x in 段の外れ(s3.replace("言えない時は解決がまだ足りていない。", ""), k3))
    assert MGK_の外れ((CORE / "振る舞い.md").read_text(encoding="utf-8"), s3.replace("言われた時の答え方は振る舞いの既定", "答え方は別"))
