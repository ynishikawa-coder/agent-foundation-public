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


class Seg(list):
    """段の語の並び。prefixed＝前に代入（X=1）・env・sudo などの包みが付いていた（読むだけと証せない）。"""
    prefixed = False


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
    out = Seg(seg[i:])
    out.prefixed = i > 0
    return out


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


# ── 網と読むだけの見分け（守りは網を既定にし、読み手は「何も走らせない」と証せた時に通す側にだけ使う）──
# なぜ: 読み手が段の頭を知っている形の表で決めると、表に無い形（if/then・!・coproc・timeout -s・env -u・
#   echo … | bash・perl -e・ssh・find -exec など）を「ふつうの命令」と返し、守りが黙って通した（PR #81 のレビュー）。
#   形の表は必ず漏れる。だから守りは「危ない語が命令のどこかに在る」を既定で止め、読み手が全部の段を
#   「読むだけの命令」と証せた時だけ通す。知らない形は証せないので止まる。
_SPLIT = re.compile(r"[\s;|&()<>{}`$=,\[\]]+")
# 読むだけと証す正本: 命令の名ごとに「読むだけと分かっている option の集合」を持つ。名だけでは決めない
#   （名が読むだけでも、option・設定・前の代入で別の命令を走らせる・file へ書く形が在る＝PR #91 のレビュー:
#   git -c diff.external=… diff・GIT_EXTERNAL_DIFF=… git diff・git grep -O…・rg --pre・sort --compress-program・
#   sort --output・git diff --output・tree -o）。段の option が 1 つでも集合の外なら証せない（守りは止める側）。
# 形: 名 → (短い旗の字, 値を取る短い旗の字, 長い旗の名, 位置の語の上限〔None＝上限なし〕)
#   ANY＝どの語も出力の字か式で、何も走らせない（echo・printf・test・true・false）。
ANY = None
_S = lambda *names: frozenset(" ".join(names).split())
SAFE = {
    "cat": ("AbeEnstTuv", "", _S("show-all number-nonblank show-ends number squeeze-blank show-tabs show-nonprinting"), None),
    "less": ("NnRSFXiI", "", _S("RAW-CONTROL-CHARS chop-long-lines quit-if-one-screen no-init LINE-NUMBERS"), None),
    "more": ("", "", _S(""), None),
    "head": ("cnqvz0123456789", "cn", _S("lines bytes quiet silent verbose zero-terminated"), None),
    "tail": ("cnqvzfF0123456789", "cn", _S("lines bytes quiet silent verbose zero-terminated follow retry"), None),
    "grep": ("EFGPiyvwxclLoqsbHhnTZzraRIUefmABCdD", "efmABCdD",
             _S("extended-regexp fixed-strings basic-regexp perl-regexp regexp file ignore-case no-ignore-case",
                "invert-match word-regexp line-regexp count color colour files-without-match files-with-matches",
                "max-count only-matching quiet silent no-messages byte-offset with-filename no-filename label",
                "line-number initial-tab null null-data after-context before-context context text binary-files",
                "devices directories exclude exclude-from exclude-dir include recursive dereference-recursive",
                "line-buffered binary"), None),
    "rg": ("eFfiSsvwxclnNoqHIaABCtTgmuLMjr0.", "efABCtTgmMjr",
           _S("regexp file fixed-strings ignore-case case-sensitive smart-case invert-match word-regexp line-regexp",
              "count count-matches files-with-matches files-without-match line-number no-line-number only-matching",
              "quiet with-filename no-filename text after-context before-context context type type-not type-list",
              "glob iglob max-count hidden no-ignore no-ignore-vcs follow files json color heading no-heading",
              "multiline multiline-dotall max-columns replace null sort sortr vimgrep trim column no-messages",
              "unrestricted max-depth pcre2 engine no-config passthru byte-offset"), None),
    "ls": ("aAlhRtrSd1FGcikmnpsuUXCxQqgoLHvT", "IwT",
           _S("all almost-all human-readable recursive reverse color classify directory sort time full-time",
              "group-directories-first inode size si format indicator-style literal quoting-style",
              "numeric-uid-gid dereference ignore hide width"), None),
    "wc": ("clmwL", "", _S("bytes chars lines words max-line-length"), None),
    "file": ("bLhizkNsE", "", _S("brief mime mime-type mime-encoding dereference no-dereference keep-going"), None),
    "stat": ("LftcL", "c", _S("dereference file-system format printf terse"), None),
    "diff": ("uqrNyiwbBEaZtTscpdeUxXCSIW", "UxXCSIW",
             _S("unified brief recursive new-file side-by-side ignore-case ignore-all-space ignore-space-change",
                "ignore-blank-lines text report-identical-files color exclude exclude-from no-dereference",
                "strip-trailing-cr label minimal suppress-common-lines ignore-matching-lines width normal",
                "context show-function-line show-c-function ignore-tab-expansion ignore-trailing-space"), None),
    "cmp": ("blsin", "in", _S("print-bytes verbose quiet silent ignore-initial bytes"), None),
    "comm": ("123z", "", _S("check-order nocheck-order output-delimiter total zero-terminated"), None),
    "sort": ("bdfgiMhnRrVcCsuzkt", "kt",
             _S("ignore-leading-blanks dictionary-order ignore-case general-numeric-sort human-numeric-sort",
                "month-sort numeric-sort random-sort reverse version-sort check stable unique zero-terminated",
                "key field-separator"), None),
    "uniq": ("cdDiuzfsw", "fsw", _S("count repeated all-repeated ignore-case unique zero-terminated group"), 1),
    "cut": ("bcfdsnz", "bcfd", _S("bytes characters fields delimiter only-delimited complement output-delimiter",
                                   "zero-terminated"), None),
    "tr": ("cdsCt", "", _S("complement delete squeeze-repeats truncate-set1"), None),
    "nl": ("bdfhilnsvw", "bdfhilnsvw", _S(""), None),
    "column": ("tsxnec", "sc", _S("table separator"), None),
    "jq": ("rjcnsSeaCMR", "", _S("raw-output join-output compact-output null-input slurp sort-keys exit-status",
                                  "ascii-output color-output monochrome-output tab indent arg argjson slurpfile",
                                  "rawfile args jsonargs raw-input"), None),
    "readlink": ("femnqsvz", "", _S("canonicalize canonicalize-existing canonicalize-missing no-newline quiet",
                                     "silent verbose zero"), None),
    "realpath": ("emLPqsz", "", _S("canonicalize-existing canonicalize-missing logical physical quiet",
                                    "relative-to relative-base strip no-symlinks zero"), None),
    "dirname": ("z", "", _S("zero"), None),
    "basename": ("asz", "s", _S("multiple suffix zero"), None),
    "pwd": ("LP", "", _S(""), None),
    "which": ("a", "", _S(""), None),
    "type": ("afptP", "", _S(""), None),
    "du": ("achsSkmbLHlxd0", "d", _S("all apparent-size summarize human-readable max-depth si total bytes",
                                      "count-links dereference one-file-system null inodes"), None),
    "df": ("ahHiklPTt", "t", _S("all human-readable si inodes local portability print-type type output total"), None),
    "tree": ("adlfiFLIPCnsughDpJrtvU", "LIP", _S("noreport dirsfirst charset gitignore prune du filelimit sort",
                                                    "matchdirs ignore-case"), None),
    "od": ("AjNtvbcdiosxwS", "AjNtwS", _S(""), None),
    "hexdump": ("bcCdoxvn s", "ns", _S(""), None),
    "strings": ("afntedw", "nte", _S("all print-file-name bytes radix encoding"), None),
    "echo": ANY, "printf": ANY, "test": ANY, "[": ANY, "true": ANY, "false": ANY,
}
for _h in ("md5sum", "sha1sum", "sha256sum"):
    SAFE[_h] = ("bctwz", "", _S("binary check tag text zero quiet status strict warn ignore-missing"), None)
