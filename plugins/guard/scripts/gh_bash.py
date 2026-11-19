"""PreToolUse — Bash から GitHub へ PR・issue の文（題・本文・コメント・レビュー・判定）を書き込む命令を止め、MCP の道具へ回す。

なぜ在るか: PR の文の見張り（pr_text）は GitHub の MCP の道具の入力だけを見る。判定の名乗りの照らし（checker の verdict_form）も
その見張りの中から呼ばれる。ところが Bash の `gh pr comment`・`gh api`・curl で書けば、同じ文がどの照らしも通らずに PR へ載る
（書いた窓の助手が作った窓の id で green の判定を出す道が残っていた）。照らしの入口を 1 つ足して追いかけると、入口が増えるたびに
穴が開く。なので、PR・issue の文を GitHub へ出す道を MCP の道具の 1 本に絞り、Bash の書き込みは出す前に止める
（オーナー同意 2026-11-19: 文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい。
同じ文を別の口から出す道を閉じるだけで、止める物は増やしていない）。止まるのは AI の Bash の呼び出しだけ。人の操作は止めない。

止める形（命令の語に分けて見る。`bash -c`・`sh -c`・`eval` の中の字も同じに見る）:
  gh   … `gh pr|issue` の comment・review・create・edit・merge・close・reopen・ready、`gh api` の書き込み
         （-X/--method が GET・HEAD 以外、または -X 無しで -f/-F/--field/--raw-field/--input を渡す＝gh は POST にする）
  HTTP … curl・wget・http（httpie）で api.github.com か uploads.github.com へ GET・HEAD 以外を送る
         （-X/--request、-d/--data*/--json/-F/--form/-T、wget の --post-data・--method）
読み切れない形（引用の閉じ忘れ等）は、命令の字に gh か api.github.com と書き込みの印が在れば止める側に倒す。
通す物: 読むだけの gh（`gh pr view`・`gh api -X GET search/...`・`gh pr diff`）と git（Bash の git push の commit の説明は
  ここでは見ない＝CI の公開の検査が出した後に拾う）。gh の release・gist・repo edit など PR・issue の外の文も見ない（原因の台帳に残す）。
射程の天井: python・node の中から HTTP で書く形は命令の字に出ないので見えない（原因の台帳に残す・レビューの見る点で見る）。
"""
from __future__ import annotations

import re
import shlex

HOOKS = {"pre": "check"}

GH_WRITE = {
    "pr": {"comment", "review", "create", "edit", "merge", "close", "reopen", "ready"},
    "issue": {"comment", "create", "edit", "close", "reopen"},
}
READ_METHODS = {"GET", "HEAD"}
GH_API_FIELDS = {"-f", "-F", "--field", "--raw-field", "--input"}
HOSTS = re.compile(r"(?:^|[/@.])(?:api|uploads)\.github\.com\b", re.I)
CURL_DATA = re.compile(r"^(?:-d|--data(?:-\w+)?|--json|-F|--form(?:-string)?|-T|--upload-file|--post-data|--post-file)(?:=|$)")
CURL_DATA_SHORT = re.compile(r"^-[A-Za-z]*[dFT]")         # -d'..'・-sd 等の詰めた短い旗
SHELLS = {"bash", "sh", "zsh", "dash"}
SEP = {";", "&&", "||", "|", "&", "\n", "(", ")"}
ROUGH = re.compile(r"\bgh\b[\s\S]*\b(?:comment|review|create|edit|merge|close|reopen|ready|api)\b|api\.github\.com", re.I)
ROUGH_WRITE = re.compile(r"\b(?:comment|review|create|edit|merge|close|reopen|ready)\b|-X\s*(?!GET|HEAD)\w|--method"
                         r"|\s-[dfFT]\b|--data|--json|--field|--raw-field|--input|--form", re.I)


