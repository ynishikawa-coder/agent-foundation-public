"""根治の入口を指すと見るのは、入口の字を持つ道具か、1 本の口を本当に呼ぶ道具だけか（注入の試験）。

意図: 止めた・赤の知らせを出す道具が、根治の入口（細目 §3「まず構造を疑う」）へ必ず案内する。
課題: 口（lib/root_cause.py）を呼ぶ道具は入口の字を自分で持たないので、字だけを見る照らしでは通らず、字を注に写す形が戻っていた。
原因: 照らしが「入口の字が file に在るか」だけを見て、口を呼ぶ形を知らなかった。"""
from test_core_plugin import 根治の入口を指す


def test_注入_入口の字も口の呼び出しも無い道具は入口を指さない():
    assert not 根治の入口を指す('print("赤")\nsys.exit(1)\n')
    assert not 根治の入口を指す('# from root_cause import root_cause\nsys.exit(1)\n')
    assert 根治の入口を指す('    from root_cause import root_cause  # noqa: E402\n')
