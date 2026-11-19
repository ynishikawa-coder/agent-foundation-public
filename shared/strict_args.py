"""命令の印を厳しく読む 1 本の口（土台の命令は全部これで印を読む＝印の読み方を各命令に写さない）。

なぜ在るか: argparse の既定は、値を 1 つ取る印を 2 度書くと 1 つ目を黙って捨て（`--dest a --dest b` は b だけ）、
印の頭だけ書いても（`--de`）黙って受ける。どちらも、打った人が思った値と違う値で命令が動く。知らない値は既定で止める
（核 §3）ので、ここで止める。

  - 値を 1 つ取る印（store）を 2 度書いたら止める（exit 2）。並べて取る印（append・nargs）は今までどおり。
  - 印の頭だけの書き方（略記）を受けない（allow_abbrev=False）。知らない印は argparse の既定どおり止める。

使い方: `from strict_args import ArgumentParser` を argparse.ArgumentParser の代わりに使う。plugin の中の命令は
plugin の lib/strict_args.py（この file への symlink。入れる時に実物へ写される）を読む。
"""
from __future__ import annotations

import argparse


class _Once(argparse._StoreAction):
    """値を 1 つ取る印。同じ印（同じ dest）を 1 度の読みで 2 度書いたら止める。"""

    def __call__(self, parser, namespace, values, option_string=None):
        seen = getattr(parser, "_af_seen", None)
        if option_string and seen is not None:
            if self.dest in seen:
                parser.error("%s を 2 度書いた（1 つ目「%s」と 2 つ目「%s」のどちらで動くか決められない）。1 つにして打ち直す"
                             % ("/".join(self.option_strings), seen[self.dest], values))
            seen[self.dest] = values
        super().__call__(parser, namespace, values, option_string)


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
        self.register("action", None, _Once)
        self.register("action", "store", _Once)

    def parse_known_args(self, args=None, namespace=None):
        self._af_seen = {}
        try:
            return super().parse_known_args(args, namespace)
        finally:
            self._af_seen = None
