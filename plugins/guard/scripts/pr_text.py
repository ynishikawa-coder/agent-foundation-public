"""PreToolUse — PR の題・本文と、PR・issue へのコメントと commit の説明を、GitHub へ出す前に照らす。崩れていれば AI だけを止めて書き直させる。

なぜ在るか: レビューの判定の形・PR 本文の整地の 4 欄・人が読む文の言葉・公開の repo に置かない物は、決まりと道具はあるのに
AI が自分で回すか、出した後に CI やレビューが拾うだけだった。そのため、形の崩れた判定が合流の材料になり、欄の欠けた PR 本文が
レビューで初めて見つかり、公開の repo の PR 本文に置かない語が出て GitHub の編集の履歴に残った（オーナー同意 2026-11-19:
決まりが文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい）。
止まるのは AI の道具の呼び出しだけ（文はまだ GitHub に出ていない）。人の操作は何も止めない。

見る道（GitHub へ文を出す道は 2 つ。どちらも同じ照らしを当てる）:
  MCP の道具 … 名の末尾（MCP の server の名は問わない）で見分ける。
    PR     … create_pull_request・update_pull_request（題・本文）
    コメント … add_issue_comment・update_issue_comment・add_reply_to_pull_request_comment・pull_request_review_write・
               add_comment_to_pending_review（本文）
    issue  … issue_write（題・本文）
    commit … merge_pull_request（commit_title・commit_message）・push_files・create_or_update_file・delete_file（message）
    並べていない MCP の道具でも、入力に owner・repo と題か本文が在れば GitHub へ出す文として言葉と公開を照らす。
  Bash … 命令の字を探さず、読み手（cmd_read）が解いた段ごとの語で読む: gh pr|issue create・edit・comment・close・reopen、
    gh pr review・merge、gh release create・edit、gh api（-f/-F の題・本文・message の欄・--input の JSON・graphql の欄）、
    git commit（-m・-F）。--body-file・-F の file は読む。`$(cat <<'EOF' … EOF)` と標準入力の heredoc は中身を読む。
    読めない本文（$(…)・解けない変数・パイプの標準入力・--fill・--template）は止める（照らせない文は出さない）。
照らす物（見分けは正本を直に読む・呼ぶ。ここに決まりを写さない）:
  verdict … （材料: 出す先の PR の先端・PR 本文の頭の `書いた窓:`・PR の commit の `Claude-Session:` を gh で引き、
            判定を出す窓の実物の id〔窓の環境の CLAUDE_CODE_REMOTE_SESSION_ID〕と一緒に渡す。引けなければ止める）
            GitHub のレビューの承認・変更の要求（event・--approve・--request-changes）は形の上で判定＝本文が何でも照らす。
            コメントの本文は字を 1 つの形へ寄せて（全角→半角・強調の印を外す）、`レビューした窓: … 判定: green|red` の行・
            verdict の見出し・判定か verdict の欄が green|red だけの行の どれかが在れば判定と見なす。
            判定なら checker の `scripts/verdict_form.py` をそのまま呼ぶ。赤なら止める。道具が見つからない・壊れた時も止める
  cleanup … PR の本文（本文を渡す時だけ）に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し
            （`## 1.`〜`## 4.`。見出しの名は雛形から読む）が全部在り、各見出しの下の中身が空でない（空行・見出し・`**欄**:` の札・
            `〔…〕`・`<…>`・`-`・TBD だけなら無いと同じ）事と、雛形の `〔…〕` が残っていない事。整地の要らない PR
            （振る舞いを変えない: 誤字・記録だけ・版だけ等）は本文に `整地: 不要（<訳>）` の 1 行を書く（訳の中身が同じ空の読み方で
            空なら、書いていないと同じ。訳の良し悪しはレビューが照らす）
  words   … GitHub へ出す全ての文（PR・コメント・issue・commit）に、窓の id（`session_01…`）がそのまま出ていない事。
            数えないのは: 本文の頭の欄の塊（最初の空行まで）の、値が窓の id だけの欄（`親窓: <id>`・`書いた窓: <id>`）・
            判定の形が id を置く欄（verdict_form の form_id_lines）・コードの囲み・`…` の字・URL の中
  public  … 出す先の repo が公開か（GitHub の repo の visibility を gh で引く。引けない時だけ、窓の取り出しの workflow が
            action public-guard を呼ぶか／値の表 public_repos_extra で見る）。公開なら、文を `public-guard/guard.py --text` に渡す
            （置かない語の表は取り出しの workflow の deny-words-file）。当たれば止める。検査が見つからない・壊れた時も止める
誤って止めた時: 値の表 pr_cleanup_exempt_repos・pr_words_exempt_repos（owner/repo に当てる正規表現）で repo ごとに外す。
判定の形と公開の検査は外す口を持たない（直すのは文の方・判定の形の決まりは review-pr の SKILL.md が正本）。
値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import unicodedata

import cmd_read as R
import guard_common as G

HOOKS = {"pre": "check"}

TIMEOUT = 30
SHOWN = 12
FILE_LIMIT = 1_000_000

PR_TOOLS = ("create_pull_request", "update_pull_request")
COMMENT_TOOLS = ("add_issue_comment", "update_issue_comment", "add_reply_to_pull_request_comment",
                 "pull_request_review_write", "add_comment_to_pending_review")
ISSUE_TOOLS = ("issue_write",)
COMMIT_TOOLS = ("merge_pull_request", "push_files", "create_or_update_file", "delete_file")
# 文の欄（MCP の入力の鍵・gh api の欄の名）→ どこの文か
WHERE = {
    "pr": {"title": "PR の題", "body": "PR の本文"},
    "comment": {"title": "コメントの題", "body": "コメント"},
    "issue": {"title": "issue の題", "body": "issue の本文"},
    "commit": {"title": "commit の題", "body": "commit の説明", "commit_title": "commit の題",
               "commit_message": "commit の説明", "message": "commit の説明"},
    "other": {},
}
TEXT_KEYS = ("title", "body", "commit_title", "commit_message", "message")
REVIEW_VERDICT_EVENTS = ("APPROVE", "REQUEST_CHANGES")

VERDICT_FORM = ("checker", os.path.join("scripts", "verdict_form.py"), "AF_VERDICT_FORM")
CLEANUP_TEMPLATE = ("dev-flow", os.path.join("skills", "preimpl-cleanup", "整地受領証.template.md"), "AF_CLEANUP_TEMPLATE")

# 判定の形の印（review-pr の形）。字は照らす前に _flat で 1 つの形へ寄せる（全角→半角・強調の印を外す・小文字）。
# 名乗りの欄と判定が 1 行に揃う行・verdict の見出し・形の 2 つの欄の名（1 行目の「判定」と節の「verdict」）が green|red だけを
# 持つ行。引用（行頭の `>`）の中は、前の判定を引いた返事なので数えない。
VERDICT_LINE = re.compile(r"^[ \t]*レビューした窓\s*:.*判定\s*:\s*(?:green|red)\b", re.M)
VERDICT_HEAD = re.compile(r"^[ \t]*#{1,6}\s*verdict\s*$", re.M)
VERDICT_PAIR = re.compile(r"^[ \t]*(?!>)[^:\n>]{0,30}(?:判定|verdict)[^:\n]{0,30}:\s*(?:green|red)\s*(?:\([^)\n]*\))?\s*$", re.M)
NOT_NEEDED = re.compile(r"^\s*(?:[-*]\s*)?\**整地\**\s*[:：]\s*\**\s*(?:不要|要らない)\s*[（(](.*)[)）]\s*$", re.M)
TEMPLATE_HEAD = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)
HEADING = re.compile(r"^(#{1,6})\s*(.*?)\s*#*\s*$")
PLACEHOLDER = re.compile(r"〔[^〕\n]{4,}〕")
# 欄の中身が空と同じ行（session-watch の手の窓の 4 欄 hand_lack と同じ読み方: 置き場の印だけの行は無いと同じ）。
# 行の頭の箇条の印と `**欄の名**:` の札は外してから見る（札だけの行は中身でない）。
BLANK = re.compile(r"^(?:[-–—…・.。、\s*_`|:：]*|〔[^〕]*〕|<[^>]*>|＜[^＞]*＞|TBD|TODO|未定|未記入|空|\(空\)|（空）)$", re.I)
LABEL = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])(?:\s+|$))?\s*(?:\*\*[^*\n]+\*\*\s*(?:（[^）\n]*）|\([^)\n]*\))?\s*[:：]?)?")
SESSION_ID = re.compile(r"(?<![A-Za-z0-9_/])session_0[A-Za-z0-9]{15,}")
ID_FIELD = re.compile(r"^\s*[^\s:：][^:：]{0,20}[:：]\s*session_[A-Za-z0-9]+\s*$")
URL = re.compile(r"https?://\S+")
FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
INLINE = re.compile(r"`[^`\n]+`")
COMMENT = re.compile(r"<!--.*?-->", re.S)
TRAILER = re.compile(r"^\s*Claude-Session\s*:\s*\S*?(session_[A-Za-z0-9]+)", re.M | re.I)


class Post:
    """GitHub へ出す 1 つの文の束。kind: pr / comment / issue / commit / other。"""

    def __init__(self, kind, repo="", number=None, cwd="", event=False):
        self.kind, self.repo, self.number, self.cwd, self.event = kind, repo, number, cwd, event
        self.texts = []     # [(どこ, 文)]
        self.unread = []    # 読めない文の訳

    def add(self, key, text):
        if isinstance(text, str) and text.strip():
            self.texts.append((WHERE.get(self.kind, {}).get(key) or "GitHub へ出す文（%s）" % key, text))

    def body(self):
        return next((t for w, t in self.texts if w in ("PR の本文", "コメント", "issue の本文")), "")


def tool_kind(name):
    name = str(name or "")
    for kind, names in (("pr", PR_TOOLS), ("comment", COMMENT_TOOLS), ("issue", ISSUE_TOOLS), ("commit", COMMIT_TOOLS)):
        if any(name == n or name.endswith("__" + n) for n in names):
            return kind
    return ""


def _repo_name(ti):
    owner, repo = str(ti.get("owner") or "").strip(), str(ti.get("repo") or "").strip()
    return "%s/%s" % (owner, repo) if owner and repo else ""


def _matches(patterns, text):
    return any(isinstance(p, str) and p and re.search(p, text) for p in patterns or [])


def _find_sibling(plugin, rel, env_name, data):
    """隣の plugin の正本の在り処。探す順: 環境変数 → 窓の repo の作業の木（見る点を変える PR の枝でもその枝の表で照らす）
    → 土台の共通の在り処探し（guard_common.sibling_plugin_file・qa_page と同じ口）。"""
    env = os.environ.get(env_name) or ""
    if env:
        return env if os.path.isfile(env) else ""
    root = G.project_dir(data)
    cand = os.path.join(root, "plugins", plugin, rel) if root else ""
    if cand and os.path.isfile(cand):
        return cand
    return G.sibling_plugin_file(plugin, rel)


def _tmp_file(text, name):
    d = G.tmp_dir("pr_text")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%d-%s.md" % (os.getpid(), name))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)


def _blank(text):
    """欄の中身が空と同じか（空行・見出し・札だけ・置き場の印だけ）。"""
    for ln in str(text or "").splitlines() or [""]:
        if HEADING.match(ln.strip()):
            continue
        rest = LABEL.sub("", ln, count=1).strip()
        if not BLANK.match(rest):
            return False
    return True


# ── 道: MCP の道具 ──
def mcp_post(name, ti, cwd):
    kind = tool_kind(name)
    if not kind:
        # 並べていない MCP の道具でも、GitHub の repo へ題か本文を出すなら言葉と公開を照らす
        if not (str(name).startswith("mcp__") and _repo_name(ti)
                and any(isinstance(ti.get(k), str) and ti[k].strip() for k in ("title", "body"))):
            return None
        kind = "other"
    number = next((ti.get(k) for k in NUMBER_KEYS if ti.get(k)), None)
    event = str(ti.get("event") or "").upper() in REVIEW_VERDICT_EVENTS
    post = Post(kind, _repo_name(ti), number, cwd, event)
    post.comment_id = ti.get("comment_id")
    for k in TEXT_KEYS:
        if kind == "commit" or k in ("title", "body"):
            post.add(k, ti.get(k))
    return post


# ── 道: Bash（gh・git commit を読み手 cmd_read の語で読む）──
_CAT_DOC = re.compile(r"\$\(\s*cat\s*<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2[ \t]*\n(.*?)\n[ \t]*\3[ \t]*\n?\s*\)", re.S)
_DOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")
_MARK = "\x03%d\x03"


def _inline_docs(cmd):
    """`$(cat <<'EOF' … EOF)` を印に置き換えた命令と、印の中身の並び。中身が展開されうる（引用の無い印で $ か ` を含む）物は残す
    （読み手が読めない所として扱う）。"""
    docs = []

    def rep(m):
        strip, quoted, body = m.group(1), m.group(2), m.group(4)
        if strip:
            body = "\n".join(ln.lstrip("\t") for ln in body.split("\n"))
        if not quoted and re.search(r"[$`\\]", body):
            return m.group(0)
        docs.append(body)
        return _MARK % (len(docs) - 1)

    return _CAT_DOC.sub(rep, cmd), docs


