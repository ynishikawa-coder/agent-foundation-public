"""PreToolUse — 設計書の型の gate（check_spec_doc.py）を、封の入口 seal.py を通さず --lock で直に呼ぶ手を止める。

なぜ在るか: 封の入口 seal.py は 15 §6 の決定照合が済むまで gate を呼ばない。ところが gate を直に --lock で呼ぶと
  照合を見ずに LOCK され、決定の記録と食い違う設計書が合格証跡つきで渡りえた（入口を飛ばす別の道）。
  封への道を seal.py の 1 本にする。seal.py が中で gate を呼ぶのは Bash の道具を通らないので、ここには当たらない。
見分け方: 命令の字を探さず、シェルが実際に渡す語の並び（cmd_read の読み手＝引用符で割った字・変数・bash -c／eval の
  中・前に付く包みを解いた形）で見る。gate を走らせる段（gate の file を直に走らせる段・python の類が gate を走らせる段）に、
  --lock か argparse が受ける略し（--l・--lo・--loc・--lock=…）が在れば止める。
読めない時は止める側: gate を走らせる段の、走らせる file や印の語が読めない（$(…)・解けない変数）時も止める。
  python の -c の中身に gate の名が在る時も止める（python の中の呼び出しは読み手の外）。
止まるのは AI の道具の呼び出しだけ（人の手の命令は止めない）。
通す: --lock の無い呼び出し（各 step の機械チェック・--verify-receipt・--stamp）。
射程の外（正直に書く）: 別の script の file の中から gate を呼ぶ形は見えない（その script を走らせる命令の字には gate が無い）。
  根の直しは gate 自身が seal.py の証跡を求めること（型の持ち主の repo の仕事・原因の台帳の行）。
"""
from __future__ import annotations

import os
import re

import cmd_read as R

GATE = "check_spec_doc.py"
LOCK = "--lock"
PY = re.compile(r"^(?:python[\d.]*|pypy[\d.]*|py)$")
RUNNERS = {"uv": ("run",), "pipx": ("run",), "poetry": ("run",), "pdm": ("run",), "hatch": ("run",), "rye": ("run",)}


# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}


def _script(words):
    """段が走らせる file の語（gate を走らせうる所）と、その後ろの語の並び。走らせない段は (None, [])。"""
    if not words:
        return None, []
    prog = R.prog_name(words)
    if prog in RUNNERS:
        i = 1
        while i < len(words) and words[i].text in RUNNERS[prog]:
            i += 1
        words = words[i:]
        prog = R.prog_name(words)
    if not words:
        return None, []
    if words[0].opaque or prog.endswith(".py") or prog == GATE:
        return words[0], words[1:]
    if PY.match(prog):
        i = 1
        while i < len(words):
            t = words[i].text
            if t == "-c" or t.startswith("-c"):
                code = words[i + 1] if t == "-c" and i + 1 < len(words) else R.Word(t[2:], words[i].opaque)
                return R.Word("-c:" + code.text, code.opaque), words[i + 1:]
            if t == "-m":
                return (words[i + 1] if i + 1 < len(words) else None), words[i + 2:]
            if t.startswith("-"):
                i += 1
                continue
            return words[i], words[i + 1:]
    return None, []


def hit(cmd):
    """止める訳（1 行）か ""。"""
    reading = R.read(cmd)
    for seg in reading.segments:
        script, rest = _script(seg)
        if script is None:
            continue
        if script.text.startswith("-c:"):
            if GATE.split(".")[0] in script.text:
                return "python の -c の中で gate（%s）を呼ぶ" % GATE
            continue
        is_gate = os.path.basename(script.text) == GATE or GATE in script.text
        lock = any(R.abbrev_of(w.text, LOCK) for w in rest)
        unread_lock = any(w.opaque for w in rest)
        if is_gate and lock:
            return "gate（%s）を --lock（略しを含む）で直に呼ぶ" % GATE
        if is_gate and unread_lock:
            return "gate（%s）に読めない印（$(…)・解けない変数）を渡す" % GATE
        if script.opaque and (lock or GATE in cmd):
            return "走らせる file が読めない（$(…)・解けない変数）段に --lock か gate の名が在る"
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
