"""PreToolUse — 試験から有料の上流（AI の API など）へ直接つながる線を書く手を止める。

なぜ在るか: 開発中の自動試験が、本物の AI の API を叩き続けて費用の大半を占めた実測がある。
データを壊す書き込みは全部塞いでいたのに、読み取り（AI に読ませる口）だけ本物を通していた。
費用も壊れ物として、試験の中で本物へつなぐ線を書く時に止める。

止める: 試験らしい path（tests/・e2e/・spec/・__tests__/・test_*.py・*.test.js …）へ書く中身に、
  有料の上流の鍵名か公式のエンドポイントが現れた時。
逃げ道: 中身に PAID_UPSTREAM_GUARD を書く（＝環境変数 1 本で本物へ切り替える共通の関所を通す宣言。既定は録画の再生か偽物）。

見る口: Write / Edit / MultiEdit / NotebookEdit と、Bash で試験らしい path へ書く形（`>`・`>>` のリダイレクト・
  `tee`・`sed -i`／`perl -i` の的）。Bash は命令の文全体（heredoc の中身を含む）に印があるかを見る。ただし命令の頭の
  環境の代入（`ANTHROPIC_API_KEY=dummy pytest … > tests/out.log`）は書く中身でないので抜く（鍵名を環境に置いて試験を回し、
  出力を試験の dir の log へ書くだけの命令は止めない）。命令の書き方は推し量らない（知らない書き方も全体を見る）。
射程の外（正直に書く）: 自分のサーバを経た中継（例: 手元のサーバが本物の鍵で AI へ中継する）は見えない。
  Bash でも、書く中身が命令の外にある形（cp・mv・別の script の中で書く・python -c の中の open・命令の出力を書く形）は見えない。
判定できない時は通す（1 つの不具合で書き込みを止めない）。
"""
from __future__ import annotations

import os
import re

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|e2e|__tests__|spec|specs|testing)(/|$)"
    r"|(^|/)test_[^/]*\.py$"
    r"|[._-](test|spec|e2e)\.[cm]?[jt]sx?$"
    r"|_test\.(py|go)$",
    re.I)

PAID_MARKERS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "FAL_KEY", "REPLICATE_API_TOKEN",
    "api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com",
    "api.mistral.ai", "api.cohere.ai", "api.groq.com",
)
GUARD_MARKER = "PAID_UPSTREAM_GUARD"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CONTENT_KEYS = ("content", "new_string", "new_source")



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

def _path_of(tool_input):
    for k in ("file_path", "notebook_path"):
        v = tool_input.get(k)
        if v:
            return str(v)
    return ""


def _payload(tool_input):
    """書こうとしている中身を全部つなげる（MultiEdit の edits も含む）。"""
    parts = [tool_input[k] for k in CONTENT_KEYS if isinstance(tool_input.get(k), str)]
    for e in tool_input.get("edits") or []:
        if isinstance(e, dict):
            parts += [e[k] for k in CONTENT_KEYS if isinstance(e.get(k), str)]
    return "\n".join(parts)


def reason(path, hits):
    return (
        "試験から有料の上流（AI の API など）へ直接つながる線なので止めました。\n"
        "  書こうとしている file: {}\n"
        "  当たった印: {}\n"
        "開発中の自動試験が本物の API を叩き続けると、費用の大半がそこに消えます（実測がある）。\n"
        "進め方:\n"
        "  ① 既定は録画の再生か偽物にする（本物が無い時は赤で止める。『無ければ本物で』の逃げは黙って課金する）\n"
        "  ② 本物を通す線が本当に要るなら、環境変数 1 本で切り替える共通の関所を通し、この file に `{}` を書く\n"
        "  ③ 手元のサーバが本物の鍵で中継していないかも、その行を引用して確かめる（この見張りからは見えない）"
    ).format(path, " / ".join(hits), GUARD_MARKER)


# Bash で file へ書く的: リダイレクト（> と >>・2> などの数字つきや >& は除く）・tee・sed -i／perl -i の最後の語
_REDIRECT = re.compile(r"(?<![0-9&>])>>?\s*(?!&)([^\s;&|<>()]+)")
_TEE = re.compile(r"\btee\b((?:\s+-[a-zA-Z]+)*)((?:\s+[^\s;&|<>()-][^\s;&|<>()]*)+)")
_INPLACE = re.compile(r"\b(?:sed|perl)\s+[^;&|]*?-i\S*[^;&|]*?\s([^\s;&|<>()]+)\s*(?:$|[;&|])", re.M)