def _segments(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace_split = True
    lex.commenters = ""
    seg = []
    for tok in lex:
        if tok in SEP or set(tok) <= set(";&|()\n"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def _base(tok):
    return tok.rsplit("/", 1)[-1]


def _strip_prefix(seg):
    """前置き（VAR=値・env・command・sudo・time・nohup）を外す。"""
    i = 0
    while i < len(seg):
        t = seg[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) or _base(t) in ("env", "command", "sudo", "time", "nohup", "exec", "xargs"):
            i += 1
            continue
        if t.startswith("-") and i > 0 and _base(seg[i - 1]) in ("env", "sudo", "xargs"):
            i += 1
            continue
        break
    return seg[i:]


def _method(args, flags=("-X", "--method", "--request")):
    for i, a in enumerate(args):
        for f in flags:
            if a == f and i + 1 < len(args):
                return args[i + 1].upper()
            if a.startswith(f + "=") or (f.startswith("-X") and a.startswith("-X") and len(a) > 2 and not a.startswith("--")):
                return a.split("=", 1)[-1].upper() if "=" in a else a[2:].upper()
    return ""


def gh_write(args):
    """gh の引数（gh の後ろ）が PR・issue へ書くなら、その形の名。"""
    words, skip = [], False
    for x in args:
        if skip:
            skip = False
        elif x in ("-R", "--repo", "--hostname"):
            skip = True               # 値を取る全体の旗（その値は語に数えない）
        elif not x.startswith("-"):
            words.append(x)
    if len(words) >= 2 and words[0] in GH_WRITE and words[1] in GH_WRITE[words[0]]:
        return "gh %s %s" % (words[0], words[1])
    if words and words[0] == "api":
        if len(words) > 1 and words[1] == "graphql":
            # graphql は読むのも POST。書くのは mutation だけ
            return "gh api graphql（mutation）" if any(re.search(r"\bmutation\b", x) for x in args) else ""
        m = _method(args)
        if m and m not in READ_METHODS:
            return "gh api -X %s" % m
        if not m and any(x in GH_API_FIELDS or any(x.startswith(f + "=") for f in GH_API_FIELDS if f.startswith("--"))
                         for x in args):
            return "gh api（-f/-F/--input で POST）"
    return ""


def http_write(prog, args):
    if not any(HOSTS.search(x) for x in args):
        return ""
    if prog == "wget":
        m = _method(args, ("--method",))
        if (m and m not in READ_METHODS) or any(CURL_DATA.match(x) for x in args):
            return "wget（GitHub の API へ書き込み）"
        return ""
    m = _method(args)
    if m and m not in READ_METHODS:
        return "%s -X %s（GitHub の API）" % (prog, m)
    if not m and any(CURL_DATA.match(x) or CURL_DATA_SHORT.match(x) for x in args):
        return "%s（GitHub の API へデータを送る＝POST）" % prog
    if prog == "http" and any(re.match(r"^(POST|PATCH|PUT|DELETE)$", x, re.I) for x in args):
        return "http（GitHub の API へ書き込み）"
    return ""


def writes(cmd, depth=0):
    """命令の字の中の、GitHub へ PR・issue の文を書く形の並び。読み切れなければ字で粗く見る（止める側に倒す）。"""
    if depth > 4:
        return ["入れ子が深くて読み切れない命令"] if ROUGH.search(cmd) else []
    try:
        segs = list(_segments(cmd))
    except ValueError:
        return ["読み切れない命令の形（%s）" % ROUGH.search(cmd).group(0)[:40]] \
            if ROUGH.search(cmd) and ROUGH_WRITE.search(cmd) else []
    out = []
    for seg in segs:
        seg = _strip_prefix(seg)
        if not seg:
            continue
        prog, args = _base(seg[0]), seg[1:]
        if prog in SHELLS and "-c" in args[:-1]:
            out += writes(args[args.index("-c") + 1], depth + 1)
        elif prog == "eval":
            out += writes(" ".join(args), depth + 1)
        elif prog == "gh":
            w = gh_write(args)
            if w:
                out.append(w)
        elif prog in ("curl", "wget", "http", "https"):
            w = http_write(prog, args)
            if w:
                out.append(w)
        # 置き換え $(...)・`...` の中も見る
        for a in args:
            for inner in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", a):
                out += writes(inner[0] or inner[1], depth + 1)
    return out


def check(data, vals):
    if data.get("tool_name") != "Bash":
        return ""
    ti = data.get("tool_input") or {}
    cmd = ti.get("command") if isinstance(ti, dict) else ""
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    hits = writes(cmd)
    if not hits:
        return ""
    return ("[guard] Bash から GitHub へ PR・issue の文を書き込む命令なので、出す前に止めた（%s）。\n"
            "PR の題・本文・コメント・レビュー・判定は、GitHub の MCP の道具（create_pull_request・update_pull_request・"
            "add_issue_comment・pull_request_review_write など）で出す。その道だけを PR の文の見張りが照らす"
            "（判定の名乗り・整地の欄・窓の id・公開の repo に置かない物）。Bash の gh・curl はその照らしを通らない。\n"
            "直し方: 同じ文を MCP の道具で出し直す。読むだけなら gh は `gh api -X GET …`・`gh pr view` で通る。"
            "細目は skill `guard:guard-rules`。" % "・".join(dict.fromkeys(hits)))
