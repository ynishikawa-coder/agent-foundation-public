"""PreToolUse — 設計書の型の gate（check_spec_doc.py）を、封の入口 seal.py を通さず --lock で直に呼ぶ手を止める。

なぜ在るか: 封の入口 seal.py は 15 §6 の決定照合が済むまで gate を呼ばない。ところが gate を直に --lock で呼ぶと
  照合を見ずに LOCK され、決定の記録と食い違う設計書が合格証跡つきで渡りえた（入口を飛ばす別の道）。
  封への道を seal.py の 1 本にする。seal.py が中で gate を呼ぶのは Bash の道具を通らないので、ここには当たらない。
止める: Bash の命令のうち実際に動かす並び（guard_common.executed_parts）に check_spec_doc.py と --lock の両方が在る時。
  命令の行が 1 つの素の命令（shell の特別な字〔改行・| & ; < > $ ` \\ ( ) { }〕と引用の外の glob の字〔* ? [〕が 1 つも無く、
  命令の名が path を含まない素の名で、代入・export・tee など file や環境へ出す手でない形）で、引数が全部「字を渡す口」の表
  （guard_common._SLOTS: commit の文・PR の本文・grep の型・echo の字など）に収まる時だけ、名を挙げるだけとして外す（注釈も外す）。
  表の外の道具・前置きが 1 つでも在れば・読み切れない物が在れば命令の字全体で見る（前の版と同じ判定＝止める側に倒す）。
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