def _stdin_docs(cmd):
    """標準入力へ渡す heredoc の中身の並び（展開されうる物は None）。"""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        found = list(_DOC.finditer(lines[i]))
        i += 1
        for m in found:
            body = []
            while i < len(lines) and lines[i].strip().lstrip("\t") != m.group(3):
                body.append(lines[i].lstrip("\t") if m.group(1) else lines[i])
                i += 1
            i += 1
            text = "\n".join(body)
            out.append(None if not m.group(2) and re.search(r"[$`\\]", text) else text)
    return out


def _restore(text, docs):
    return re.sub("\x03(\\d+)\x03", lambda m: docs[int(m.group(1))] if int(m.group(1)) < len(docs) else m.group(0), text)


def _origin_repo(cwd):
    """作業の木の origin の owner/repo（GitHub の URL の形・proxy の path の形どちらも末尾 2 つ）か ""。"""
    if not cwd or not os.path.isdir(cwd):
        return ""
    try:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    parts = [p for p in re.split(r"[/:]", re.sub(r"\.git$", "", url.rstrip("/"))) if p]
    return "%s/%s" % (parts[-2], parts[-1]) if len(parts) >= 2 else ""


def _takes_value(kind):
    return kind not in ("bool", "unread")


def _parse(args, spec):
    """語の並びを (位置の語, [(名, 種類, 値の Word か None)], [値の無い印]) に読む（-xVALUE・-x=V・--x=V・短い印の束も読む）。"""
    pos, vals, flags, i = [], [], [], 0
    while i < len(args):
        w = args[i]
        t = w.text
        if t == "--":
            pos += args[i + 1:]
            break
        if t.startswith("--"):
            name, eq, inline = t.partition("=")
            kind = spec.get(name, "bool")
            if _takes_value(kind):
                val = R.Word(inline, w.opaque) if eq else (args[i + 1] if i + 1 < len(args) else None)
                i += 0 if eq else 1
                vals.append((name, kind, val))
            else:
                flags.append(name)
                if kind == "unread":
                    vals.append((name, kind, None))
            i += 1
            continue
        if t.startswith("-") and len(t) > 1 and not t[1:].isdigit():
            j = 1
            while j < len(t):
                name = "-" + t[j]
                kind = spec.get(name, "bool")
                if _takes_value(kind):
                    rest = t[j + 1:]
                    rest = rest[1:] if rest.startswith("=") else rest
                    if rest:
                        val = R.Word(rest, w.opaque)
                    else:
                        val = args[i + 1] if i + 1 < len(args) else None
                        i += 1
                    vals.append((name, kind, val))
                    break
                flags.append(name)
                if kind == "unread":
                    vals.append((name, kind, None))
                j += 1
            i += 1
            continue
        pos.append(w)
        i += 1
    return pos, vals, flags


