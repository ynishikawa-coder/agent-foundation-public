"""原因の台帳の行き先の見張り（PostToolUse・止めずに知らせる）。

決まり: 原因の台帳の行き先の値は細目 §3「原因の台帳」の行が正本（`直す窓`／`直した`／`直さない`、まだ付いていない行の印
「未定」）。各社の台帳（Javis は Notion の「原因の台帳」）の選べる値がこの表とずれると、表に無い値（例「オーナーの判断」）の行が
「直した」「直さない」のどちらでもないまま残り、根治の終わり（全部が直したか直さない）を数えられない。
前の形: 台帳へ書く道具の入力を誰も照らさず、細目は 3 つ・Notion の台帳は 5 つのまま、表に無い値で行が書かれていた。
今の形: Notion へページを書く・直す入力の中の `行き先` の値を細目の表（core の 細目.md を直に読む＝写さない）と照らし、表に無い値なら
  書いた後に知らせる（止めない＝新しく止めるにはオーナーの同意が要る）。直し方: 行を表の値へ替える。表に足すべき値なら、
  細目を直す PR（核・細目の変更はオーナーの同意）を出す。細目が読めない時は黙る（推して知らせない）。
"""
import os
import re

import guard_common as G

HOOKS = {"post": "check"}

KEY = "行き先"
WRITE_TOOLS = ("notion-create-pages", "notion-update-page")
_LINE = re.compile(r"^- \*\*原因の台帳\*\*.*$", re.M)


def saimoku_text():
    path = os.environ.get("AF_SAIMOKU") or G.sibling_plugin_file("core", "細目.md")
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def table(text):
    """(行き先の値の並び, まだ付いていない行の印) か None（細目の行が読めない）。"""
    m = _LINE.search(text or "")
    if not m:
        return None
    line = m.group(0)
    head = line.split("行き先を付ける:", 1)
    if len(head) != 2:
        return None
    vals = re.findall(r"`([^`]+)`", head[1].split("。", 1)[0])
    pend = re.search(r"行き先の無い行（([^）]+)）", line)
    if not vals or not pend:
        return None
    return vals, pend.group(1)


def _dests(v, out):
    """入力の中の `行き先` の値（文字の物）を全部拾う。"""
    if isinstance(v, dict):
        for k, x in v.items():
            if k == KEY and isinstance(x, str):
                out.append(x)
            else:
                _dests(x, out)
    elif isinstance(v, list):
        for x in v:
            _dests(x, out)
    return out


def check(data, vals):
    name = str(data.get("tool_name") or "")
    if not name.endswith(WRITE_TOOLS):
        return ""
    got = _dests(data.get("tool_input"), [])
    if not got:
        return ""
    t = table(saimoku_text())
    if t is None:
        return ""
    known, pend = t
    bad = sorted({v for v in got if v not in known and v != pend})
    if not bad:
        return ""
    return ("[guard] 原因の台帳の行き先 %s は細目 §3「原因の台帳」の表（%s・まだ付いていない行の印「%s」）に無い（書いた物は"
            "止めていない）。表に無い値の行は、細目 §7「根治の終わり」で数えられない。直し方: 行の行き先を表の値に"
            "替える（オーナーが決める物なら `直さない` は 1 行ずつオーナーに聞く）。台帳の選べる値の方を表に合わせるか、"
            "表に足す値なら細目を直す PR を出す（細目の変更はオーナーの同意）。"
            % ("・".join("「%s」" % b for b in bad), "・".join("`%s`" % k for k in known), pend))
