"""並ぶ PR が同じ大きな file を取り合って衝突しない形を照らす（細目を節ごとの file に）。

意図: 並べた窓の PR が、main に先に入った PR と衝突せずに入る（衝突を解く往復でレビューを回し直さない）。
課題: 開いた PR の多くが、約 2.4 万字 1 枚の 細目.md を同時に触り、
1 本入るたびに残りが衝突した。
原因: 別々の話の文が 1 枚の file に集まり、全部の PR が同じ所（同じ file・同じ末尾）へ足す形だった。
解決: 細目は節ごとの file（plugins/core/細目/<番号>-<名>.md）。
"""
import re
import shutil


from saimoku import DIR

_HEAD = re.compile(r"^## (?:(\d+)\.\s+)?(.+?)\s*$", re.M)


def 節の形の外れ(d):
    """節ごとの file の形から外れた物の並び: 1 つの file に節が 2 つ以上・名の番号と見出しの番号が違う・頭の file 以外に節が無い。"""
    bad = []
    for f in sorted(d.glob("*.md")):
        heads = _HEAD.findall(f.read_text(encoding="utf-8"))
        no = f.name.split("-", 1)[0]
        if no == "00":
            if heads:
                bad.append(f"{f.name}: 頭の file に節が在る")
            continue
        if len(heads) != 1:
            bad.append(f"{f.name}: 節が {len(heads)} 個（1 file に 1 節）")
        elif heads[0][0] and int(heads[0][0]) != int(no):
            bad.append(f"{f.name}: 名の番号 {no} と見出しの番号 {heads[0][0]} が違う")
    return bad


def test_細目は_1_節_1_file():
    assert 節の形の外れ(DIR) == []
    assert not (DIR.parent / "細目.md").exists(), "割る前の 1 枚が戻った（節ごとの file と 2 つの正本になる）"


def test_注入_2_つの節を_1_file_に入れると赤(tmp_path):
    d = tmp_path / "細目"
    shutil.copytree(DIR, d)
    three, four = d / "03-直すは根治.md", d / "04-聞き方.md"
    three.write_text(three.read_text(encoding="utf-8") + "\n" + four.read_text(encoding="utf-8"), encoding="utf-8")
    four.unlink()
    assert any("03-直すは根治.md: 節が 2 個" in b for b in 節の形の外れ(d))