def _spec(**groups):
    out = {}
    for kind, names in groups.items():
        for n in names.split():
            out[n] = kind.replace("__", ":")
    return out


_COMMON = {"-R": "repo", "--repo": "repo"}
_TB = _spec(text__title="-t --title", text__body="-b --body", file__body="-F --body-file")
# gh の (群, 動き) → (kind, 印の読み方)。印の読み方は gh の help の印の形（値を取るか・文か・文の file か・読めない作り方か）。
GH = {
    ("pr", "create"): ("pr", {**_TB, **_spec(unread="-f --fill --fill-first --fill-verbose", unreadval="-T --template",
                                             val="-B --base -H --head -l --label -a --assignee -r --reviewer -m --milestone "
                                                 "-p --project --recover")}),
    ("pr", "edit"): ("pr", {**_TB, **_spec(val="--add-label --remove-label --add-assignee --remove-assignee --add-reviewer "
                                               "--remove-reviewer --add-project --remove-project -B --base -m --milestone")}),
    ("pr", "comment"): ("comment", _spec(text__body="-b --body", file__body="-F --body-file")),
    ("pr", "review"): ("comment", _spec(text__body="-b --body", file__body="-F --body-file")),
    ("pr", "close"): ("comment", _spec(text__body="-c --comment")),
    ("pr", "reopen"): ("comment", _spec(text__body="-c --comment")),
    ("pr", "merge"): ("commit", _spec(text__commit_title="-t --subject", text__commit_message="-b --body",
                                      file__commit_message="-F --body-file", val="--match-head-commit -A --author-email")),
    ("issue", "create"): ("issue", {**_TB, **_spec(unreadval="-T --template",
                                                   val="-a --assignee -l --label -m --milestone -p --project --recover")}),
    ("issue", "edit"): ("issue", {**_TB, **_spec(val="--add-label --remove-label --add-assignee --remove-assignee "
                                                     "--add-project --remove-project -m --milestone")}),
    ("issue", "comment"): ("comment", _spec(text__body="-b --body", file__body="-F --body-file")),
    ("issue", "close"): ("comment", _spec(text__body="-c --comment", val="-r --reason")),
    ("issue", "reopen"): ("comment", _spec(text__body="-c --comment")),
    ("release", "create"): ("other", _spec(text__title="-t --title", text__body="-n --notes", file__body="-F --notes-file",
                                           val="--target --discussion-category --notes-start-tag")),
    ("release", "edit"): ("other", _spec(text__title="-t --title", text__body="-n --notes", file__body="-F --notes-file",
                                         val="--target --discussion-category --tag")),
}
GH_API = _spec(field="-f --raw-field", tfield="-F --field", input="--input",
               val="-X --method -H --header -q --jq -t --template --cache -p --preview --hostname")
