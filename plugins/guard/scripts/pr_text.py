"""PreToolUse — PR の題・本文と、PR・issue へのコメント・MCP から出す commit の説明を、公開の repo なら GitHub へ出す前に公開の検査に通す。

意図: 公開の repo に置かない物（秘密・個人の情報・顧客の語・置かない語）を、GitHub に出る前に照らす（核 §1-4。GitHub の本文は
書き替えても古い版が編集の履歴に公開で残る）。止まるのは AI の道具の呼び出しだけ。人の操作は何も止めない。

見る道具: 名の末尾（MCP の server の名は問わない）で見分ける。
  PR     … create_pull_request・update_pull_request（題・本文）
  コメント … add_issue_comment・update_issue_comment・add_reply_to_pull_request_comment・pull_request_review_write・
             add_comment_to_pending_review（本文）
  issue  … issue_write（題・本文）
  commit … merge_pull_request（commit_title・commit_message）・push_files・create_or_update_file・delete_file（message）
           ＝MCP から出す commit の説明。公開の検査だけを当てる
照らす物（見分けは正本を直に読む・呼ぶ。ここに決まりを写さない）:
  public  … 公開の repo（窓の repo の取り出しの workflow が action public-guard を呼ぶ／値の表 public_repos_extra）なら、
            題・本文を `public-guard/guard.py --text` に渡す（呼び口の見分けと置かない語の表は workflow の読み手
            public-guard/workflow_reader.py が正本: PR・push で走る job の step の呼び口だけを数え、語の表は全部の呼び口の with: の
            deny-words-file の和）。当たれば止める。
            公開かを決められない時は公開として照らす（既定で止める側）: 出す先の取り出しが手元に無ければ GitHub の記録
            （gh api repos/<owner>/<repo> の visibility）を引き、private・internal の時だけ公開でないと読む（引けない・答えが
            分からない時は公開）。取り出しに開けない・壊れた workflow が 1 つでも在れば公開として照らす（その分の語の表は読めない）
            検査が見つからない・壊れた時も止める（公開の repo へは、照らせない文を出さない）
            開けない・壊れた workflow は出した後（PostToolUse の notice）にも名と訳を知らせる
公開の検査は外す口を持たない（直すのは文の方）。
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

import guard_common as G

HOOKS = {"pre": "check", "post": "notice"}

TIMEOUT = 30
SHOWN = 12

PR_TOOLS = ("create_pull_request", "update_pull_request")
COMMENT_TOOLS = ("add_issue_comment", "update_issue_comment", "add_reply_to_pull_request_comment",
                 "pull_request_review_write", "add_comment_to_pending_review")
ISSUE_TOOLS = ("issue_write",)
COMMIT_TOOLS = ("merge_pull_request", "push_files", "create_or_update_file", "delete_file")
COMMIT_FIELDS = (("commit_title", "commit の題"), ("commit_message", "commit の説明"), ("message", "commit の説明"))

URL = re.compile(r"https?://\S+")



def tool_kind(name):
    name = str(name or "")
    for kind, names in (("pr", PR_TOOLS), ("comment", COMMENT_TOOLS), ("issue", ISSUE_TOOLS), ("commit", COMMIT_TOOLS)):
        if any(name == n or name.endswith("__" + n) for n in names):
            return kind
    return ""


def _repo_name(ti):
    owner, repo = str(ti.get("owner") or "").strip(), str(ti.get("repo") or "").strip()
    return "%s/%s" % (owner, repo) if owner and repo else ""


def _matches(patterns, repo):
    """repo（owner/repo）の名の全体が、値の表の正規表現のどれかに当たるか（大小を問わない＝GitHub の名と同じ）。
    一部に当たるだけでは当てない（`o/r` が `o/r-fork`・`xo/r` を外さない）。owner ごとなら `^o/.*$` と書く。"""
    for p in patterns or []:
        try:
            if isinstance(p, str) and p and re.fullmatch(p, repo, re.I):
                return True
        except re.error:
            continue
    return False


def _repo_rows(key, data, vals):
    """値の表 guard の repo の名の鍵（型 repo_names）の (名の全体の形の行, 形の違う行)。
    値の表の照らしは形の違う行が 1 つでも在ると鍵ごと落とす（既定の [] に戻る）ので、生の行を読み、行ごとに分ける
    （形の違う行が混じっても、同じ並びの正しい行は効く）。生の表が読めない時は vals の値を使う。"""
    raw = G.table("guard", data or {}).get(key)
    rows = raw if isinstance(raw, list) else (vals.get(key) or [])
    bad = G.SV.bad_repo_names(rows)
    return [r for r in rows if r not in bad], bad


def _public_extra(repo, data, vals):
    """値の表 public_repos_extra に repo が在るか。名の全体の形の行は全体の一致で当てる。形の違う行は、名の一部にでも
    当たれば公開と見る（公開の照らしを黙って外さない＝安全の守り。形の違いは値の表の照らしが名指す）。"""
    good, bad = _repo_rows("public_repos_extra", data, vals)
    if _matches(good, repo):
        return True
    for p in bad:
        try:
            if isinstance(p, str) and p and re.search(p, repo, re.I):
                return True
        except re.error:
            continue
    return False


def _tmp_file(text, name):
    d = G.tmp_dir("pr_text")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "%d-%s.md" % (os.getpid(), name))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)


# ── 公開の repo の見分け（workflow の読み手）──
WORKFLOW_DIR = os.path.join(".github", "workflows")
# 取り出しの origin の URL（https・ssh://・scp の形 <利用者>@github.com:o/r）から owner/repo を読む。host は github.com だけ。
REMOTE = re.compile(r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?github\.com(?::\d+)?/|(?:[^@/:]+@)?github\.com:)"
                    r"([^/\s]+)/([^/\s]+?)(?:\.git)?/*$", re.I)


def _reader():
    """workflow の読み手（正本 public-guard/workflow_reader.py・見回りと手元の検査も同じ物を読む）。見つからなければ例外
    （公開の repo の取り出しで照らせない時は、黙って通さず止める＝check の broken）。"""
    path = G.foundation_file(os.path.join("public-guard", "workflow_reader.py"))
    if not path:
        raise RuntimeError("workflow の読み手（public-guard/workflow_reader.py）が見つからない" + G.miss_note())
    return G.load_module("af_pr_text_workflow_reader", path)


def _foundation():
    """土台の repo の名（owner/repo）。正本は workflow の読み手の FOUNDATION（写さない）。読めなければ ""。"""
    try:
        return str(_reader().FOUNDATION)
    except Exception:  # noqa: BLE001  読めない時は呼ぶ側が多く照らす向きに倒す
        return ""


def calls_public_guard(raw, foundation=None):
    """workflow の text に、数える public-guard の呼び口（PR・push で走る job の step）が在るか。見分けは読み手の counted。"""
    found = _foundation() if foundation is None else foundation
    return bool(_reader().counted(raw, found))


def github_repo(url):
    """git の remote の URL の owner/repo（github.com のでなければ ""）。末尾の .git・/ は外す。"""
    m = REMOTE.match(str(url or "").strip())
    return "%s/%s" % m.groups() if m else ""


def _checkout_of(repo, data):
    """窓の repo の取り出しが owner/repo なら、その根。origin の URL を owner/repo に読み、名の全体で比べる（GitHub と同じく
    大小を問わない）。"""
    root = G.project_dir(data)
    if not root or not repo:
        return ""
    try:
        url = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
        top = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return top if top and github_repo(url).lower() == repo.lower() else ""


def _broken_form(reader, raw):
    """workflow の字が在るのに、読み手が jobs の形を読めない訳（読めれば ""）。読み手は読めない形を空の dict にするので、
    黙って「呼び口が無い」と読まない。コメントと空行だけの file は壊れていない（中身が無い）。"""
    body = [ln for ln in raw.splitlines() if ln.strip() and not ln.strip().startswith("#") and ln.strip() not in ("---", "...")]
    if not body:
        return ""
    wf = reader.load(raw)
    if not wf:
        return "壊れている（読み手が workflow の形を読めない）"
    if not isinstance(wf.get("jobs"), dict):
        return "壊れている（jobs が無い・形が違う）"
    return ""


def _scan(top, unread):
    """(数える呼び口が在るか, 置かない語の表の path の並び)。取り出しの workflow の全部を読み手で読み、数える呼び口
    （PR・push で走り、job と step の if: が字どおりの false でない）が 1 つでも在れば真。語の表は数える呼び口の全部の和。
    開けない・壊れた workflow は黙って飛ばさず、unread に (path, 訳) で積む（公開かを決められていない印）。
    utf-8 で読めない字の workflow は例外のまま（check が照らしの壊れとして止める・今までどおり）。"""
    reader, found, words, public = None, None, [], False
    for wf in sorted(glob.glob(os.path.join(top, WORKFLOW_DIR, "*.y*ml"))):
        try:
            with open(wf, encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            unread.append((wf, "開けない（%s）" % (e.strerror or e.__class__.__name__)))
            continue
        if reader is None:
            reader = _reader()
            found = str(getattr(reader, "FOUNDATION", "") or "")
        broken = _broken_form(reader, raw)
        if broken:
            unread.append((wf, broken))
            continue
        if reader.counted(raw, found):
            public = True
            words += [os.path.join(top, n) for n in reader.deny_words_files(raw, found)
                      if os.path.join(top, n) not in words]
    return public, words


# GitHub の記録の repo の見え方（visibility が無い古い答えは private の真偽から読む）
VISIBILITY_JQ = '.visibility // (if .private == true then "private" elif .private == false then "public" else "" end)'


def _gh(args):
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=TIMEOUT)


def _hidden_on_github(repo):
    """GitHub の記録が repo を公開でない（private・internal）と言い切るか。引けない・gh が無い・答えが分からない時は偽
    （＝公開として照らす側）。"""
    try:
        p = _gh(["repos/%s" % repo, "--jq", VISIBILITY_JQ])
    except (OSError, subprocess.SubprocessError):
        return False
    return p.returncode == 0 and p.stdout.strip().lower() in ("private", "internal")


def public_target(repo, data, vals, unread=None):
    """(公開か, 取り出しの根, 置かない語の表の path の並び)。決められない時は公開（既定で止める側）:
    - 取り出しが在る: workflow に数える呼び口が在れば公開。開けない・壊れた workflow が 1 つでも在れば、それが呼び口かを
      決められないので公開（語の表はその分を読めない）。unread（渡されれば）に (path, 訳) を積む。
    - 取り出しが無い: GitHub の記録で private・internal と言い切れる時だけ公開でない。名が無い・引けない時は公開。
    どちらでも公開と決まらなければ、値の表 public_repos_extra に在る時は公開。"""
    top = _checkout_of(repo, data)
    if top:
        bad = []
        public, words = _scan(top, bad)
        if unread is not None:
            unread.extend(bad)
        if public or bad:
            return True, top, words
    elif not repo or not _hidden_on_github(repo):
        return True, top, []
    if repo and _public_extra(repo, data, vals):
        return True, top, []
    return False, top, []


def find_public_guard(top=""):
    """public-guard/guard.py の path か ""（土台の repo の根に在る・plugin の外）。探す順: 環境変数 → 出す先の repo の取り出し
    （土台そのものへ出す時）→ 土台の共通の在り処探し（guard_common.foundation_file）。"""
    env = os.environ.get("AF_PUBLIC_GUARD") or ""
    if env:
        return env if os.path.isfile(env) else ""
    rel = os.path.join("public-guard", "guard.py")
    if top and os.path.isfile(os.path.join(top, rel)):
        return os.path.join(top, rel)
    return G.foundation_file(rel)

def check_public(texts, repo, data, vals):
    is_public, top, words = public_target(repo, data, vals)
    if not is_public:
        return []
    missing = [w for w in words if not os.path.isfile(w)]
    if missing:
        return ["公開の repo の workflow が名指す置かない語の表 %s が無く、照らせない（CI も同じ時に止まる）。表を置くか"
                "workflow を直す" % os.path.relpath(missing[0], top or None)]
    tool = find_public_guard(top)
    if not tool:
        return ["公開の repo だが、公開の検査（土台の public-guard/guard.py）が見つからず照らせない。土台の marketplace を"
                "入れ直す（または AF_PUBLIC_GUARD に path）" + G.miss_note()]
    cmd = [sys.executable, tool]
    for i, (where, text) in enumerate(texts):
        cmd += ["--text", "%s=%s" % (where, _tmp_file(text, "public%d" % i))]
    if words:
        # 数える呼び口が 2 つ以上の表を名指せば、全部の和で照らす（guard.py の --deny-words-file は 1 つ）
        joined = words[0] if len(words) == 1 else _tmp_file("\n".join(_read(w) for w in words), "deny-words")
        cmd += ["--deny-words-file", joined]
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



def notice(data, vals):
    """PostToolUse: 出した先の repo の取り出しに、開けない・壊れた workflow があれば名と訳を知らせる（止めない＝止めに変えるかは
    オーナーの同意を待つ）。出す前は公開として照らした（public_target）が、その workflow が名指す置かない語の表は読めていない。"""
    kind = tool_kind(data.get("tool_name"))
    ti = data.get("tool_input")
    if not kind or not isinstance(ti, dict):
        return ""
    top = _checkout_of(_repo_name(ti), data)
    unread = []
    if top:
        _scan(top, unread)
    if not unread:
        return ""
    lines = ["[guard] GitHub へ出した文の出す先 %s の取り出しに、読めない workflow がある（知らせるだけ・この知らせでは止めていない）。"
             "公開の検査を呼ぶかを決められないので公開として照らしたが、その workflow が名指す置かない語の表は読めていない:" % _repo_name(ti)]
    lines += ["- %s — %s" % (os.path.relpath(p, top) if top else p, why) for p, why in unread[:SHOWN]]
    lines.append("直し方: workflow を開ける・読める形に直す（GitHub も壊れた workflow は走らせない）。公開の repo なら、出した文に"
                 "置かない物が無いかを公開の検査（public-guard/guard.py --text）で確かめ、当たれば書き直す。")
    return "\n".join(lines)

HOW = {
    "broken": "一時の置き場（TMPDIR・AF_GUARD_TMP）に書けるか・入れた plugin が揃っているかを確かめ、直してから出し直す。"
              "直せない時は止めた文を添えて親の窓へ返す（見張りを外して出さない）。",
    "public": "当たった所を書き直す（秘密・個人の情報は消す・作り物の例は example.com などにする・置かない語と顧客の語は一般の言葉に言い換える）。"
              "GitHub の本文は書き替えても古い版が編集の履歴に公開で残るので、出す前に直す。",
}
HEAD = {
    "broken": "照らしが壊れた",
    "public": "公開の repo に置かない物がある",
}


def findings(data, vals):
    """[(札, 文)]。"""
    kind = tool_kind(data.get("tool_name"))
    ti = data.get("tool_input")
    if not kind or not isinstance(ti, dict):
        return []
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
    if not texts:
        return []
    return [("public", m) for m in check_public(texts, repo, data, vals)]


def check(data, vals):
    """止めるなら理由、通すなら ""。見る道具の照らしの中で何かが壊れたら、黙って通さず止める（guard の入口は例外を通す側に倒すため）。"""
    try:
        found = findings(data, vals)
    except Exception as e:      # noqa: BLE001
        if not tool_kind(data.get("tool_name")):
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
    lines.append("公開の検査は外す口を持たない（直すのは文の方）。")
    return "\n".join(lines)
