"""PreToolUse — PR の題・本文と、PR・issue へのコメントを、GitHub へ出す前に照らす。崩れていれば AI だけを止めて書き直させる。

なぜ在るか: レビューの判定の形・PR 本文の整地の 4 欄・人が読む文の言葉・公開の repo に置かない物は、決まりと道具はあるのに
AI が自分で回すか、出した後に CI やレビューが拾うだけだった。そのため、形の崩れた判定が合流の材料になり、欄の欠けた PR 本文が
レビューで初めて見つかり、公開の repo の PR 本文に置かない語が出て GitHub の編集の履歴に残った（オーナー同意 2026-11-19:
決まりが文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい）。
止まるのは AI の道具の呼び出しだけ（文はまだ GitHub に出ていない）。人の操作は何も止めない。

見る道具: 名の末尾（MCP の server の名は問わない）で見分ける。
  PR     … create_pull_request・update_pull_request（題・本文）
  コメント … add_issue_comment・update_issue_comment・add_reply_to_pull_request_comment・pull_request_review_write・
             add_comment_to_pending_review（本文）
  issue  … issue_write（題・本文）
  commit … merge_pull_request（commit_title・commit_message）・push_files・create_or_update_file・delete_file（message）
           ＝MCP から出す commit の説明。公開の検査だけを当てる
  push   … Bash の git push（どの remote の枝にも無い commit の説明と名義）。公開の検査だけを当てる。命令の字に正規表現を
           当てず、guard_common.parse_shell で走る命令の語に分けて見る（前置き・bash -c・eval の中も）。読み切れない形は git と
           push の字が在れば push と見て、窓の cwd と読めた cd・-C の先の全部を照らす。先が字で決まらなければ止める
照らす物（見分けは正本を直に読む・呼ぶ。ここに決まりを写さない）:
  verdict … （材料: 出す先の PR の先端と、PR 本文の頭の `書いた窓:` を gh で引き、--writer・--head で渡す。引けなければ止める）
            コメントがレビューの判定（verdict_form の LINE1 に合う行・その字の欄が窓の id と green|red と揃う崩れた行・
            verdict の見出し）なら、checker の `scripts/verdict_form.py` をそのまま呼ぶ。赤なら止める。道具が見つからない・
            壊れた時も止める。PR の review の event が APPROVE・REQUEST_CHANGES なら本文によらず判定と見る。形が合えば、
            点 4 の物差しの最後の行が、この窓か助手が物差しを回した道具の呼び出し（値の表 pr_ruler_trace の跡の形・
            Bash は読み切れる物差しの命令 1 つだけ・tool_use の id で結ぶ・走った＝誤りなく返ったか Exit code N で始まる）の結果の最後の行と同じか（回した跡）も
            照らす。PR 本文を読んだ結果・同じ呼び出しの他の命令の出力・結果の途中の字は数えない
  cleanup … PR の本文（本文を渡す時だけ）に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し
            （`## 1.`〜`## 4.`。見出しの名は雛形から読む）が全部在り、雛形の `〔…〕` が残っていない事。整地の要らない PR
            （振る舞いを変えない: 誤字・記録だけ・版だけ等）は本文に `整地: 不要（<訳>）` の 1 行を書く。PR の差分の file を
            gh で引き、振る舞いの file（コード・SKILL.md・hooks・核／細目／振る舞い）を触れば止める
  words   … PR の題・本文とコメント・issue の文に、窓の id（`session_01…`）がそのまま出ていない事。頭の決まった欄（親窓・
            書いた窓・job・触る path・検査・連絡板の窓）・判定の名乗りと点 3・コードの囲み・`…` の字・URL の中は数えない
  board   … 連絡板の repo（細目 §8）へのコメント・issue: 連絡板の issue のコメントの冒頭の 1 行が、連絡板の本文の「書き方」の形か。
            新しい issue を立てない（連絡板は 1 本だけ）。連絡板の repo を細目から読めない・在る無しを引けない時は止める
  public  … 公開の repo（GitHub の repo の visibility が正本。引けない時だけ窓の repo の取り出しの workflow が action public-guard
            を呼ぶ／値の表 public_repos_extra。それでも決まらなければ止める）なら、
            題・本文を `public-guard/guard.py --text` に渡す（置かない語の表はその workflow の deny-words-file）。当たれば止める。
            検査が見つからない・壊れた時も止める（公開の repo へは、照らせない文を出さない）
隣の正本（判定の道具・雛形・公開の検査）は、窓の repo の作業の木に commit していない書き替えが在れば使わず、入れた plugin の物で照らす。
誤って止めた時: 値の表 pr_cleanup_exempt_repos・pr_words_exempt_repos（owner/repo に当てる正規表現）で repo ごとに外す。
判定の形と公開の検査は外す口を持たない（直すのは文の方・判定の形の決まりは review-pr の SKILL.md が正本）。
値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

import guard_common as G

HOOKS = {"pre": "check"}

TIMEOUT = 30
SHOWN = 12

PR_TOOLS = ("create_pull_request", "update_pull_request")
COMMENT_TOOLS = ("add_issue_comment", "update_issue_comment", "add_reply_to_pull_request_comment",
                 "pull_request_review_write", "add_comment_to_pending_review")
ISSUE_TOOLS = ("issue_write",)
COMMIT_TOOLS = ("merge_pull_request", "push_files", "create_or_update_file", "delete_file")
COMMIT_FIELDS = (("commit_title", "commit の題"), ("commit_message", "commit の説明"), ("message", "commit の説明"))

VERDICT_FORM = ("checker", os.path.join("scripts", "verdict_form.py"), "AF_VERDICT_FORM")
CLEANUP_TEMPLATE = ("dev-flow", os.path.join("skills", "preimpl-cleanup", "整地受領証.template.md"), "AF_CLEANUP_TEMPLATE")

# 判定の形の印（review-pr の形）: 名乗りの欄と判定が 1 行に揃う行（どの行でも・`:` の全角半角を問わない）か、verdict の見出し
# （# の数・大小文字を問わない）。引用（行頭の `>`）の中は、前の判定を引いた返事なので数えない。
VERDICT_HEAD = re.compile(r"^[ \t]*#{1,6}\s*verdict\s*$", re.M | re.I)
NOT_NEEDED = re.compile(r"^\s*(?:[-*]\s*)?\**整地\**\s*[:：]\s*(?:不要|要らない)\s*[（(]\s*(?![<＜〔])\S[^)）]*[)）]", re.M)
TEMPLATE_HEAD = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)
PLACEHOLDER = re.compile(r"〔[^〕\n]{4,}〕")
HEAD_FIELD = re.compile(r"^\s*(?:親窓|書いた窓|job|触る path|検査|窓)\s*[:：]")   # 窓: は連絡板の冒頭の行
SESSION_ID = re.compile(r"(?<![A-Za-z0-9_/])session_0[A-Za-z0-9]{15,}")
URL = re.compile(r"https?://\S+")
FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
INLINE = re.compile(r"`[^`\n]+`")
COMMENT = re.compile(r"<!--.*?-->", re.S)
QUOTE = re.compile(r"^[ \t]*>.*$", re.M)                  # 引用の行（人の文を引いた所＝この PR の欄でない）


GIT_OPT_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env")


# push する dir を変える語（cd・pushd・popd・git の -C・--git-dir・--work-tree・env -C・GIT_DIR= など）。命令の字と読めた語で数を比べ、
# 字に在るのに読めた語に無い（$(…)・関数・bash -c の中の読めない所・前置きの外した所に在る）なら、push の先を読み切れないと見る。
DIR_WORD = re.compile(r"(?<![\w./-])(?:cd|pushd|popd|-C|--chdir|-D|--git-dir|--work-tree)(?![\w-])|\bGIT_(?:DIR|WORK_TREE)\b")


# parse_shell の読み切れない所（Unknown.code）のどれで照らす側に倒すか。code で決め、訳の字は見ない。今は全部の code
# （知らない code が足されても、guard_common.UNKNOWN_CODES に在れば倒す側に入る）。
PUSH_UNREAD = G.UNKNOWN_CODES          # git と push の字が在れば push と見る
RULER_UNREAD = G.UNKNOWN_CODES         # 物差しの呼び出しと数えない


def _join(base, d):
    d = os.path.expanduser(d)
    return os.path.join(base, d) if base and not os.path.isabs(d) else d


def _git_dir(argv, k, cd, dirs, bad):
    """argv[k] の git の -C・--git-dir・--work-tree の先を dirs に足し、その git が push なら push する dir を返す（でなければ None）。"""
    i, where = k + 1, cd
    while i < len(argv) and argv[i].startswith("-"):
        opt, eq, val = argv[i].partition("=")
        if opt in GIT_OPT_ARG:
            if not eq and i + 1 < len(argv):
                val = argv[i + 1]
                i += 1
            if opt in ("-C", "--git-dir", "--work-tree"):
                if G.is_dyn(val) or not val:
                    bad.append("git の %s の先が字で決まらない" % opt)
                else:
                    where = _join(where, val) if opt == "-C" else _join(cd, val)
                    dirs.append(where)
        i += 1
    return where if i < len(argv) and argv[i] == "push" else None


def git_push(cmd):
    """Bash の命令が git push を走らせるなら (push しうる dir の並び, True, 読めない理由)、走らせないなら ([], False, "")。
    命令の字に正規表現を当てず、guard_common.parse_shell で走る単純な命令の語に分けて見る（前置き・bash -c・eval の中も）。
    dir は窓の cwd からの相対（"" が窓の cwd）。読み切れる命令では push する git の -C か前の cd の 1 つ。読み切れない形
    （parse_shell の unknowns: $(…)・関数・| bash・表に無い前置き等）が在り、命令の字に git と push の字が在れば push と見て
    （知らない形を push でないと見て通さない＝照らす側に倒す）、窓の cwd と読めた cd・-C の先の全部を返す（読めた cd を捨てない）。
    cd・-C の先が字で決まらない（変数・命令の置き換え・引数の無い cd・cd -・popd）か、dir を変える語が読めない所に在れば、
    理由を返す（呼ぶ側が止める）。"""
    cmd = cmd or ""
    cmds, unknowns = G.parse_shell(cmd)
    cd, dirs, pushes, bad = "", [""], [], []
    for argv in cmds:
        if argv[0] in ("cd", "pushd", "popd"):
            args = [w for w in argv[1:] if w != "--"]
            if argv[0] == "popd" or len(args) != 1 or args[0] == "-" or G.is_dyn(args[0]):
                bad.append("%s の先が字で決まらない（変数・命令の置き換え・引数なし・cd -・popd）" % argv[0])
                continue
            cd = _join(cd, args[0])
            dirs.append(cd)
            continue
        for k in [k for k, w in enumerate(argv) if os.path.basename(w) == "git"]:     # flock … git -C x push の類の中の git も
            where = _git_dir(argv, k, cd, dirs, bad)
            if k == 0 and where is not None:
                pushes.append(where)
    said = len(DIR_WORD.findall(cmd))
    read = sum(len(DIR_WORD.findall(" ".join(argv))) for argv in cmds)
    if said > read:
        bad.append("dir を変える語（cd・-C・GIT_DIR 等）が読み切れない所に在る")
    if {u.code for u in unknowns} & PUSH_UNREAD and "git" in cmd and "push" in cmd:
        return list(dict.fromkeys(dirs)), True, "・".join(bad)
    if pushes:
        return list(dict.fromkeys(pushes)), True, "・".join(bad)
    return [], False, ""


def tool_kind(name, ti=None):
    name = str(name or "")
    if name == "Bash":
        cmd = (ti or {}).get("command") if isinstance(ti, dict) else ""
        return "push" if isinstance(cmd, str) and git_push(cmd)[1] else ""
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
    if cand and os.path.isfile(cand) and _committed(root, os.path.join("plugins", plugin)):
        return cand
    return G.sibling_plugin_file(plugin, rel)


def _committed(root, rel):
    """作業の木の rel に commit していない書き替えが無いか。在れば手元の正本を使わない（手元で緩めた検査で照らさない）。
    git で確かめられない時も使わない。"""
    try:
        p = subprocess.run(["git", "-C", root, "status", "--porcelain", "--", rel], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0 and not p.stdout.strip()


def _tmp_file(text, name):
    d = G.tmp_dir("pr_text")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%d-%s.md" % (os.getpid(), name))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)


# ── verdict（レビューの判定の形）──
MARKUP_HEAD = re.compile(r"^[\s>#*_+\-]*")
MARKUP_IN = re.compile(r"\*+|`|(?<![A-Za-z0-9])__?|__?(?![A-Za-z0-9])")   # 語の中の _（session_…）は残す
ANY_SESSION = re.compile(r"session_[A-Za-z0-9]+")
GREEN_RED = re.compile(r"(?<![A-Za-z])(?:green|red)", re.I)


def plain(line):
    """箇条・引用・見出しの頭と、太字・斜体・`…` の印を外した字（崩れた名乗りも同じ行として読む）。"""
    return MARKUP_IN.sub("", MARKUP_HEAD.sub("", line)).strip()


def verdict_form(data):
    """checker の verdict_form の (path, module)。判定の 1 行目の形（LINE1）の正本＝ここに写さない。"""
    tool = _find_sibling(*VERDICT_FORM, data)
    return (tool, G.load_module("af_pr_text_verdict_form", tool)) if tool else ("", None)


def looks_verdict(body, line1):
    """判定のコメントか。正本の 1 行目の形（line1）に合う行、line1 の字の欄（「レビューした窓」「判定」）が窓の id と
    green|red と同じ行に揃う行（太字・箇条・「: 」の抜け・「greenです」の崩れた名乗り）、verdict の見出しで見分ける。
    文中の「レビューした窓は判定: green を付けました」（窓の id が無い）は判定と見なさない。"""
    body = FENCE.sub(" ", COMMENT.sub(" ", body))
    if VERDICT_HEAD.search(body):
        return True
    anchors = re.findall(r"[^\x00-\x7f]+", line1.pattern)
    for ln in body.splitlines():
        if ln.lstrip().startswith(">"):
            continue                 # 引いた行（前の判定の引用）は判定でない
        s = plain(ln)
        if line1.match(s):
            return True
        if anchors and all(a in s for a in anchors) and ANY_SESSION.search(s) and GREEN_RED.search(s):
            return True
    return False


WRITER_LINE = re.compile(r"^\s*書いた窓\s*[:：]\s*(session_[A-Za-z0-9]+)", re.M)
NUMBER_KEYS = ("issue_number", "pullNumber", "pull_number")


def _gh(args):
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=TIMEOUT)


def pr_facts(repo, ti):
    """判定を出す先の PR の (先端の SHA, 書いた窓, 誤り)。GitHub から引く（判定の形の道具が要る材料・写さない）。

    書いた窓は PR 本文の頭の決まった欄 `書いた窓: <session id>`（CONTRIBUTING §1 の PR の型）から読む。
    引けない時は誤りを返す（欠けた材料で判定を通さない）。"""
    if not repo:
        return "", "", "出す先の repo（owner・repo）が道具の入力に無い"
    number = next((ti.get(k) for k in NUMBER_KEYS if ti.get(k)), None)
    try:
        if not number and ti.get("comment_id"):
            p = _gh(["repos/%s/issues/comments/%s" % (repo, ti["comment_id"]), "--jq", ".issue_url"])
            number = p.stdout.strip().rsplit("/", 1)[-1] if p.returncode == 0 else None
        if not number:
            return "", "", "判定を出す先の PR の番号が分からない"
        if not re.fullmatch(r"\d+", str(number).strip()):
            return "", "", "判定を出す先の PR の番号が数でない（%s）" % str(number)[:20]
        p = _gh(["repos/%s/pulls/%s" % (repo, number), "--jq", '.head.sha + "\\n" + (.body // "")'])
    except FileNotFoundError:
        return "", "", "GitHub の CLI（gh）が無く、PR の先端と書いた窓を引けない"
    except (OSError, subprocess.SubprocessError) as e:
        return "", "", "PR を引けなかった（%s）" % e.__class__.__name__
    if p.returncode != 0:
        return "", "", "PR #%s を引けなかった（判定は PR に出す・gh の認証か網を確かめる）: %s" % (
            number, " / ".join((p.stderr or "").strip().splitlines()[-1:]) or "（gh の出力なし）")
    head, _, body = p.stdout.partition("\n")
    m = WRITER_LINE.search(body)
    if not re.fullmatch(r"[0-9a-f]{40}", head.strip()):
        return "", "", "PR #%s の先端の SHA が読めない" % number
    if not m:
        return head.strip(), "", "PR #%s の本文の頭に `書いた窓: <session id>` が無く、別の目を照らせない（PR の型どおりに書く）" % number
    return head.strip(), m.group(1), ""


VERDICT_EVENTS = ("APPROVE", "REQUEST_CHANGES")     # PR の review の判定そのものの印（本文の字によらず判定と見る）


def review_event(data):
    """pull_request_review_write の event が判定の印（APPROVE・REQUEST_CHANGES）ならその字、でなければ ""。"""
    ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    name = str(data.get("tool_name") or "")
    if not (name == "pull_request_review_write" or name.endswith("__pull_request_review_write")):
        return ""
    ev = str(ti.get("event") or "").strip().upper()
    return ev if ev in VERDICT_EVENTS else ""


def check_verdict(body, data, vals=None):
    forced = review_event(data)
    if not forced and "判定" not in body and not VERDICT_HEAD.search(body):
        return []
    try:
        tool, mod = verdict_form(data)
    except BaseException as e:      # noqa: BLE001  読み込みで exit する壊れた道具も（見張りごと落とさない）
        return ["判定の形の道具（checker の verdict_form.py）が壊れた（読めない: %s）" % e.__class__.__name__]
    if not tool:
        return ["判定の形の道具（checker の verdict_form.py）が見つからず、判定かを見分けられない。plugin checker を入れる"
                "（または AF_VERDICT_FORM に path）"]
    if not forced and not looks_verdict(body, mod.LINE1):
        return []
    ti = data.get("tool_input") or {}
    head, writer, err = pr_facts(_repo_name(ti), ti)
    if err:
        return ["判定の材料: " + err]
    try:
        p = _run([sys.executable, tool, _tmp_file(body, "verdict"), "--writer", writer, "--head", head])
    except (OSError, subprocess.SubprocessError) as e:
        return ["判定の形の道具が走らなかった: %s" % e.__class__.__name__]
    if p.returncode == 0:
        return check_ruler(body, data, vals)
    errs = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    if p.returncode != 1 or not errs:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-2:]
        return ["判定の形の道具が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))]
    return ["判定の形: " + e for e in errs]


# ── 物差しを回した跡（review-pr 手順 3・点 4）──
RULER_POINT = re.compile(r"^[\s|>*-]*4\b[^\n]*?(?:pass|fail)\s*[（(](.+)[)）]", re.M)


def _transcripts(data):
    """この窓の会話ログと、その窓の助手の会話ログ（<会話ログ>/subagents/*.jsonl）。"""
    path = data.get("transcript_path") if isinstance(data, dict) else ""
    if not isinstance(path, str) or not os.path.isfile(path):
        return []
    sub = os.path.join(os.path.splitext(path)[0], "subagents")
    return [path] + sorted(glob.glob(os.path.join(sub, "*.jsonl")))


def _rows(path):
    import json
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def is_ruler(block, matchers):
    """道具の呼び出し 1 つが物差しを回した物か（跡の形＝値の表 pr_ruler_trace）。Bash は命令の字に当てず、guard_common.parse_shell
    で走る単純な命令に分け、読み切れない所が無く、前の cd を除いて物差しの命令 1 つだけの時に数える＝`cat scripts/check_all.sh`・
    本文を引く `gh api …; bash scripts/check_all.sh`・`… | tail`・`$(…)` の付いた呼び出しは物差しでない（結果の字に他の命令の
    出力が混ざる）。"""
    if str(block.get("name") or "") != "Bash":
        return G.matches_tool(block, matchers)
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    cmds, unknowns = G.parse_shell(inp.get("command") or "")
    if {u.code for u in unknowns} & RULER_UNREAD:
        return False                    # 読み切れない命令は物差しと数えない（数える側に倒さない）
    while cmds and cmds[0][0] in ("cd", "pushd"):
        cmds = cmds[1:]                 # 前の cd は出力を出さない
    return len(cmds) == 1 and G.matches_tool(dict(block, input=dict(inp, command=" ".join(cmds[0]))), matchers)


def ruler_results(path, matchers):
    """会話ログの、物差しを回した道具の呼び出し（tool_use の id で結ぶ）の、走った結果の字を順に出す。走ったかは
    guard_common.tool_use_ran（誤りなく返った物と、Bash が走って 0 でない数で終わった物＝返りの頭が Exit code N・物差しが赤を
    返した物。拒まれた・hook に止められた・中断した・返りの無い呼び出しは出さない）。ほかの道具の結果（PR 本文を読んだ結果など）は
    出さない＝本文に書かれた物差しの行を跡に数えない。"""
    rows = list(_rows(path))
    ids = [blk["id"] for row in rows for blk in G.tool_uses(row) if blk.get("id") and is_ruler(blk, matchers)]
    out = []
    for i in dict.fromkeys(ids):
        ran, text, _ = G.tool_use_ran(rows, i)
        if ran:
            out.append(text)
    return out


def last_line(text):
    """結果の最後の空でない行（前後の空白と、pytest の囲みの = を外す）。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-1].strip().strip("=").strip() if lines else ""


def check_ruler(body, data, vals=None):
    """点 4 に書いた物差しの最後の行が、この窓（か助手）の物差しを回した道具の結果の最後の行と同じか。同じなら物差しを自分で回した跡。"""
    m = RULER_POINT.search(FENCE.sub(" ", COMMENT.sub(" ", body)))
    if not m or not m.group(1).strip():
        return ["物差しの跡: 点 4（回帰）の値の後に、回した物差しの最後の行（例: `pass（check_all: 緑 (4 本)）`）が無い"]
    want = m.group(1).strip().strip("=").strip()
    matchers, bad = G.tool_matchers(vals if vals is not None else G.values(data), "pr_ruler_trace")
    if not matchers:
        return ["物差しの跡: 物差しを回した道具の呼び出しの形（値の表 guard.pr_ruler_trace）が無く、跡を照らせない%s" % (
            "（%s）" % "・".join(bad[:2]) if bad else "")]
    logs = _transcripts(data)
    if not logs:
        return ["物差しの跡: この窓の会話ログが読めず、物差しを回した跡を照らせない"]
    for path in logs:
        try:
            if any(last_line(r) == want for r in ruler_results(path, matchers)):
                return []
        except OSError:
            continue
    return ["物差しの跡: 点 4 の「%s」が、この窓と助手が物差しを回した道具（値の表 guard.pr_ruler_trace の形・物差しの命令だけの"
            "呼び出し）の結果の最後の行と合わない（PR 本文や他の道具・他の命令の出力に在る字は数えない。物差しを PR の先端で"
            "それだけで回し、結果の最後の行をそのまま書く）%s" % (want[:60], "。読めない形: " + "・".join(bad[:2]) if bad else "")]


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


def check_cleanup(body, repo, data, vals):
    if repo and _matches(vals.get("pr_cleanup_exempt_repos"), repo):
        return []
    body = QUOTE.sub("", FENCE.sub(" ", COMMENT.sub(" ", body)))   # 注記（雛形の説明）・コードの囲み・引用の中は数えない
    if NOT_NEEDED.search(body):
        return check_not_needed(repo, data)
    tpl = _find_sibling(*CLEANUP_TEMPLATE, data)
    if not tpl:
        return ["整地の雛形（dev-flow の preimpl-cleanup の 整地受領証.template.md）が見つからず、欄を確かめられない。"
                "plugin dev-flow を入れる（または AF_CLEANUP_TEMPLATE に path）"]
    try:
        heads, holders = template_parts(tpl)
    except (OSError, ValueError) as e:
        return ["整地の雛形が読めない: %s" % e]
    out = []
    lack = [("%s. %s" % (no, name)) for no, name in heads
            if not re.search(r"^#{1,6}\s*(?:%s\.\s*)?%s" % (no, re.escape(name)), body, re.M)]
    if lack:
        out.append("整地の見出しが無い: %s（雛形の見出し %d つ）" % ("・".join(lack), len(heads)))
    left = [h for h in holders if h in body]
    if left:
        out.append("整地の雛形の `〔…〕` が残っている: %s" % "・".join(h + "…" for h in left[:3]))
    return out


BEHAVIOR_FILE = re.compile(r"\.(?:py|mjs|cjs|js|ts|sh)$|(?:^|/)SKILL\.md$|(?:^|/)hooks/|(?:^|/)(?:核|細目|振る舞い)\.md$")


def changed_files(repo, ti):
    """PR の差分の file の並びと誤り。直す時は PR の番号から、作る時は base...head の比べから引く。"""
    number = next((ti.get(k) for k in NUMBER_KEYS if ti.get(k)), None)
    if number:
        if not re.fullmatch(r"\d+", str(number).strip()):
            return [], "PR の番号が数でない"
        args = ["repos/%s/pulls/%s/files" % (repo, number), "--paginate", "--jq", ".[].filename"]
    elif ti.get("head") and ti.get("base"):
        args = ["repos/%s/compare/%s...%s" % (repo, ti["base"], ti["head"]), "--jq", ".files[].filename"]
    else:
        return [], "PR の番号も head・base も道具の入力に無い"
    try:
        p = _gh(args)
    except FileNotFoundError:
        return [], "GitHub の CLI（gh）が無い"
    except (OSError, subprocess.SubprocessError) as e:
        return [], e.__class__.__name__
    if p.returncode != 0:
        return [], " / ".join((p.stderr or "").strip().splitlines()[-1:]) or "gh が失敗した"
    return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()], ""


def check_not_needed(repo, data):
    """「整地: 不要」は振る舞いの file（コード・SKILL.md・hooks・核／細目／振る舞い）を触らない PR だけ。"""
    if not repo:
        return []                       # 出す先の無い入力は道具の側が断る（GitHub へ出ない）
    files, err = changed_files(repo, (data.get("tool_input") or {}))
    if err:
        return ["「整地: 不要」の訳を照らす材料（PR の差分の file）を引けない: %s" % err]
    hit = [f for f in files if BEHAVIOR_FILE.search(f)]
    if hit:
        return ["「整地: 不要」と書いたが、振る舞いの file を触る: %s%s（4 欄を書く）" % (
            "・".join(hit[:4]), "…" if len(hit) > 4 else "")]
    return []


# ── words（PR の題・本文の言葉）──
def visible_prose(body, keep=()):
    """数えない所（頭の決まった欄・コード・URL・注記・keep に当たる行）を除いた文。"""
    body = FENCE.sub(" ", COMMENT.sub(" ", body))
    lines = [ln for ln in body.splitlines() if not HEAD_FIELD.match(ln) and not any(k.search(plain(ln)) for k in keep)]
    return URL.sub(" ", INLINE.sub(" ", "\n".join(lines)))


def check_words(texts, repo, vals, keep=()):
    if repo and _matches(vals.get("pr_words_exempt_repos"), repo):
        return []
    out = []
    for where, text in texts:
        ids = list(dict.fromkeys(SESSION_ID.findall(visible_prose(text, keep))))
        if ids:
            out.append("%sに窓の id がそのまま %d 個: %s" % (where, len(ids), "・".join(ids[:3]) + ("…" if len(ids) > 3 else "")))
    return out


# ── public（公開の repo に置かない物）──
WORKFLOW_DIR = os.path.join(".github", "workflows")
DENY_FILE = re.compile(r"^\s*deny-words-file\s*:\s*[\"']?([^\s\"'#]+)", re.M)
USES_GUARD = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*[\"']?[^\s\"']*public-guard(?:@[^\s\"']*)?[\"']?\s*$", re.M)
YAML_COMMENT = re.compile(r"(?:^|(?<=\s))#.*$", re.M)
GITHUB_REMOTE = re.compile(r"github\.com[/:]([^/\s:]+/[^/\s]+?)(?:\.git)?/?$")


def remote_repo(url):
    """remote の URL（https・ssh の scp の形〔ホスト名の後が「:」〕・ssh:// の形）から owner/repo。GitHub でなければ ""。"""
    m = GITHUB_REMOTE.search((url or "").strip())
    return m.group(1) if m else ""


def workflow_lines(raw):
    """workflow の YAML の、注（`#` から行末）を外した字。字の中の `#`（引用の中）は残らないことがあるが、注を数えない側に倒す。"""
    return YAML_COMMENT.sub("", raw)


def _checkout_of(repo, data, root=None):
    """窓の repo（push では push する dir＝root）の取り出しが owner/repo なら、その根。"""
    root = root or G.project_dir(data)
    if not root or not repo:
        return ""
    try:
        url = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return top if top and remote_repo(url).lower() == repo.lower() else ""


def visibility(repo):
    """GitHub から引いた repo の公開か（True／False）。引けなければ None。"""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        return None
    try:
        p = _gh(["repos/%s" % repo, "--jq", ".private"])
    except (OSError, subprocess.SubprocessError):
        return None
    v = p.stdout.strip() if p.returncode == 0 else ""
    return {"false": True, "true": False}.get(v)


def public_target(repo, data, vals, root=None):
    """(公開か, 取り出しの根, 置かない語の表の path, 誤り)。公開かは GitHub の repo の visibility が正本（取り出しの有無に頼らない）。
    引けない時だけ取り出しの workflow と値の表 public_repos_extra で見分け、それでも決まらなければ誤り（照らせない文は出さない）。"""
    top = _checkout_of(repo, data, root)
    vis = visibility(repo)
    words = ""
    if top:
        for wf in sorted(glob.glob(os.path.join(top, WORKFLOW_DIR, "*.y*ml"))):
            try:
                with open(wf, encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue
            raw = workflow_lines(raw)
            if USES_GUARD.search(raw):
                m = DENY_FILE.search(raw)
                words = os.path.join(top, m.group(1)) if m else ""
                if vis is None:
                    return True, top, words, ""
                break
    if vis is not None:
        return vis, top, words, ""
    if repo and _matches(vals.get("public_repos_extra"), repo):
        return True, top, "", ""
    if not repo:
        return False, top, "", ""       # 出す先の無い入力は道具の側が断る（GitHub へ出ない）
    return False, top, "", "出す先の repo %s が公開かを GitHub から引けず、照らせない（gh の認証か網を確かめる）" % (repo or "（無い）")


def find_public_guard(top=""):
    """public-guard/guard.py の path か ""（土台の repo の根に在る・plugin の外）。探す順: 環境変数 → 出す先の repo の取り出し
    （土台そのものへ出す時）→ 土台の共通の在り処探し（guard_common.foundation_file）。"""
    env = os.environ.get("AF_PUBLIC_GUARD") or ""
    if env:
        return env if os.path.isfile(env) else ""
    rel = os.path.join("public-guard", "guard.py")
    if top and os.path.isfile(os.path.join(top, rel)) and _committed(top, "public-guard"):
        return os.path.join(top, rel)
    return G.foundation_file(rel)

def check_public(texts, repo, data, vals, root=None):
    is_public, top, words, err = public_target(repo, data, vals, root)
    if err:
        return [err]
    if not is_public:
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


# ── push（Bash の git push で出す commit の説明と名義）──
def push_dirs(cmd, data):
    """(push しうる dir の絶対の並び, 読めない理由)。"""
    dirs, _, bad = git_push(cmd)
    base = (data.get("cwd") if isinstance(data.get("cwd"), str) else "") or G.project_dir(data)
    return list(dict.fromkeys(os.path.normpath(_join(base, d)) if d else base for d in dirs or [""])), bad


def push_texts(d):
    """(owner/repo, [(どこ, 字)], 誤り)。push する commit（どの remote の枝にも無い物）の説明と名義。"""
    try:
        url = subprocess.run(["git", "-C", d, "remote", "get-url", "origin"], capture_output=True, text=True, timeout=10)
        log = subprocess.run(["git", "-C", d, "log", "--format=%an <%ae>%n%cn <%ce>%n%B", "HEAD", "--not", "--remotes"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return "", [], "push する commit を読めない（%s）" % e.__class__.__name__
    if url.returncode != 0:
        return "", [], ""               # repo でない・origin の無い所の push は GitHub の origin へ出ない（git の側が断る）
    if log.returncode != 0:
        return "", [], "push する commit を読めない: %s" % " / ".join((log.stderr or url.stderr or "").strip().splitlines()[-1:])
    repo = remote_repo(url.stdout)
    if not repo:
        return "", [], ""
    return repo, ([("commit の説明と名義", log.stdout)] if log.stdout.strip() else []), ""


# ── board（2 アカウントをまたぐ連絡板）──
BOARD_TITLE = "連絡板"
BOARD_FORM = re.compile(r"冒頭の\s*1\s*行は[^`\n]*`([^`\n]+)`")


def _board(repo, number):
    """連絡板の issue なら (本文, "")。別の issue なら ("", "")。引けなければ ("", 誤り)。"""
    try:
        p = _gh(["repos/%s/issues/%s" % (repo, number), "--jq", '.title + "\n" + (.body // "")'])
    except (OSError, subprocess.SubprocessError) as e:
        return "", "連絡板かを引けない（%s）" % e.__class__.__name__
    if p.returncode != 0:
        return "", "連絡板かを引けない: %s" % (" / ".join((p.stderr or "").strip().splitlines()[-1:]) or "gh が失敗した")
    title, _, body = p.stdout.partition("\n")
    return (body, "") if title.strip().startswith(BOARD_TITLE) else ("", "")


def form_pattern(form):
    """連絡板の本文の `窓: <session id> アカウント: <Javis|UTC>` を正規表現にする（形は連絡板の本文が正本）。"""
    out, pos = "", 0
    for m in re.finditer(r"<([^>]+)>", form):
        out += re.escape(form[pos:m.start()])
        inner = m.group(1)
        out += r"session_[A-Za-z0-9]+" if "session" in inner else "(?:%s)" % "|".join(re.escape(x.strip()) for x in inner.split("|"))
        pos = m.end()
    return re.compile("^" + out + re.escape(form[pos:]) + r"\s*$")


BOARD_REPO = re.compile(r"またぐ連絡[^\n]*?`([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)`")


def board_repo():
    """(連絡板の在る repo, 誤り)。正本は細目 §8「またぐ連絡」。読めない・形が合わない時は誤り（黙って照らしを飛ばさない）。"""
    path = G.sibling_plugin_file("core", "細目.md")
    if not path:
        return "", "連絡板の repo の正本（core の 細目.md）が見つからず、連絡板へ出す文かを見分けられない。plugin core を同じ版で入れる"
    try:
        with open(path, encoding="utf-8") as f:
            m = BOARD_REPO.search(f.read())
    except (OSError, UnicodeDecodeError) as e:
        return "", "連絡板の repo の正本（core の 細目.md）が読めない（%s）" % e.__class__.__name__
    if not m:
        return "", "細目.md の「またぐ連絡」に連絡板の repo（`owner/repo`）が無く、連絡板へ出す文かを見分けられない"
    return m.group(1), ""


def check_board(kind, body, repo, ti):
    """連絡板の repo（細目 §8）へ出す文: 連絡板のコメントは本文の「書き方」の冒頭の 1 行の形。新しい issue を立てない（1 本だけ）。"""
    if not repo:
        return []                       # 出す先の無い入力は道具の側が断る（GitHub へ出ない）
    board_at, err = board_repo()
    if err:
        return [err]
    if repo.lower() != board_at.lower():
        return []
    if kind == "issue" and str(ti.get("method") or "create") == "create":
        try:
            p = _gh(["repos/%s/issues?state=open&per_page=100" % repo, "--paginate", "--jq", ".[].title"])
        except (OSError, subprocess.SubprocessError) as e:
            return ["連絡板の issue が在るかを引けない（%s）。引けないまま新しい issue を立てない" % e.__class__.__name__]
        if p.returncode != 0:
            return ["連絡板の issue が在るかを引けない: %s。引けないまま新しい issue を立てない" % (
                " / ".join((p.stderr or "").strip().splitlines()[-1:]) or "gh が失敗した")]
        if any(t.strip().startswith(BOARD_TITLE) for t in p.stdout.splitlines()):
            return ["この repo には連絡板の issue が在る。アカウントをまたぐ連絡は新しい issue を立てず、連絡板へ 1 コメントで書く"]
        return []
    number = ti.get("issue_number")
    if kind != "comment" or not number or not re.fullmatch(r"\d+", str(number).strip()):
        return []
    board, err = _board(repo, number)
    if err:
        return [err]
    if not board:
        return []
    m = BOARD_FORM.search(board)
    if not m:
        return ["連絡板の本文に冒頭の 1 行の形（「冒頭の 1 行は … `…`」）が無く、照らせない（連絡板の書き方を直す）"]
    first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if not form_pattern(m.group(1)).match(first):
        return ["連絡板のコメントの冒頭の 1 行が `%s` の形でない: %s" % (m.group(1), first[:50])]
    return []


HOW = {
    "broken": "一時の置き場（TMPDIR・AF_GUARD_TMP）に書けるか・入れた plugin が揃っているかを確かめ、直してから出し直す。"
              "直せない時は止めた文を添えて親の窓へ返す（見張りを外して出さない）。",
    "verdict": "判定のコメントは skill `checker:review-pr` の「判定の形」で書き直す（形の正本はその SKILL.md と verdict_form.py・"
               "ここに写さない）。`python3 <verdict_form.py> <下書き> --writer <書いた窓> --head <PR の先端>` が exit 0 になってから出す。",
    "cleanup": "PR 本文の「何をどう変えたか」の後に `## 整地（根治の 4 段）` を置き、skill `dev-flow:preimpl-cleanup` の雛形の 4 つの見出しで"
               "書く（中身は頭が書く・`〔…〕` を残さない）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）なら、4 欄の代わりに "
               "`整地: 不要（<なぜ要らないか>）` の 1 行を書く（訳はレビューが照らす）。",
    "words": "窓の id は、読む人が開けるリンク（https://claude.ai/code/<id>）にして役の名を添える（例: 「直す窓（リンク）」）か、役の名だけに"
             "する。決まった欄（親窓・書いた窓）とコードの囲みの中は数えない。",
    "board": "連絡板の本文の「書き方」のとおり、冒頭の 1 行を書き、1 コメントに 1 件で書く。新しい issue は立てない。",
    "public": "当たった所を書き直す（秘密・個人の情報は消す・作り物の例は example.com などにする・置かない語と顧客の語は一般の言葉に言い換える）。"
              "GitHub の本文は書き替えても古い版が編集の履歴に公開で残るので、出す前に直す。",
}
HEAD = {
    "broken": "照らしが壊れた",
    "verdict": "レビューの判定の形が崩れている",
    "cleanup": "PR 本文の整地の欄が雛形と合わない",
    "words": "PR の題・本文に AI の中の呼び名が出ている",
    "board": "連絡板の書き方と合わない",
    "public": "公開の repo に置かない物がある",
}


def findings(data, vals):
    """[(札, 文)]。"""
    ti = data.get("tool_input")
    kind = tool_kind(data.get("tool_name"), ti)
    if not kind or not isinstance(ti, dict):
        return []
    if kind == "push":
        dirs, bad = push_dirs(ti.get("command") or "", data)
        if bad:
            return [("public", "push する repo を読み切れず、公開の検査を当てられない（%s）。cd・-C の先を字で書き、push を"
                               "それだけの命令で走らせる" % bad)]
        out = []
        for d in dirs:                  # push しうる repo の全部に公開の検査を当てる
            repo, texts, err = push_texts(d)
            out += [("public", err)] if err else [("public", m) for m in check_public(texts, repo, data, vals, d)] if texts else []
        return list(dict.fromkeys(out))
    repo = _repo_name(ti)
    title = ti.get("title") if isinstance(ti.get("title"), str) else ""
    body = ti.get("body") if isinstance(ti.get("body"), str) else ""
    texts = []
    if kind == "commit":
        texts = [(where, ti[k]) for k, where in COMMIT_FIELDS if isinstance(ti.get(k), str) and ti[k].strip()]
        return [("public", m) for m in check_public(texts, repo, data, vals)] if texts else []
    if title.strip():
        texts.append(("PR の題" if kind == "pr" else "issue の題", title))
    if body.strip():
        texts.append(({"pr": "PR の本文", "comment": "コメント", "issue": "issue の本文"}[kind], body))
    if not texts and not (kind == "comment" and review_event(data)):
        return []
    out = []
    keep = ()
    if kind == "comment" and (body.strip() or review_event(data)):
        out += [("verdict", m) for m in check_verdict(body, data, vals)]
        try:
            tool, mod = verdict_form(data) if "判定" in body else ("", None)
        except BaseException:      # noqa: BLE001  壊れた道具は上の verdict が名指す
            mod = None
        if mod is not None and hasattr(mod, "LINE1") and hasattr(mod, "OTHER_EYE"):      # 判定の 1 行目の名乗りと点 3 の「書いた窓 … ≠ この窓」は窓の id を書く欄
            keep = (mod.LINE1, re.compile(mod.OTHER_EYE.pattern.strip("^$")))
    if kind in ("comment", "issue"):
        out += [("board", m) for m in check_board(kind, body, repo, ti)]
    if kind == "pr" and body.strip():
        out += [("cleanup", m) for m in check_cleanup(body, repo, data, vals)]
    out += [("words", m) for m in check_words(texts, repo, vals, keep)]
    out += [("public", m) for m in check_public(texts, repo, data, vals)]
    return out


def check(data, vals):
    """止めるなら理由、通すなら ""。見る道具の照らしの中で何かが壊れたら、黙って通さず止める（guard の入口は例外を通す側に倒すため）。"""
    try:
        found = findings(data, vals)
    except Exception as e:      # noqa: BLE001
        if not tool_kind(data.get("tool_name"), data.get("tool_input")):
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
