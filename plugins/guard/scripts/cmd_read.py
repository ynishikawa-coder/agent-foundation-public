"""Bash の命令を、守りが照らす前に 1 つの形（段ごとの語の並び）へ読む読み手。

なぜ在るか: 守りが命令の字の並び（`check_spec_doc.py --lock` の字・`dropdb` の字）を正規表現で探すと、
  引用符で字を割る（"che"'ck'）・変数に置く（G=…; $G）・略す（--loc）・`bash -c "…"` に包む形が通った。
  守りは字を見ず、シェルが実際に渡す語の並びを見る。読めない所（$(…)・`…`・解けない変数）は「読めない」の印を付けて返し、
  守りはそこを止める側に倒す（AI の呼び出しだけを止める＝人の手の命令は見ない）。

返す物: Reading（segments＝段ごとの Word の並び・opaque＝どこかに読めない所が在るか）。
  Word.text は引用符を外して変数を解いた語。Word.opaque は、その語に解けない展開が残る時 True。
  前に付く包み（env X=1・sudo・command・exec・nohup・time・nice・timeout N・xargs）は外し、包みの中の命令を段にする。
  bash/sh/zsh/dash -c と eval の文字は、もう 1 度読んで段に足す（入れ子は DEPTH 段まで・越えたら読めない）。
  heredoc の中身は語に入れない（命令でない）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# 見張りでなく見張りが使う読み手（どの出来事でも回らない＝入口の guard.py は空の宣言を飛ばす）
HOOKS = {}

DEPTH = 4
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
WRAPPERS = {"sudo", "command", "exec", "nohup", "time", "nice", "builtin", "stdbuf", "doas", "caffeinate"}
WITH_ARG = {"timeout": 1, "nice": 0}
SUDO_ARG = {"-u", "-g", "-h", "-p", "-C", "-U", "-D", "-r", "-t", "-T"}
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
OPS = {";", "&&", "||", "|", "&", "|&", "(", ")", "{", "}", "\n"}


@dataclass
class Word:
    text: str
    opaque: bool = False


@dataclass
class Reading:
    segments: list = field(default_factory=list)   # list[list[Word]]
    opaque: bool = False

    def argvs(self):
        return [[w.text for w in seg] for seg in self.segments]


def _strip_heredocs(cmd):
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        tags = [m.group(2) for m in _HEREDOC.finditer(line)]
        i += 1
        for tag in tags:
            while i < len(lines) and lines[i].strip().lstrip("\t") != tag:
                i += 1
            i += 1
    return "\n".join(out)


REDIR = re.compile(r"\d*(?:&>>?|>>|>&|<&|<<<|<<-?|>\||<>|>|<)")


def _balanced(s, i, open_, close):
    """s[i] が open_ の時、対になる close の位置（引用符の中は数えない）。無ければ -1。"""
    depth, q = 0, ""
    while i < len(s):
        c = s[i]
        if q:
            if c == "\\" and q == '"':
                i += 2
                continue
            if c == q:
                q = ""
        elif c in "'\"":
            q = c
        elif c == "\\":
            i += 2
            continue
        elif s.startswith(open_, i):
            depth += 1
            i += len(open_)
            continue
        elif c == close:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _tokens(s):
    """シェルの字句: [(kind, raw, parts)]。kind は word / op / redir。word の parts は [(字, 引用の種類)]。
    $(…)・`…` は ("sub", 中身) の部分にする（中の命令は別に読む）。読めない（引用符が閉じない）時は None。"""
    out, i, n = [], 0, len(s)
    parts, cur_open = [], False

    def flush():
        nonlocal parts, cur_open
        if cur_open:
            out.append(("word", parts))
        parts, cur_open = [], False

    while i < n:
        c = s[i]
        if c in " \t\r":
            flush()
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if s[i + 1] == "\n":
                i += 2
                continue
            parts.append((s[i + 1], "esc"))
            cur_open = True
            i += 2
            continue
        if c == "#" and not cur_open:
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        m = REDIR.match(s, i)
        if m and (not cur_open or s[i] in "<>&"):
            if cur_open and m.group(0)[0].isdigit():
                pass
            else:
                flush()
                out.append(("redir", m.group(0)))
                i = m.end()
                continue
        if s.startswith(("&&", "||", "|&", ";;"), i):
            flush()
            out.append(("op", s[i:i + 2]))
            i += 2
            continue
        if c in ";&|\n(){}" and not (c in "{}" and cur_open):
            if c in "{}" and i + 1 < n and s[i + 1] not in " \t\n;":
                parts.append((c, "plain"))
                cur_open = True
                i += 1
                continue
            flush()
            out.append(("op", c))
            i += 1
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return None
            parts.append((s[i + 1:j], "single"))
            cur_open = True
            i = j + 1
            continue
        if c == '"':
            j, buf = i + 1, []
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n and s[j + 1] in '"\\$`\n':
                    buf.append(("\\" + s[j + 1]) if s[j + 1] == "$" else s[j + 1])
                    j += 2
                    continue
                if s.startswith("$(", j):
                    k = _balanced(s, j + 1, "(", ")")
                    if k < 0:
                        return None
                    if buf:
                        parts.append(("".join(buf), "double"))
                        buf = []
                    parts.append((s[j + 2:k], "sub"))
                    j = k + 1
                    continue
                if s[j] == "`":
                    k = s.find("`", j + 1)
                    if k < 0:
                        return None
                    if buf:
                        parts.append(("".join(buf), "double"))
                        buf = []
                    parts.append((s[j + 1:k], "sub"))
                    j = k + 1
                    continue
                buf.append(s[j])
                j += 1
            if j >= n:
                return None
            parts.append(("".join(buf), "double"))
            cur_open = True
            i = j + 1
            continue
        if s.startswith("$(", i):
            k = _balanced(s, i + 1, "(", ")")
            if k < 0:
                return None
            parts.append((s[i + 2:k], "sub"))
            cur_open = True
            i = k + 1
            continue
        if c == "`":
            k = s.find("`", i + 1)
            if k < 0:
                return None
            parts.append((s[i + 1:k], "sub"))
            cur_open = True
            i = k + 1
            continue
        if s.startswith("${", i):
            k = s.find("}", i)
            if k < 0:
                return None
            parts.append((s[i:k + 1], "plain"))
            cur_open = True
            i = k + 1
            continue
        parts.append((c, "plain"))
        cur_open = True
        i += 1
    flush()
    return out


def _cook(parts, env, subs):
    """部分の並びを 1 語へ。変数を解き、解けない展開・$(…) があれば opaque。$(…) の中身は subs へ足す。"""
    buf, opaque = [], False
    for frag, kind in parts:
        if kind in ("single", "esc"):
            buf.append(frag.replace("$", "\x00"))      # 引用・逃がしの中の $ は展開しない
        elif kind == "sub":
            subs.append(frag)
            opaque = True
            buf.append("\x01" + frag.replace("$", "\x00") + "\x02")
        else:
            buf.append(frag.replace("\\$", "\x00"))
    joined = "".join(buf)

    def rep(m):
        nonlocal opaque
        k = m.group(1) or m.group(2)
        if k in env:
            return env[k].replace("$", "\x00")
        opaque = True
        return m.group(0)

    cooked = _VAR.sub(rep, joined)
    if re.search(r"\$\{[^}]*\}|\$[@*#?!$0-9-]", cooked):
        opaque = True
    return Word(cooked.replace("\x00", "$").replace("\x01", "$(").replace("\x02", ")"), opaque)


def _unwrap(seg):
    """前に付く包み（env X=1・sudo・timeout 5 など）を外した語の並び。"""
    i = 0
    while i < len(seg):
        t = os.path.basename(seg[i].text)
        if _ASSIGN.match(seg[i].text):
            i += 1
            continue
        if t == "env":
            i += 1
            while i < len(seg) and (seg[i].text.startswith("-") or _ASSIGN.match(seg[i].text)):
                i += 1
            continue
        if t in WRAPPERS or t in WITH_ARG:
            i += 1
            while i < len(seg) and seg[i].text.startswith("-"):
                i += 2 if (t in ("sudo", "doas") and seg[i].text in SUDO_ARG) else 1
            i += WITH_ARG.get(t, 0)
            continue
        if t == "xargs":
            i += 1
            while i < len(seg) and seg[i].text.startswith("-"):
                i += 1
            continue
        break
    return seg[i:]


def read(cmd, env=None, depth=0):
    """命令の文を Reading に読む。"""
    out = Reading()
    if not isinstance(cmd, str) or depth > DEPTH:
        out.opaque = True
        return out
    env = dict(env or {})
    toks = _tokens(_strip_heredocs(cmd))
    if toks is None:
        out.opaque = True
        toks = [("word", [(t, "single")]) for t in re.split(r"\s+", cmd) if t]
    seg, subs, skip = [], [], False

    def close():
        nonlocal seg
        if seg:
            words = _unwrap(seg)
            if not words:
                for w in seg:
                    m = _ASSIGN.match(w.text)
                    if m:
                        if w.opaque:
                            env.pop(m.group(1), None)
                        else:
                            env[m.group(1)] = m.group(2)
            else:
                out.segments.append(words)
                _inner(words, env, depth, out)
        seg = []

    for kind, val in toks:
        if kind == "op":
            close()
            continue
        if kind == "redir":
            skip = True
            continue
        w = _cook(val, env, subs)
        if skip:
            skip = False
            if w.opaque:
                out.opaque = True
            continue
        if w.opaque:
            out.opaque = True
        seg.append(w)
    close()
    for sub in subs:
        inner = read(sub, env, depth + 1)
        out.segments.extend(inner.segments)
    return out


def _inner(words, env, depth, out):
    """bash -c "…"・eval "…" の中の命令を、もう 1 度読んで段に足す。"""
    prog = os.path.basename(words[0].text)
    code = None
    if prog in SHELLS:
        for i, w in enumerate(words[1:], 1):
            if w.text.startswith("-") and "c" in w.text.lstrip("-") and not w.text.startswith("--"):
                code = words[i + 1] if i + 1 < len(words) else None
                break
    elif prog == "eval":
        code = Word(" ".join(w.text for w in words[1:]), any(w.opaque for w in words[1:]))
    if code is None:
        return
    inner = read(code.text, env, depth + 1)
    out.segments.extend(inner.segments)
    if inner.opaque or code.opaque:
        out.opaque = True


def abbrev_of(word, long_opt, min_len=3):
    """word が long_opt（例 --lock）か、argparse が受ける略し（--l・--lo・--loc）か、--lock=… か。"""
    w = word.split("=", 1)[0]
    return w.startswith("--") and len(w) >= min_len and long_opt.startswith(w)


def prog_name(words):
    return os.path.basename(words[0].text) if words else ""
