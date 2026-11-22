"""決まりの file ごとに、文を 1 つ消しても試験が赤にならない文が守らない文の表と合うか（照らし方の正本は tests/test_rule_holes.py）。

意図: PR ごとの検査を速くしたまま、決まりの文の照らしを 1 文も減らさない。
課題: 決まりの file を全部 1 本の試験で消して回していたので、検査の組を分けてもその 1 本の組だけが長かった。
原因: 消して回す仕事が決まりの file の数だけ在るのに、1 本の試験に束ねていた。
ここでは決まりの file ごとに 1 本にし、check_all が組に散らして同時に回す（決まりの試験の探しは組ごとに 1 回）。
"""
import pytest

import test_rule_holes as rh   # pytest が集めた同じ module（決まりの試験の探しを組の中で 1 回にする）



def AF_SHARD_WEIGHT(nodeid):
    """check_all が組に分ける時の試験ごとの重さ。消して回す時間は決まりの file の大きさにほぼ比べる
    （測った値: 8695 バイトで約 200 秒・309 バイトで約 15 秒）。ほかの試験 1 本（約 0.1 秒）を 1 として、5 バイトで 1。"""
    rel = nodeid.rsplit("[", 1)[-1].rstrip("]")
    return max(1, len((rh.ROOT / rel).read_bytes()) // 5) if rel in rh.RULE_FILES else 1


@pytest.mark.parametrize("rel", rh.RULE_FILES)
def test_決まりの文は消すと試験が赤になるか_守らない文の表に在り_表に古い行が無い(rel):
    now = {(rel, s) for s in rh.穴(rel)}
    table = {(r, s) for r, s in rh.表() if r == rel}
    new, stale = sorted(now - table), sorted(table - now)
    assert not new, ("この文を消しても試験が赤にならない（文を照らす試験を足す。足せない訳がある時だけ "
                     "tests/data/試験で守らない文/ に 1 件 1 file で載せる・名は 表の名）:\n" + "\n".join(f"{r}\t{s}" for r, s in new)
                     + "\n照らしから外れた試験（元の文で通らない・用意できない fixture）:\n"
                     + "\n".join(f"{k}: {v}" for k, v in sorted(rh.外れた.items())))
    assert not stale, ("表の文が無くなったか、試験で守られるようになった（表から消す）:\n"
                       + "\n".join(f"{r}\t{s}" for r, s in stale))


def test_守らない文の表の行はどれも決まりの_file_を名指す():
    """file ごとに照らすと、決まりの file でない path の行はどの回にも拾われない＝古い行が残る。それを拒む。"""
    bad = sorted((r, s) for r, s in rh.表() if r not in rh.RULE_FILES)
    assert not bad, "決まりの file でない path の行（表から消す）:\n" + "\n".join(f"{r}\t{s}" for r, s in bad)
