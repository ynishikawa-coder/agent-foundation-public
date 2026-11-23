"""約束: 根治の入口を指すと見るのは、入口の字を持つ道具か、1 本の口を本当に呼ぶ道具だけ（字も口も無い道具・注に書いただけの import は通さない）。"""
from test_core_plugin import 根治の入口を指す


def test_注入_入口の字も口の呼び出しも無い道具は入口を指さない():
    assert not 根治の入口を指す('print("赤")\nsys.exit(1)\n')
    assert not 根治の入口を指す('# from root_cause import root_cause\nsys.exit(1)\n')
    assert 根治の入口を指す('    from root_cause import root_cause  # noqa: E402\n')
