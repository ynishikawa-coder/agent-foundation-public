"""PreToolUse — 設計書の型の gate（check_spec_doc.py）を、封の入口 seal.py を通さず --lock で直に呼ぶ手を止める。

なぜ在るか: 封の入口 seal.py は 15 §6 の決定照合が済むまで gate を呼ばない。ところが gate を直に --lock で呼ぶと
  照合を見ずに LOCK され、決定の記録と食い違う設計書が合格証跡つきで渡りえた（入口を飛ばす別の道）。
  封への道を seal.py の 1 本にする。seal.py が中で gate を呼ぶのは Bash の道具を通らないので、ここには当たらない。
見分け方（網を既定にする）: 命令のどこかに gate の名と --lock（argparse が受ける略し --l・--lo・--loc・--lock=… を含む）が
  在れば止める。語は cmd_read.mentions（引用符で割った字を寄せ・変数を解き・-c／eval の中も割った語の集合）で見るので、
  段の頭の形（if/then・!・timeout -s・env -u・echo … | bash・perl -e・ssh・find -exec・cp して別名で走らせる 等）を問わない。
  通すのは、読み手が全部の段を「何も走らせない読むだけの命令」と証せた時（cmd_read.inert＝grep・cat・git log 等で読む）だけ。
  知らない形は証せないので止まる（読み手は通す側にだけ使う＝PR #81 のレビューの直し）。
  gate の名が無くても、--lock と読めない所（$(…)・解けない変数）が共に在る命令は止める（名を隠して走らせうる）。
止まるのは AI の道具の呼び出しだけ（人の手の命令は止めない）。
通す: --lock の無い呼び出し（各 step の機械チェック・--verify-receipt・--stamp）と、gate を読むだけの命令。
射程の外（正直に書く）: 別の script の file の中から gate を呼ぶ形・名を符号に隠す形（base64 等）は見えない。
  根の直しは gate 自身が seal.py の証跡を求めること（型の持ち主の repo の仕事・原因の台帳の行）。
"""
from __future__ import annotations

import cmd_read as R

GATE = "check_spec_doc.py"
LOCK = "--lock"


# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}


def _gate_named(words):
    stem = GATE.rsplit(".", 1)[0].lower()
    return any(stem in w.lower() for w in words)


def hit(cmd):
    """止める訳（1 行）か ""。"""
    if not isinstance(cmd, str) or R.inert(cmd):
        return ""
    words = R.mentions(cmd)
    lock = any(R.abbrev_of(w, LOCK) for w in words)
    if not lock:
        return ""
    if _gate_named(words):
        return "gate（%s）の名と --lock（略しを含む）が命令に共に在る" % GATE
    if R.read(cmd).opaque:
        return "--lock と読めない所（$(…)・解けない変数）が命令に共に在る（gate の名を隠して走らせうる）"
    return ""


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if data.get("tool_name") != "Bash":
        return ""
    cmd = (data.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str):
        return ""
    why = hit(cmd)
    if not why:
        return ""
    return ("設計書の型の gate（check_spec_doc.py）を封の入口を通さず直に --lock で呼ぶ手なので止めました（%s）。\n"
            "封は spec-doc の入口 seal.py から通します（15 §6 の決定照合が済むまで gate を呼ばない入口）:\n"
            "  python3 <spec-doc の skill の dir>/seal.py <設計書dir>\n"
            "照合だけ見たい時は seal.py に --match-only。--lock を付けない gate の呼び出し（各 step の機械チェック・"
            "--verify-receipt・--stamp）は止めません。" % why)
