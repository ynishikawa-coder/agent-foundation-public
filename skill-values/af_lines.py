"""行の区切りの 1 本の口（行で照らす物を、相手と同じ区切りで切る）。

相手＝GitHub の表示（CommonMark）・JSONL・git の出力は、行を \n・\r\n・\r だけで切る。
str.splitlines は U+2028・U+2029・U+0085・\v・\f・\x1c-\x1e でも切る＝表示では 1 行の物に偽の行
（偽の見出し・偽の欄・偽の締め）を作り、1 行の語を割って行ごとの照合をすり抜けさせ、JSONL の 1 行を割って読めなくする。
行で照らす道具はここを通す（各 plugin の lib/ へは symlink で届く）。
"""
from __future__ import annotations

import re

LINE_END = re.compile(r"\r\n?|\n")


def text_lines(text):
    """相手と同じ区切りで切った行。末尾の改行の後の空の行は入れない（行の数は splitlines と同じ）。"""
    if not text:
        return []
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text[-1:] in ("\n", "\r"):
        text = text[:-1]
    return LINE_END.split(text)