GIT_COMMIT = _spec(text__message="-m --message", file__message="-F --file",
                   val="-C --reuse-message -c --reedit-message -t --template --author --date --fixup --squash --cleanup "
                       "--trailer --pathspec-from-file")
GIT_GLOBAL_VAL = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path")


class _Ctx:
    def __init__(self, cwd, docs, stdin):
        self.cwd, self.docs, self.stdin = cwd, docs, stdin

    def word(self, w):
        """値の語の字（読めなければ None）。"""
        if w is None or w.opaque:
            return None
        return _restore(w.text, self.docs)

    def file(self, w):
        """文の file の中身（読めなければ None）。`-` は標準入力の heredoc（命令に 1 つだけ在る時）。"""
        path = self.word(w)
        if path is None:
            return None
        if path == "-":
            return self.stdin[0] if len(self.stdin) == 1 else None
        full = os.path.join(self.cwd or "", os.path.expanduser(path))
        try:
            if os.path.getsize(full) > FILE_LIMIT:
                return None
            with open(full, encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return None


def _fill(post, vals, ctx):
    for name, kind, val in vals:
        if kind == "repo":
            got = ctx.word(val)
            if got:
                post.repo = got.split("/", 1)[-1] if got.count("/") == 2 else got   # HOST/OWNER/REPO も読む
            continue
        if kind in ("unread", "unreadval"):
            post.unread.append("%s は本文を GitHub の側の仕組み（commit・雛形）で作る＝出す文を読めない" % name)
            continue
        if not kind.startswith(("text:", "file:")):
            continue
        key = kind.split(":", 1)[1]
        text = ctx.word(val) if kind.startswith("text:") else ctx.file(val)
        if text is None:
            post.unread.append("%s の値が読めない（$(…)・解けない変数・無い file・パイプの標準入力）" % name)
            continue
        post.add(key, text)


def _gh_post(words, ctx):
    args = words[1:]
    names = [w.text for w in _parse(args, _COMMON)[0]]     # gh の形は `gh <群> <動き> …`（群と動きが先の 2 語）
    if not names:
        return None
    if names[0] == "api":
        return _gh_api_post(args, ctx)
    group, action = (names + ["", ""])[:2]
    if (group, action) not in GH:
        return None
    kind, spec = GH[(group, action)]
    pos, vals, flags = _parse(args, {**_COMMON, **spec})
    rest = [w.text for w in pos[2:]]
    number = next((re.sub(r".*/", "", r) for r in rest if re.fullmatch(r"#?\d+|https?://\S+/(?:pull|issues)/\d+", r)), None)
    event = (group, action) == ("pr", "review") and bool(set(flags) & {"-a", "--approve", "-r", "--request-changes"})
    post = Post(kind, "", number.lstrip("#") if number else None, ctx.cwd, event)
    post.group = group
    _fill(post, vals, ctx)
    if not post.repo:
        post.repo = _origin_repo(ctx.cwd)
    return post


def _api_kind(endpoint):
    """REST の path の形から (kind, owner/repo の印か ""・番号)。"""
    toks = [t for t in endpoint.split("?", 1)[0].strip("/").split("/") if t]
    if toks[:1] == ["graphql"]:
        return "other", "", None
    if toks[:1] != ["repos"] or len(toks) < 3:
        return "other", "", None
    repo, rest = "%s/%s" % (toks[1], toks[2]), toks[3:]
    number = rest[1] if len(rest) > 1 and rest[1].isdigit() and rest[0] in ("pulls", "issues") else None
    if "comments" in rest or "reviews" in rest:
        kind = "comment"
    elif rest[:1] == ["pulls"] and rest[-1:] == ["merge"]:
        kind = "commit"
    elif rest[:1] == ["pulls"]:
        kind = "pr"
    elif rest[:1] == ["issues"]:
        kind = "issue"
    elif rest[:1] in (["contents"], ["git"], ["commits"]):
        kind = "commit"
    else:
        kind = "other"
    return kind, repo, number


def _gh_api_post(args, ctx):
    pos, vals, _ = _parse(args, {**_COMMON, **GH_API})
    endpoint = ctx.word(pos[1]) if len(pos) > 1 else None
    if endpoint is None:
        post = Post("other", _origin_repo(ctx.cwd), cwd=ctx.cwd)
        if any(k in ("field", "tfield", "input") for _, k, _ in vals):
            post.unread.append("gh api の出す先（endpoint）が読めない")
        return post
    kind, repo, number = _api_kind(endpoint)
    if "{owner}" in repo or "{repo}" in repo or not repo:
        repo = _origin_repo(ctx.cwd) if (not repo or "{" in repo) else repo
    post = Post(kind, repo, number, ctx.cwd)
    graphql = endpoint.strip("/").startswith("graphql")
    fields = {}
    for name, k, val in vals:
        if k == "repo":
            continue
        if k == "input":
            raw = ctx.file(val)
            try:
                got = json.loads(raw) if raw is not None else None
            except ValueError:
                got = None
            if not isinstance(got, dict):
                post.unread.append("gh api --input の JSON が読めない")
                continue
            fields.update({kk: vv for kk, vv in got.items() if isinstance(vv, (str, int, float, bool))})
            continue
        if k not in ("field", "tfield"):
            continue
        raw = ctx.word(val)
        if raw is None or "=" not in raw:
            post.unread.append("gh api %s の欄が読めない" % name)
            continue
        key, _, value = raw.partition("=")
        key = re.sub(r"\[.*$", "", key)
        if k == "tfield" and value.startswith("@"):
            value = ctx.file(R.Word(value[1:]))
            if value is None:
                post.unread.append("gh api %s %s= の file が読めない" % (name, key))
                continue
        fields[key] = value
    post.event = str(fields.get("event") or "").upper() in REVIEW_VERDICT_EVENTS
    for key, value in fields.items():
        if isinstance(value, str) and (graphql or key in TEXT_KEYS):
            post.add(key, value)
    return post


def _git_post(words, ctx):
    args, i, cwd = words[1:], 0, ctx.cwd
    while i < len(args):
        t = args[i].text
        if t in GIT_GLOBAL_VAL:
            if t == "-C" and i + 1 < len(args):
                cwd = os.path.join(cwd or "", args[i + 1].text)
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        break
    if i >= len(args) or args[i].text != "commit":
        return None
    sub = _Ctx(cwd, ctx.docs, ctx.stdin)
    _, vals, _ = _parse(args[i + 1:], GIT_COMMIT)
    post = Post("commit", _origin_repo(cwd), cwd=cwd)
    msgs = Post("commit")
    _fill(msgs, vals, sub)
    post.unread = msgs.unread
    if msgs.texts:
        post.texts = [("commit の説明", "\n\n".join(t for _, t in msgs.texts))]
    return post


def bash_posts(cmd, cwd):
    """Bash の命令から GitHub へ出す文の束の並び。"""
    if not isinstance(cmd, str) or not cmd.strip():
        return []
    flat, docs = _inline_docs(cmd)
    ctx = _Ctx(cwd, docs, _stdin_docs(flat))
    out = []
    for words in R.read(flat).segments:
        prog = R.prog_name(words)
        if prog == "cd" and len(words) == 2 and not words[1].opaque:
            nxt = os.path.join(ctx.cwd or "", os.path.expanduser(words[1].text))
            ctx.cwd = os.path.normpath(nxt) if os.path.isdir(nxt) else ctx.cwd
            continue
        post = _gh_post(words, ctx) if prog == "gh" else _git_post(words, ctx) if prog == "git" else None
        if post is not None and (post.texts or post.unread):
            out.append(post)
    return out


def posts_of(data):
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return []
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else G.project_dir(data)
    if name == "Bash":
        return bash_posts(ti.get("command"), cwd)
    post = mcp_post(name, ti, cwd)
    return [post] if post is not None and (post.texts or post.event) else []


# ── verdict（レビューの判定の形）──
def _flat(text):
    """照らす前に字を 1 つの形へ寄せる（全角→半角・強調と打ち消しの印を外す・小文字）。"""
    return re.sub(r"[*~]+|(?<!\w)_+|_+(?!\w)", "", unicodedata.normalize("NFKC", text)).lower()


def looks_verdict(body):
    """判定のコメントか。判定の形そのものの印（名乗りと判定が揃う行・verdict の見出し・判定の欄が green|red だけの行）で
    見分ける。文中に「判定: green」と書いた普通のコメントや「レビューした窓は…」で始まる文は判定と見なさない。"""
    body = _flat(FENCE.sub(" ", COMMENT.sub(" ", body)))
    return bool(VERDICT_LINE.search(body) or VERDICT_HEAD.search(body) or VERDICT_PAIR.search(body))


WRITER_LINE = re.compile(r"^\s*書いた窓\s*[:：]\s*(session_[A-Za-z0-9]+)", re.M)
NUMBER_KEYS = ("issue_number", "pullNumber", "pull_number")


def _gh(args, cwd=None):
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd or None)


