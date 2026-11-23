"""試験が決まりの文書（Markdown）を構造で読む 1 か所: 見出し・節・箇条の子・太字の欄・表の行。

意図: 試験が「決まりがこの形（節・欄・段・行）で、この順で在るか」を照らし、文の言い回しには頼らない。
課題: 試験が文を丸ごと字で照らしていたので、言い回しを変えると赤・順を崩しても字が残れば緑・注記（HTML の注記や
  コードの囲い）の中の字でも緑だった。
原因: 試験が文書の構造を読む口を持たず、各試験が `"字" in text` で照らしていた。
読み方: 注記（<!-- … -->）とコードの囲い（```）の中は構造に数えない（見出し・欄に見えても字の例なので）。
"""
from __future__ import annotations

import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEAD = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


def 地の行(text: str) -> list[str]:
    """注記とコードの囲いの中を空の行にした行の列（行の番号は元と揃う）。"""
    text = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            out.append("")
            continue
        out.append("" if fence else line)
    return out


def 見出し(text: str, level: int | None = None) -> list[str]:
    """見出しの名を順に返す（level を渡すとその深さだけ）。"""
    out = []
    for line in 地の行(text):
        m = _HEAD.match(line)
        if m and (level is None or len(m.group(1)) == level):
            out.append(m.group(2))
    return out


def 節(text: str, name: str) -> str | None:
    """名が name の見出しの節の本文（次の同じか浅い見出しまで・見出しの行は含まない）。無い・2 つ在る時は None。"""
    lines = 地の行(text)
    hits = [(n, len(m.group(1))) for n, l in enumerate(lines) if (m := _HEAD.match(l)) and m.group(2) == name]
    if len(hits) != 1:
        return None
    start, depth = hits[0]
    body = []
    for line in lines[start + 1:]:
        m = _HEAD.match(line)
        if m and len(m.group(1)) <= depth:
            break
        body.append(line)
    return "\n".join(body)


_ITEM = re.compile(r"^([ \t]*)- \*\*(.+?)\*\*(.*)$")


def 箇条の子(text: str, head: str) -> list[tuple[str, str]] | None:
    """太字の名が head の箇条（`- **head**…`）の、すぐ下の子の箇条（`  - **名** — 本文`）を (名, 本文) の順の列で返す。
    子の本文は、その子のさらに下の行も含む。head の箇条が無い・2 つ在る時は None。"""
    lines = 地の行(text)
    hits = [n for n, l in enumerate(lines) if (m := _ITEM.match(l)) and m.group(2) == head]
    if len(hits) != 1:
        return None
    indent = len(_ITEM.match(lines[hits[0]]).group(1))
    kids: list[list] = []
    for line in lines[hits[0] + 1:]:
        if not line.strip():
            continue
        lead = len(line) - len(line.lstrip(" \t"))
        if lead <= indent:
            break
        m = _ITEM.match(line)
        if m and kids and lead > kids[0][2]:
            kids[-1][1] += "\n" + line.strip()
        elif m:
            kids.append([m.group(2), m.group(3).lstrip(" —-:："), lead])
        elif kids:
            kids[-1][1] += "\n" + line.strip()
    return [(k[0], k[1]) for k in kids]


_FIELD = re.compile(r"^(?:[-*][ \t]+)?\*\*(.+?)\*\*")


def 太字の欄(unit: str) -> list[tuple[str, str]]:
    """行の頭が太字の名で始まる欄を (名, 中身) の順の列で返す。中身は次の欄の行の手前まで（下の箇条も含む）。
    箇条の子（字下げした行）の太字は欄に数えない。"""
    out: list[list[str]] = []
    for line in 地の行(unit):
        m = _FIELD.match(line)
        if m:
            name = re.split(r"[（(]", m.group(1))[0].strip()
            out.append([name, line[m.end():]])
        elif out:
            out[-1][1] += "\n" + line
    return [(a, b) for a, b in out]


def 表の行(text: str, first: str) -> list[list[str]]:
    """頭の行の 1 つ目の升が first の表の、中の行を升の列で返す（頭の行と区切りの行は除く）。無ければ []。"""
    lines = 地の行(text)
    for n, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if cells and cells[0] == first:
            rows = []
            for nxt in lines[n + 1:]:
                if not nxt.strip().startswith("|"):
                    break
                row = [c.strip() for c in nxt.strip().strip("|").split("|")]
                if set("".join(row)) <= set("-: "):
                    continue
                rows.append(row)
            return rows
    return []


def 欄(text: str, name: str) -> str | None:
    """行の頭の太字の名が name の欄（`- **name** — …` か `**name**: …`）の中身。次の欄の行・見出し・字下げの浅い箇条の
    手前まで（欄の下の字下げした行は含む）。無い・2 つ在る時は None（どの欄かを決められないので照らさせない）。"""
    lines = 地の行(text)
    hits = []
    for n, line in enumerate(lines):
        m = _FIELD.match(line)
        if m and re.split(r"[（(]", m.group(1))[0].strip() == name:
            hits.append((n, m.end()))
    if len(hits) != 1:
        return None
    start, end = hits[0]
    lead = len(lines[start]) - len(lines[start].lstrip(" \t"))
    body = [lines[start][end:]]
    for line in lines[start + 1:]:
        if not line.strip():
            body.append("")
            continue
        here = len(line) - len(line.lstrip(" \t"))
        if _HEAD.match(line) or (here <= lead and (_FIELD.match(line) or line.lstrip().startswith(("- ", "* ", "|")))):
            break
        body.append(line)
    return "\n".join(body).strip().lstrip("—-:：").strip()


def 置き場(text: str, word: str) -> list[str]:
    """地の行（注記・コードの囲いの外）で word が在る所の、いちばん内の見出しの名を出る順に返す（見出しの前は ""）。
    注記や囲いの中にしか無ければ [] ＝字が在っても決まりとして置かれていない。"""
    out, here = [], ""
    for line in 地の行(text):
        m = _HEAD.match(line)
        if m:
            here = m.group(2)
        if word in line:
            out.append(here)
    return out