SAFE["egrep"] = SAFE["fgrep"] = SAFE["grep"]
SAFE["sed"] = ("nErsuzl", "efl", _S("quiet silent expression file regexp-extended separate unbuffered null-data",
                                       "posix debug sandbox line-length"), None)

# git: 前の option は -C と pager の切りだけ（-c・--git-dir・--work-tree・--exec-path は設定や別の repo の hook を引く）。
#   副命令は読むだけの物だけ（add・commit・fetch は hook・filter・取り込みが走る）。副命令ごとの option も同じ集合で証す。
_GIT_GLOBAL = {"--no-pager": 0, "-P": 0, "--no-optional-locks": 0, "-C": 1}
_DIFF_L = _S("stat numstat shortstat name-only name-status patch no-patch unified raw patch-with-stat summary color",
             "no-color color-words word-diff word-diff-regex ignore-space-change ignore-all-space ignore-blank-lines",
             "ignore-cr-at-eol ignore-space-at-eol find-renames find-copies diff-filter abbrev full-index binary",
             "relative text exit-code quiet cached staged merge-base no-renames histogram patience minimal",
             "diff-algorithm src-prefix dst-prefix no-prefix function-context compact-summary dirstat check",
             "no-ext-diff no-textconv ignore-submodules submodule stat-width inter-hunk-context color-moved anchored")