def window_id():
    """判定を出す窓の実物の session id（窓の環境の CLAUDE_CODE_REMOTE_SESSION_ID の cse_… を session_… に）か ""。"""
    raw = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID") or ""
    m = re.fullmatch(r"(?:cse|session)_([A-Za-z0-9]+)", raw.strip())
    return "session_" + m.group(1) if m else ""


def pr_facts(post):
    """判定を出す先の PR の (先端の SHA, 書いた窓, commit を書いた窓の並び, 誤り)。GitHub から引く（写さない）。

    書いた窓は PR 本文の頭の決まった欄 `書いた窓: <session id>`（CONTRIBUTING §1 の PR の型）、commit を書いた窓は
    PR の merge でない commit の `Claude-Session:`（review-pr の別の目の材料）。引けない時は誤りを返す（欠けた材料で判定を通さない）。"""
    repo = post.repo
    if not repo:
        return "", "", [], "出す先の repo（owner・repo）が道具の入力に無い"
    number = post.number
    try:
        if not number and getattr(post, "comment_id", None):
            p = _gh(["repos/%s/issues/comments/%s" % (repo, post.comment_id), "--jq", ".issue_url"])
            number = p.stdout.strip().rsplit("/", 1)[-1] if p.returncode == 0 else None
        if not number and getattr(post, "group", "") == "pr" and post.cwd:
            p = subprocess.run(["gh", "pr", "view", "-R", repo, "--json", "number", "--jq", ".number"], cwd=post.cwd,
                               capture_output=True, text=True, timeout=TIMEOUT)
            number = p.stdout.strip() if p.returncode == 0 and p.stdout.strip().isdigit() else None
        if not number:
            return "", "", [], "判定を出す先の PR の番号が分からない"
        p = _gh(["repos/%s/pulls/%s" % (repo, number), "--jq", '.head.sha + "\\n" + (.body // "")'])
        if p.returncode != 0:
            return "", "", [], "PR #%s を引けなかった（判定は PR に出す・gh の認証か網を確かめる）: %s" % (
                number, (p.stderr or "").strip().splitlines()[-1:] or "")
        c = _gh(["repos/%s/pulls/%s/commits" % (repo, number), "--paginate", "--jq",
                 '.[] | select((.parents | length) < 2) | .commit.message'])
    except FileNotFoundError:
        return "", "", [], "GitHub の CLI（gh）が無く、PR の先端と書いた窓を引けない"
    except (OSError, subprocess.SubprocessError) as e:
        return "", "", [], "PR を引けなかった（%s）" % e.__class__.__name__
    if c.returncode != 0:
        return "", "", [], "PR #%s の commit を引けなかった（commit を書いた窓を照らせない）" % number
    head, _, body = p.stdout.partition("\n")
    m = WRITER_LINE.search(body)
    if not re.fullmatch(r"[0-9a-f]{40}", head.strip()):
        return "", "", [], "PR #%s の先端の SHA が読めない" % number
    if not m:
        return head.strip(), "", [], "PR #%s の本文の頭に `書いた窓: <session id>` が無く、別の目を照らせない（PR の型どおりに書く）" % number
    authors = list(dict.fromkeys(TRAILER.findall(c.stdout)))
    return head.strip(), m.group(1), authors, ""


