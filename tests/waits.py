"""前提の file を待つ飛ばしの 1 つの口（check_all が数える）。

前の形: 試験は `if not PICTURE.is_file(): pytest.skip("待ち: docs/全体の絵.json …")` と、飛ばす条件の path と理由の文の
path を別々に手で書き、check_all は理由の文の字を読んで path の在る無しを照らした。2 つの path がずれると前提が満ちても
飛んだまま緑で、在りもしない path を文に書けば CI で部品が無くて飛ぶ試験も隠せた。
今の形: wait_for(path, 何か) だけが待つ物の飛ばしを出す。条件（path が無い）と理由は同じ 1 つの path から作り、
飛ばす例外に path を印（af_wait_path）で持たせる。check_all は理由の文を読まず、この印と待つ物の表 tests/waits.txt を照らす
（表に無い path・在るのに飛んだ path は赤）。
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def wait_for(rel, what):
    """repo の根からの path rel が在ればその Path を返し、無ければ「待ち」として飛ばす。"""
    path = ROOT / rel
    if path.exists():
        return path
    exc = pytest.skip.Exception(f"待ち: {rel}（{what}）が無い。入れば飛ばさず照らす", _use_item_location=True)
    exc.af_wait_path = rel
    raise exc
