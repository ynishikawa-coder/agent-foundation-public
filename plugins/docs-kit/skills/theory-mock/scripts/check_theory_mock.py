#!/usr/bin/env python3
"""理論モック HTML の巡回検査（/theory-mock の出口）。

`<html>?selftest` を docs-kit の共通の口（plugins/docs-kit/scripts/page_selftest.py）で開き、
枠の selftest が書いた `<pre id="selftest">` を読む。全画面（自動の全質問画面を含む）を描画して
例外・console.error・飛び先の無い data-go が 0 なら OK。

使い方:
    python3 check_theory_mock.py <理論モック.html>

終了コード:
    0 = SELFTEST OK
    1 = SELFTEST NG（NG 行と、最後に根治の入口＝細目 §3「まず構造を疑う」を指す `直し:` の行を出す・文は page_selftest が持つ）／
        selftest の結果が DOM に無い
    2 = Chrome が無い・起動できない
標準ライブラリだけ。
"""
from __future__ import annotations

import sys
from pathlib import Path

# Chrome の探し方・?selftest の読み方は docs-kit の共通の口が正本（型ごとに写さない）
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import page_selftest as PS  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("使い方: check_theory_mock.py <理論モック.html>", file=sys.stderr)
        return 1
    return PS.check(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