_LOG_L = _DIFF_L | _S("oneline graph format pretty decorate no-decorate all branches tags remotes reverse follow",
                      "no-merges merges first-parent since until after before author committer grep all-match",
                      "invert-grep regexp-ignore-case max-count skip date abbrev-commit no-abbrev-commit left-right",
                      "cherry-pick cherry-mark cherry boundary ancestry-path simplify-by-decoration topo-order",
                      "date-order author-date-order walk-reflogs source log-size parents children notes no-notes",
                      "encoding max-parents min-parents full-history dense sparse mailmap use-mailmap pickaxe-regex",
                      "pickaxe-all not no-walk do-walk diff-merges cc name-only")
_DIFF_S = "pusMCBDlRazwbWU0123456789"
SAFE_GIT = {
    "log": (_DIFF_S + "nSGLiE", "nSGLUMCBl", _LOG_L, None),
    "show": (_DIFF_S + "nSG", "nSGUMCBl", _LOG_L, None),
    "diff": (_DIFF_S + "SG", "SGUMCBl", _DIFF_L | _S("no-index"), None),
    "status": ("sbuvz", "u", _S("short branch porcelain long verbose untracked-files ignore-submodules ignored",
                                "column no-column ahead-behind no-ahead-behind renames no-renames show-stash"), None),
    "grep": ("ivwacEFGPlLnhHorqzIefABCWp", "efABCm",
             _S("ignore-case invert-match word-regexp text count extended-regexp fixed-strings basic-regexp",
                "perl-regexp files-with-matches files-without-match line-number column untracked cached",
                "max-depth heading break show-function function-context and or not all-match quiet null",
                "only-matching max-count exclude-standard no-exclude-standard full-name color no-color",
                "after-context before-context context regexp file"), None),
    "blame": ("lstnfpLMCwecS", "LMCS", _S("porcelain line-porcelain incremental show-name show-number show-email",
                                           "root reverse first-parent date abbrev color-lines color-by-age",
                                           "ignore-rev ignore-revs-file"), None),
    "ls-files": ("cdmosiktuvfzxX", "xX", _S("cached deleted modified others stage unmerged killed ignored directory",
                                            "no-empty-directory exclude-standard exclude exclude-from error-unmatch",
                                            "full-name abbrev eol deduplicate format sparse"), None),
    "rev-parse": ("q", "", _S("verify short abbrev-ref symbolic-full-name show-toplevel git-dir git-common-dir",
                              "is-inside-work-tree is-inside-git-dir is-bare-repository show-prefix show-cdup",
                              "absolute-git-dir quiet default all branches tags remotes sq not revs-only no-revs",
                              "flags no-flags symbolic path-format git-path since until"), None),
    "describe": ("", "", _S("tags all always abbrev long contains exact-match match exclude first-parent",
                           "candidates"), None),
    "shortlog": ("nsec", "", _LOG_L | _S("numbered summary email committer group"), None),
    "cat-file": ("tspe", "", _S("batch batch-check batch-all-objects follow-symlinks buffer unordered"), None),
    "ls-tree": ("dtrlz", "", _S("name-only name-status full-name full-tree abbrev long object-only format"), None),
    "merge-base": ("a", "", _S("all octopus independent is-ancestor fork-point"), None),
}
_BRANCH_LIST = {"-a", "-r", "-v", "-vv", "-l", "--list", "--all", "--remotes", "--show-current", "--no-color"}


