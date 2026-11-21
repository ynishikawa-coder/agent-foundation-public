"""PreToolUse — 設計書の型の gate（check_spec_doc.py）を、封の入口 seal.py を通さず --lock で直に呼ぶ手を止める。

なぜ在るか: 封の入口 seal.py は 15 §6 の決定照合が済むまで gate を呼ばない。ところが gate を直に --lock で呼ぶと
  照合を見ずに LOCK され、決定の記録と食い違う設計書が合格証跡つきで渡りえた（入口を飛ばす別の道）。
  封への道を seal.py の 1 本にする。seal.py が中で gate を呼ぶのは Bash の道具を通らないので、ここには当たらない。
止める: Bash の命令のうち実際に動かす並び（guard_common.executed_parts）に check_spec_doc.py と --lock の両方が在る時。
  commit の文・grep の語・echo・file へ書く heredoc・注釈で名を挙げるだけの所は動かないので見ない。python3 - <<EOF の中身・
  bash -c の字・$( ) の中で動く並びは動く側。読み切れない形（` `・<( )・括弧の組）は命令の字全体で見る（止める側に倒す）。
  止まるのは AI の道具の呼び出しだけ（人の手の命令は止めない）。
通す: --lock の無い呼び出し（各 step の機械チェック・--verify-receipt・--stamp）。
射程の外（正直に書く）: 人が手で打つ命令・別の道具の中から呼ぶ形は見えない。根の直しは gate 自身が 15 §6 を読むこと
  （型の持ち主の repo の仕事）。
"""
from __future__ import annotations

import re

import guard_common as G

_GATE = re.compile(r"check_spec_doc\.py")
_LOCK = re.compile(r"(?<![\w-])--lock(?![\w-])")



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if data.get("tool_name") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str) or not any(_GATE.search(p) and _LOCK.search(p) for p in G.executed_or_whole(cmd)):
        return ""
    return ("設計書の型の gate（check_spec_doc.py）を --lock で直に呼ぶ手なので止めました。\n"
            "封は spec-doc の入口 seal.py から通します（15 §6 の決定照合が済むまで gate を呼ばない入口）:\n"
            "  python3 <spec-doc の skill の dir>/seal.py <設計書dir>\n"
            "照合だけ見たい時は seal.py に --match-only。--lock を付けない gate の呼び出し（各 step の機械チェック・"
            "--verify-receipt・--stamp）は止めません。")
