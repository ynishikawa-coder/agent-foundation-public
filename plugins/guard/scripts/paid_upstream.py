"""PreToolUse — 試験から有料の上流（AI の API など）へ直接つながる線を書く手を止める。

意図: 費用も壊れ物として守り、試験の中で本物の AI の API へつなぐ線を書く時に止める。
課題: 開発中の自動試験が、本物の AI の API を叩き続けて費用の大半を占めた実測がある。
原因: データを壊す書き込みは全部塞いでいたのに、読み取り（AI に読ませる口）だけ本物を通していた。

止める: 試験らしい path（tests/・e2e/・spec/・__tests__/・test_*.py・*.test.js …）へ書く中身に、
  有料の上流の鍵名か公式のエンドポイントが現れた時。
逃げ道: 中身に PAID_UPSTREAM_GUARD の宣言を書く（＝環境変数 1 本で本物へ切り替える共通の関所を通す宣言。既定は録画の再生か偽物）。
  宣言は決まった形だけ数える: 行の頭の注記が印で始まる行（`# PAID_UPSTREAM_GUARD`・`// PAID_UPSTREAM_GUARD: …`）か、
  その環境変数を読む式（`os.environ.get("PAID_UPSTREAM_GUARD")`・`process.env.PAID_UPSTREAM_GUARD` 等）。
  文字列の中・注記の文の途中に印の字が在るだけでは数えない（どこかに在るだけで file 全体を見逃さない）。

見る口: Write / Edit / MultiEdit / NotebookEdit と、Bash で試験らしい path へ書く形（`>`・`>>` のリダイレクト・
  `tee`・`sed -i`／`perl -i` の的）。Bash は命令の文全体（heredoc の中身を含む）に印があるかを見る。
射程の外（正直に書く）: 自分のサーバを経た中継（例: 手元のサーバが本物の鍵で AI へ中継する）は見えない。
  Bash でも、書く中身が命令の外にある形（cp・mv・別の script の中で書く・python -c の中の open）は見えない。
判定できない時は通す（1 つの不具合で書き込みを止めない）。
"""
from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import skill_values as SV  # noqa: E402  値の表の当て方の 1 本の口（土台の skill-values/ への symlink）

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
# 宣言の決まった形: 行の頭の注記が印で始まる行／その環境変数を読む式（関所そのもの）
GUARD_DECL = re.compile(
    r"^[ \t]*(?:#|//|--|/\*|\*|;|<!--)[ \t]*" + GUARD_MARKER + r"(?:[ \t]*(?:$|[:：—\-(（*]))"
    r"|(?:environ(?:\.get)?\s*[\[(]\s*|getenv\s*\(\s*|Getenv\s*\(\s*|env\.get\s*\(\s*|ENV\s*\[\s*)['\"]"
    + GUARD_MARKER + r"['\"]"
    r"|process\.env(?:\.|\[\s*['\"])" + GUARD_MARKER + r"\b"
    r"|\$\{?" + GUARD_MARKER + r"\b",
    re.M)


def declared(text):
    """印が決まった形（行の頭の注記・環境変数を読む式）で在るか。"""
    return bool(GUARD_DECL.search(text or ""))
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
        "  ② 本物を通す線が本当に要るなら、環境変数 1 本で切り替える共通の関所を通し、この file に `# {}` の行（行の頭の注記）を書く\n"
        "  ③ 手元のサーバが本物の鍵で中継していないかも、その行を引用して確かめる（この見張りからは見えない）"
    ).format(path, " / ".join(hits), GUARD_MARKER)


# Bash で file へ書く的: リダイレクト（> と >>・2> などの数字つきや >& は除く）・tee・sed -i／perl -i の最後の語
_REDIRECT = re.compile(r"(?<![0-9&>])>>?\s*(?!&)([^\s;&|<>()]+)")
_TEE = re.compile(r"\btee\b((?:\s+-[a-zA-Z]+)*)((?:\s+[^\s;&|<>()-][^\s;&|<>()]*)+)")
_INPLACE = re.compile(r"\b(?:sed|perl)\s+[^;&|]*?-i\S*[^;&|]*?\s([^\s;&|<>()]+)\s*(?:$|[;&|])", re.M)


def bash_targets(cmd):
    """Bash の命令が書く file の path の並び（推し量り）。"""
    out = [m.group(1) for m in _REDIRECT.finditer(cmd)]
    for m in _TEE.finditer(cmd):
        out += m.group(2).split()
    out += [m.group(1) for m in _INPLACE.finditer(cmd)]
    return [t.strip("'\"") for t in out if t.strip("'\"") not in ("/dev/null", "-")]


def check_bash(data, vals):
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str) or declared(cmd):
        return ""
    tests = [t for t in bash_targets(cmd) if TEST_PATH_RE.search(t.replace(os.sep, "/"))]
    if not tests:
        return ""
    hits = SV.words_in(list(PAID_MARKERS) + list(vals.get("paid_markers_extra") or []), cmd)
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
    if not body or declared(body):
        return ""
    hits = SV.words_in(list(PAID_MARKERS) + list(vals.get("paid_markers_extra") or []), body)
    return reason(path, hits) if hits else ""
