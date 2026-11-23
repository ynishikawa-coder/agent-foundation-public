"""題の知らせ（REMIND・REMIND_PARENT・REMIND_CHILD）が見せる種類×状態の印は、TITLE_TABLE から作られ、表と食い違わないかを見る。

意図: 窓に見せる「付けてよい題の印」が、照らしの正本（TITLE_TABLE）と常に同じで、知らせのとおりに付けた題が止まらない。
課題: 知らせの文が表の印を手で写し、表を直すと知らせだけ古い印を見せ続けうる形だった。
原因: 知らせの文が表を読まず、文字の並びで印を持っていた。
入力は全部作り物（作り物の状態 🧪 を足す・❓ を抜く表）。
"""
from test_session_watch import sw


def drift(table, texts):
    """表に在る印が知らせに無い・表から抜いた組み合わせが知らせに残る、を返す。"""
    forms = sw.title_forms(table)
    return [t[:40] for t in texts if forms not in t]


def test_今の知らせは表から作った物と同じ():
    assert (sw.REMIND, sw.REMIND_PARENT, sw.REMIND_CHILD) == sw.remind_texts(sw.TITLE_TABLE)
    assert not drift(sw.TITLE_TABLE, (sw.REMIND, sw.REMIND_PARENT, sw.REMIND_CHILD))


def test_表の印は全部知らせに出る():
    for k, sts in sw.TITLE_TABLE.items():
        for s in sts:
            if s:
                assert all(s in t for t in (sw.REMIND, sw.REMIND_PARENT, sw.REMIND_CHILD)), (k, s)


def test_注入_状態を足した表で知らせが付いてくる():
    fake = dict(sw.TITLE_TABLE)
    fake[sw.HAND] = tuple(fake[sw.HAND]) + ("🧪",)
    texts = sw.remind_texts(fake)
    assert all("🧪" in t for t in texts)
    # 手で写した今の知らせは、足した表に照らすと食い違う（写しが戻ると赤になる見張りの歯）
    assert drift(fake, (sw.REMIND, sw.REMIND_PARENT, sw.REMIND_CHILD))


def test_注入_状態を抜いた表で知らせから消える():
    fake = dict(sw.TITLE_TABLE)
    fake[sw.HUMAN] = tuple(s for s in fake[sw.HUMAN] if s != sw.ASKING)
    fake[sw.AI] = tuple(s for s in fake[sw.AI] if s != sw.ASKING)
    texts = sw.remind_texts(fake)
    assert all(sw.ASKING not in sw.title_forms(fake) and sw.title_forms(fake) in t for t in texts)
    assert drift(fake, (sw.REMIND, sw.REMIND_PARENT, sw.REMIND_CHILD))


def test_知らせは親の題を写さないと言い続ける():
    for t in (sw.REMIND_PARENT, sw.REMIND_CHILD):
        assert "親の題を写さない" in t
