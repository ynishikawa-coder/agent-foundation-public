"""PreToolUse — 試験から有料の上流（AI の API など）へ直接つながる線を書く手を止める。

なぜ在るか: 開発中の自動試験が、本物の AI の API を叩き続けて費用の大半を占めた実測がある。
データを壊す書き込みは全部塞いでいたのに、読み取り（AI に読ませる口）だけ本物を通していた。
費用も壊れ物として、試験の中で本物へつなぐ線を書く時に止める。

止める: 試験らしい path（tests/・e2e/・spec/・__tests__/・test_*.py・*.test.js …）へ書く中身に、
  有料の上流の鍵名か公式のエンドポイントが現れた時。
逃げ道: 中身に PAID_UPSTREAM_GUARD を書く（＝環境変数 1 本で本物へ切り替える共通の関所を通す宣言。既定は録画の再生か偽物）。

見る口: Write / Edit / MultiEdit / NotebookEdit と、Bash で試験らしい path へ書く形（`>`・`>>` のリダイレクト・
  `tee`・`sed -i`／`perl -i` の的）。Bash は、その的へ実際に書く中身（heredoc の中身・echo／printf の字・tee へ流す
  echo／printf の字・sed／perl の式）にだけ印があるかを見る（命令の文全体を見ない＝鍵名を環境に置いて試験を回し、
  出力を試験の dir の log へ書くだけの命令は止めない）。
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


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SEP = re.compile(r"(\|\||&&|;|\||&(?!>))")
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PRINTERS = ("echo", "printf")


def _segments(cmd):
    """命令を (区切りの前の記号, 段の字, heredoc の中身の並び) に分ける。heredoc の中身は、その << を持つ段に付ける。"""
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        i += 1
        tags = [m.group(2) for m in _HEREDOC.finditer(line)]
        bodies = []
        for tag in tags:
            body = []
            while i < len(lines) and lines[i].strip() != tag:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append("\n".join(body))
        parts = _SEP.split(line)
        prev = ""
        for j in range(0, len(parts), 2):
            seg = parts[j]
            n = len(_HEREDOC.findall(seg))
            own, bodies = bodies[:n], bodies[n:]
            out.append((prev, seg, own))
            prev = parts[j + 1] if j + 1 < len(parts) else ""
    return out


def _prog(seg):
    words = [w for w in seg.split() if not _ASSIGN.match(w)]
    return os.path.basename(words[0]) if words else ""


def bash_writes(cmd):
    """Bash の命令が file へ書く (的, 書く中身) の並び（推し量り）。中身の見えない書き込みは中身を空にする。"""
    out = []
    segs = _segments(cmd)
    for k, (prev, seg, bodies) in enumerate(segs):
        prog = _prog(seg)
        own = "\n".join(bodies + ([seg] if prog in _PRINTERS else []))
        for m in _REDIRECT.finditer(seg):
            out.append((m.group(1), own))
        for m in _TEE.finditer(seg):
            fed = ""
            if prev == "|" and k:
                p_seg, p_bodies = segs[k - 1][1], segs[k - 1][2]
                fed = "\n".join(p_bodies + ([p_seg] if _prog(p_seg) in _PRINTERS else []))
            out += [(t, fed) for t in m.group(2).split()]
        for m in _INPLACE.finditer(seg + "\n"):
            out.append((m.group(1), seg))
    return [(t.strip("'\""), c) for t, c in out if t.strip("'\"") not in ("/dev/null", "-")]


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