# 命令の頭の環境の代入（`ANTHROPIC_API_KEY=dummy pytest …`）。鍵の名を環境に置いて試験を回すだけの形で、試験の file へ
# 書く中身ではない。照らす字からこれだけを抜き、残りは命令の文全体を見る（命令の書き方を推し量らない＝知らない形も見る）。
_ASSIGN_AT = re.compile(r"\s*((?:[A-Za-z_][A-Za-z0-9_]*=(?:'[^']*'|\"[^\"]*\"|[^\s;&|'\"]*)\s+)+)")
_KEYWORD_AT = re.compile(r"\s*(?:then|do|else)\b")


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def written_text(cmd):
    """照らす字: 命令の文全体から、命令の頭の環境の代入だけを抜いた物。引用符の中と heredoc の中身は命令の頭と見ない
    （そのまま照らす）。引用符が閉じない命令は何も抜かない（読めない形は全体を見る）。"""
    out, i, q, head = [], 0, "", True
    tags = []                              # この行で開いた heredoc の終わりの印（改行の後は中身をそのまま写す）
    while i < len(cmd):
        if not q and cmd[i] == "\n" and tags:
            out.append("\n")
            i += 1
            for tag in tags:
                while i < len(cmd):
                    end = cmd.find("\n", i)
                    line = cmd[i:] if end < 0 else cmd[i:end + 1]
                    out.append(line)
                    i += len(line)
                    if line.strip() == tag:
                        break
            tags = []
            head = True
            continue
        if not q:
            h = _HEREDOC.match(cmd, i)
            if h:
                tags.append(h.group(2))
                out.append(h.group(0))
                i = h.end()
                head = False
                continue
        if not q and head:
            m = _ASSIGN_AT.match(cmd, i)
            if m:
                i = m.end()
                head = False
                continue
            k = _KEYWORD_AT.match(cmd, i)
            if k:
                out.append(cmd[i:k.end()])
                i = k.end()
                continue
        c = cmd[i]
        if q:
            if c == "\\" and q == '"':
                out.append(cmd[i:i + 2])
                i += 2
                continue
            if c == q:
                q = ""
        elif c in "'\"":
            q = c
        elif c == "\\":
            out.append(cmd[i:i + 2])
            i += 2
            head = False
            continue
        out.append(c)
        if not q:
            head = c in ";&|(\n" or (head and c.isspace())
        i += 1
    return cmd if q else "".join(out)


def bash_writes(cmd):
    """Bash の命令が file へ書く (的, 照らす字) の並び（推し量り）。照らす字は命令の文全体から頭の環境の代入を抜いた物。"""
    text = written_text(cmd)
    out = [m.group(1) for m in _REDIRECT.finditer(cmd)]
    for m in _TEE.finditer(cmd):
        out += m.group(2).split()
    out += [m.group(1) for m in _INPLACE.finditer(cmd)]
    return [(t.strip("'\""), text) for t in out if t.strip("'\"") not in ("/dev/null", "-")]


def bash_targets(cmd):
    """Bash の命令が書く file の path の並び（推し量り）。"""
    return [t for t, _ in bash_writes(cmd)]


def check_bash(data, vals):
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str) or GUARD_MARKER in cmd:
        return ""
    markers = list(PAID_MARKERS) + [m for m in vals.get("paid_markers_extra") or [] if isinstance(m, str) and m]
    tests, hits = [], []
    for target, content in bash_writes(cmd):
        if not TEST_PATH_RE.search(target.replace(os.sep, "/")):
            continue
        found = [m for m in markers if m in content]
        if found:
            tests.append(target)
            hits += [m for m in found if m not in hits]
    return reason(", ".join(tests), hits) if hits else ""


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") == "Bash":
        return check_bash(data, vals)
    if str(data.get("tool_name") or "") not in WRITE_TOOLS:
        return ""
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    path = _path_of(tool_input)
    if not path or not TEST_PATH_RE.search(path.replace(os.sep, "/")):
        return ""
    body = _payload(tool_input)
    if not body or GUARD_MARKER in body:
        return ""
    markers = list(PAID_MARKERS) + [m for m in vals.get("paid_markers_extra") or [] if isinstance(m, str) and m]
    hits = [m for m in markers if m in body]
    return reason(path, hits) if hits else ""