def check_verdict(post, data):
    body = post.body()
    if not (post.event or (body and looks_verdict(body))):
        return []
    tool = _find_sibling(*VERDICT_FORM, data)
    if not tool:
        return ["判定の形の道具（checker の verdict_form.py）が見つからず、形を確かめられない。plugin checker を入れる"
                "（または AF_VERDICT_FORM に path）"]
    head, writer, authors, err = pr_facts(post)
    if err:
        return ["判定の材料: " + err]
    cmd = [sys.executable, tool, _tmp_file(body, "verdict"), "--writer", writer, "--head", head]
    poster = window_id()
    if poster:
        cmd += ["--poster", poster]
    if authors:
        cmd += ["--other-writers", ",".join(authors)]
    try:
        p = _run(cmd)
    except (OSError, subprocess.SubprocessError) as e:
        return ["判定の形の道具が走らなかった: %s" % e.__class__.__name__]
    if p.returncode == 0:
        return []
    errs = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    if p.returncode != 1 or not errs:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-2:]
        return ["判定の形の道具が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))]
    return ["判定の形: " + e for e in errs]


# ── cleanup（PR 本文の整地の 4 欄）──
def template_parts(path):
    """雛形から (見出しの並び [(番号, 名)], 置き場の字の並び)。読めなければ例外。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heads = [(no, name.split("（")[0].strip()) for no, name in TEMPLATE_HEAD.findall(text)]
    if not heads:
        raise ValueError("整地の雛形に `## N. ` の見出しが無い: %s" % path)
    holders = sorted({m.group(0)[:14] for m in PLACEHOLDER.finditer(COMMENT.sub("", text))})
    return heads, holders


def head_bodies(body, no, name):
    """本文の中の、見出し `N. 名` の下の中身（次の同じか上の段の見出しまで）の並び。"""
    lines = body.splitlines()
    want = re.compile(r"^(?:%s\.\s*)?%s" % (re.escape(no), re.escape(name)))
    out = []
    for i, ln in enumerate(lines):
        m = HEADING.match(ln.strip())
        if not m or not want.match(m.group(2)):
            continue
        level = len(m.group(1))
        end = next((j for j in range(i + 1, len(lines)) if (h := HEADING.match(lines[j].strip())) and len(h.group(1)) <= level),
                   len(lines))
        out.append("\n".join(lines[i + 1:end]))
    return out


def check_cleanup(body, repo, data, vals):
    if repo and _matches(vals.get("pr_cleanup_exempt_repos"), repo):
        return []
    body = FENCE.sub(" ", COMMENT.sub(" ", body))      # 注記（雛形の説明）とコードの囲みの中は数えない
    if any(not _blank(m.group(1)) for m in NOT_NEEDED.finditer(body)):
        return []
    tpl = _find_sibling(*CLEANUP_TEMPLATE, data)
    if not tpl:
        return ["整地の雛形（dev-flow の preimpl-cleanup の 整地受領証.template.md）が見つからず、欄を確かめられない。"
                "plugin dev-flow を入れる（または AF_CLEANUP_TEMPLATE に path）"]
    try:
        heads, holders = template_parts(tpl)
    except (OSError, ValueError) as e:
        return ["整地の雛形が読めない: %s" % e]
    out, lack, empty = [], [], []
    for no, name in heads:
        got = head_bodies(body, no, name)
        if not got:
            lack.append("%s. %s" % (no, name))
        elif all(_blank(b) for b in got):
            empty.append("%s. %s" % (no, name))
    if lack:
        out.append("整地の見出しが無い: %s（雛形の見出し %d つ）" % ("・".join(lack), len(heads)))
    if empty:
        out.append("整地の見出しの下の中身が空（空行・札・〔…〕・<…>・- だけは無いと同じ）: %s" % "・".join(empty))
    left = [h for h in holders if h in body]
    if left:
        out.append("整地の雛形の `〔…〕` が残っている: %s" % "・".join(h + "…" for h in left[:3]))
    return out


# ── words（GitHub へ出す文の言葉）──
def visible_prose(body, skip=()):
    """数えない所（頭の欄の塊の、値が窓の id だけの欄・判定の形が id を置く行・コード・URL・注記）を除いた文。"""
    lines = body.splitlines()
    head_end = next((i for i, ln in enumerate(lines) if not ln.strip()), len(lines))
    kept = [ln for i, ln in enumerate(lines) if i not in skip and not (i < head_end and ID_FIELD.match(ln))]
    text = FENCE.sub(" ", COMMENT.sub(" ", "\n".join(kept)))
    return URL.sub(" ", INLINE.sub(" ", text))


def _form_id_lines(text, data):
    """判定の形が窓の id を置く行（正本は verdict_form.form_id_lines）。道具が無ければ空（判定の照らしが別に止める）。"""
    tool = _find_sibling(*VERDICT_FORM, data)
    if not tool:
        return set()
    try:
        return set(G.load_module("verdict_form_for_pr_text", tool).form_id_lines(text))
    except (Exception, SystemExit):      # noqa: BLE001  形の道具が壊れた時は判定の照らしが止める
        return set()


def check_words(post, vals, data):
    if post.repo and _matches(vals.get("pr_words_exempt_repos"), post.repo):
        return []
    out = []
    verdict = post.kind == "comment" and (post.event or looks_verdict(post.body()))
    for where, text in post.texts:
        skip = set(_form_id_lines(text, data)) if verdict and text == post.body() else set()
        if post.kind == "comment":
            # 前の判定を引いた返事: 引用（> ）の中の 1 行目の名乗りは、判定の形の欄（既に GitHub に在る判定の写し）
            for i, ln in enumerate(text.splitlines()):
                if ln.lstrip().startswith(">") and 0 in _form_id_lines(re.sub(r"^\s*(?:>\s*)+", "", ln), data):
                    skip.add(i)
        ids = list(dict.fromkeys(SESSION_ID.findall(visible_prose(text, skip))))
        if ids:
            out.append("%sに窓の id がそのまま %d 個: %s" % (where, len(ids), "・".join(ids[:3]) + ("…" if len(ids) > 3 else "")))
    return out


# ── public（公開の repo に置かない物）──
WORKFLOW_DIR = os.path.join(".github", "workflows")
DENY_FILE = re.compile(r"deny-words-file\s*:\s*[\"']?([^\s\"'#]+)")
USES_GUARD = re.compile(r"(?:uses\s*:\s*\S*public-guard\b|^\s*public-guard\s*:)", re.M)


def visibility(repo):
    """GitHub の repo の公開の別（public / private / internal）。公開の repo は誰にでも見える＝見えない（404）なら "hidden"。
    引けない（gh が無い・認証・網）時は ""。"""
    try:
        p = _gh(["repos/%s" % repo, "--jq", ".visibility"])
    except (OSError, subprocess.SubprocessError):
        return ""
    v = p.stdout.strip()
    if p.returncode == 0 and v in ("public", "private", "internal"):
        return v
    if p.returncode != 0 and re.search(r"HTTP 404|Not Found", p.stderr or ""):
        return "hidden"
    return ""


def _checkout_of(repo, root):
    """作業の木 root の取り出しが owner/repo なら、その根。"""
    if not root or not repo or _origin_repo(root).lower() != repo.lower():
        return ""
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def public_target(repo, root, vals):
    """(公開か, 取り出しの根, 置かない語の表の path)。公開の別は GitHub の repo の実物で見る。引けない時だけ、
    取り出しの workflow が public-guard を呼ぶか・値の表 public_repos_extra で見る。"""
    top = _checkout_of(repo, root)
    guarded, words = False, ""
    if top:
        for wf in sorted(glob.glob(os.path.join(top, WORKFLOW_DIR, "*.y*ml"))):
            try:
                with open(wf, encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue
            if USES_GUARD.search(raw):
                m = DENY_FILE.search(raw)
                guarded, words = True, (os.path.join(top, m.group(1)) if m else "")
                break
    if repo and _matches(vals.get("public_repos_extra"), repo):
        return True, top, words
    vis = visibility(repo) if repo else ""
    if vis == "public":
        return True, top, words
    if vis:
        return False, top, ""
    return guarded, top, words


def find_public_guard(top=""):
    """public-guard/guard.py の path か ""（土台の repo の根に在る・plugin の外）。探す順: 環境変数 → この guard と同じ土台
    （guard_common.foundation_file＝入れた guard の版の隣）。出す先の repo の作業の木の物は読まない（PR の枝を取り出した
    手元では、守りと別の版＝古い公開の検査を呼んでしまう。守りが読む正本は守りと同じ版の 1 つ）。top は呼び口を変えないため残す。"""
    env = os.environ.get("AF_PUBLIC_GUARD") or ""
    if env:
        return env if os.path.isfile(env) else ""
    return G.foundation_file(os.path.join("public-guard", "guard.py"))


def check_public(post, data, vals):
    texts = post.texts
    is_public, top, words = public_target(post.repo, post.cwd or G.project_dir(data), vals)
    if not is_public or not texts:
        return []
    if words and not os.path.isfile(words):
        return ["公開の repo の workflow が名指す置かない語の表 %s が無く、照らせない（CI も同じ時に止まる）。表を置くか"
                "workflow を直す" % os.path.relpath(words, top or None)]
    tool = find_public_guard(top)
    if not tool:
        return ["公開の repo だが、公開の検査（土台の public-guard/guard.py）が見つからず照らせない。土台の marketplace を"
                "入れ直す（または AF_PUBLIC_GUARD に path）"]
    cmd = [sys.executable, tool]
    for i, (where, text) in enumerate(texts):
        cmd += ["--text", "%s=%s" % (where, _tmp_file(text, "public%d" % i))]
    if words:
        cmd += ["--deny-words-file", words]
    try:
        p = _run(cmd)
    except (OSError, subprocess.SubprocessError) as e:
        return ["公開の検査が走らなかった: %s" % e.__class__.__name__]
    if p.returncode == 0:
        return []
    hits = [ln.strip() for ln in p.stdout.splitlines() if ln.startswith("  ")]
    if p.returncode != 1 or not hits:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-2:]
        return ["公開の検査が壊れた（exit %d・`--text` を知らない古い版かもしれない）: %s" % (p.returncode, " / ".join(tail))]
    return ["公開の repo に置かない物: " + h for h in hits]


HOW = {
    "broken": "一時の置き場（TMPDIR・AF_GUARD_TMP）に書けるか・入れた plugin が揃っているかを確かめ、直してから出し直す。"
              "直せない時は止めた文を添えて親の窓へ返す（見張りを外して出さない）。",
    "unread": "出す文は字で直に書く（--body \"…\"・-m \"…\"）か、在る file を --body-file・-F で渡すか、`$(cat <<'EOF' … EOF)` "
              "で書く（読み手が中身を読める形）。$(…) の命令の出力・解けない変数・パイプの標準入力・--fill・--template は、出す前に"
              "照らせないので使わない。",
    "verdict": "判定のコメントは skill `checker:review-pr` の「判定の形」で書き直す（形の正本はその SKILL.md と verdict_form.py・"
               "ここに写さない）。`python3 <verdict_form.py> <下書き> --writer <書いた窓> --head <PR の先端>` が exit 0 になってから出す。"
               "別の目は判定を出す窓の実物で見る（名乗りの字を替えても、書いた窓・commit を書いた窓からは出せない）。",
    "cleanup": "PR 本文の「何をどう変えたか」の後に `## 整地（根治の 4 段）` を置き、skill `dev-flow:preimpl-cleanup` の雛形の 4 つの見出しで"
               "書く（中身は頭が書く・見出しだけ並べて中身を空にしない・`〔…〕` を残さない）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）"
               "なら、4 欄の代わりに `整地: 不要（<なぜ要らないか>）` の 1 行を書く（訳はレビューが照らす）。",
    "words": "窓の id は、読む人が開けるリンク（https://claude.ai/code/<id>）にして役の名を添える（例: 「直す窓（リンク）」）か、役の名だけに"
             "する。本文の頭の欄の塊の `親窓: <id>`・`書いた窓: <id>` と、判定の形の欄と、コードの囲みの中は数えない。",
    "public": "当たった所を書き直す（秘密・個人の情報は消す・作り物の例は example.com などにする・置かない語と顧客の語は一般の言葉に言い換える）。"
              "GitHub の本文は書き替えても古い版が編集の履歴に公開で残るので、出す前に直す。",
}
HEAD = {
    "broken": "照らしが壊れた",
    "unread": "GitHub へ出す文が読めない",
    "verdict": "レビューの判定の形が崩れている",
    "cleanup": "PR 本文の整地の欄が雛形と合わない",
    "words": "GitHub へ出す文に AI の中の呼び名が出ている",
    "public": "公開の repo に置かない物がある",
}


def findings(data, vals):
    """[(札, 文)]。"""
    out = []
    for post in posts_of(data):
        out += [("unread", m) for m in post.unread]
        if post.kind == "comment":
            out += [("verdict", m) for m in check_verdict(post, data)]
        if post.kind == "pr" and post.body().strip():
            out += [("cleanup", m) for m in check_cleanup(post.body(), post.repo, data, vals)]
        out += [("words", m) for m in check_words(post, vals, data)]
        out += [("public", m) for m in check_public(post, data, vals)]
    return out


def _watched(data):
    """壊れた時に止める側へ倒す呼び出しか（GitHub へ文を出しうる道だけ。ほかの道具・命令は巻き込まない）。"""
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    if tool_kind(name):
        return True
    if name == "Bash":
        cmd = str(ti.get("command") or "")
        try:
            return any(R.prog_name(seg) in ("gh", "git") for seg in R.read(cmd).segments)
        except Exception:      # noqa: BLE001
            return bool(re.search(r"\b(?:gh|git)\b", cmd))
    return name.startswith("mcp__") and bool(_repo_name(ti))


def check(data, vals):
    """止めるなら理由、通すなら ""。見る道の照らしの中で何かが壊れたら、黙って通さず止める（guard の入口は例外を通す側に倒すため）。"""
    try:
        found = findings(data, vals)
    except Exception as e:      # noqa: BLE001
        if not _watched(data):
            return ""
        found = [("broken", "照らしの途中で壊れた（%s）。照らせない文は出さない" % e.__class__.__name__)]
    if not found:
        return ""
    codes = list(dict.fromkeys(c for c, _ in found))
    lines = ["[guard] GitHub へ出す前の文を照らして止めた（%s）。オーナー同意 2026-11-19・人の操作は止めていない・文はまだ "
             "GitHub に出ていない。直して出し直す。" % "／".join(HEAD[c] for c in codes)]
    lines += ["- [%s] %s" % (c, m) for c, m in found[:SHOWN]]
    if len(found) > SHOWN:
        lines.append("- （ほか %d 件）" % (len(found) - SHOWN))
    lines.append("直し方:")
    lines += ["- [%s] %s" % (c, HOW[c]) for c in codes]
    lines.append("誤って止めた時: 整地を PR 本文の外に置く repo・言葉の照らしが合わない repo は、値の表の guard.pr_cleanup_exempt_repos・"
                 "guard.pr_words_exempt_repos（owner/repo に当てる正規表現）に足す（PR とレビューを通す）。判定の形と公開の検査は"
                 "外さない（決まりの正本を直す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)