def _opts_safe(words, spec):
    """words（命令の名の後の語）の option が全部 spec の集合に入るか。位置の語は spec の上限まで。"""
    if spec is ANY:
        return True
    short, short_val, long_names, max_pos = spec
    pos, i, ended = 0, 0, False
    while i < len(words):
        t = words[i].text
        if ended or t == "-" or not t.startswith("-"):
            pos += 1
        elif t == "--":
            ended = True
        elif t.startswith("--"):
            if t[2:].split("=", 1)[0] not in long_names:
                return False
        else:
            for j, ch in enumerate(t[1:], 1):
                if ch not in short:
                    return False
                if ch in short_val:
                    if j == len(t) - 1:
                        i += 1           # 値は次の語
                    break                # 値は残りの字
        i += 1
    return max_pos is None or pos <= max_pos


def _flat(s):
    return s.replace("\\\n", "").replace("'", "").replace('"', "").replace("\\", "")


def mentions(cmd):
    """命令の中の語の集合: 引用符・逃がしを外した字を割った語 ∪ 読み手が変数を解いた語（とその中を割った語）。
    位置を問わない網（字を割る・変数に置く・包む・段の頭が知らない形でも、語は網に掛かる）。"""
    out = set()
    if not isinstance(cmd, str):
        return out
    out.update(t for t in _SPLIT.split(_flat(cmd)) if t)
    for seg in read(cmd).segments:
        for w in seg:
            out.add(w.text)
            out.update(t for t in _SPLIT.split(_flat(w.text)) if t)
    # 短い旗に付けた値（-O'…'・-e…）: 旗の字の後ろに語が付くので、どこから値かを決めず後ろの全部を網に入れる
    out.update(t[k:] for t in list(out) if t.startswith("-") and not t.startswith("--") for k in range(2, min(len(t), 66)))
    out.update(os.path.basename(t) for t in list(out))
    return out


def _seg_inert(words):
    if not words or getattr(words, "prefixed", False) or any(w.opaque for w in words):
        return False
    prog = prog_name(words)
    if words[0].text != prog and "/" in words[0].text:
        return False   # 道を付けた名（./cat など）は同じ名の別の物かもしれない
    if prog == "git":
        i = 1
        while i < len(words) and words[i].text.startswith("-"):
            if words[i].text not in _GIT_GLOBAL:
                return False
            i += 1 + _GIT_GLOBAL[words[i].text]
        if i >= len(words):
            return False
        sub, rest = words[i].text, words[i + 1:]
        if sub == "branch":   # 名だけ並べる形だけが読むだけ（-d・-D・-m・-f・名を付けて作る形は書く）
            return all(w.text in _BRANCH_LIST for w in rest)
        return sub in SAFE_GIT and _opts_safe(rest, SAFE_GIT[sub])
    if prog not in SAFE:
        return False
    if prog == "sed" and any(re.search(r"(^|[;}])\s*[ew]\b|/[ew]\s*$", w.text) for w in words[1:]):
        return False   # sed の式の e（命令を走らせる）・w（file へ書く）
    return _opts_safe(words[1:], SAFE[prog])


def inert(cmd):
    """命令の全部の段が、読み手の読める形で「何も走らせない・消さない・書き換えない読むだけの命令」の時だけ True。
    読めない所（$(…)・解けない変数・字句が割れない）・表に無い頭・リダイレクトで file へ書く形は False（＝守りは止める側）。"""
    if not isinstance(cmd, str):
        return False
    r = read(cmd)
    if r.opaque or not r.segments:
        return False
    if re.search(r"(?<![<>&\d])\d*>{1,2}(?!&)\s*(?!/dev/null\b)[^\s&|;]", _flat(_strip_heredocs(cmd))):
        return False   # file へ書く
    return all(_seg_inert(seg) for seg in r.segments)
