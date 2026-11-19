"""PreToolUse — PR の題・本文と、PR・issue へのコメントを、GitHub へ出す前に照らす。崩れていれば AI だけを止めて書き直させる。
PostToolUse — 正本が読めず照らさずに通した時だけ（判定の道具が無い・古い／整地の雛形が無い・読めない）、その事を知らせる（止めない）。

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
照らす物（見分けは正本を直に読む・呼ぶ。ここに決まりを写さない）:
  verdict … （材料は記録から: 出す先の PR の先端と、PR の commit 全部の `Claude-Session:` の窓（書いた窓の組）を gh で引き
            --head・--writer で、判定を出す窓の本物の id を窓の環境の記録（CLAUDE_CODE_REMOTE_SESSION_ID）から読み --reviewer で
            渡す。本文の `書いた窓:`・判定の 1 行目の名乗りは手で書いた写しで、照らされる側。どれかが引けなければ止める）
            コメントが判定か（`verdict_form.py --looks`）と判定の形（`verdict_form.py`）を、checker の正本に直に聞く
            （見分けも形もここに写さない）。赤なら止める。判定と見分けた後に道具が壊れた時も止める。道具が見つからない・古い版で
            `--looks` に答えない時は判定かどうか見分けられないので止めず（ふつうのコメントまで止めない）、出した後に知らせる
  cleanup … PR の本文（本文を渡す時だけ）に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し
            （`## 1.`〜`## 4.`。見出しの名は雛形から読む）が全部在り、雛形の `〔…〕` が残っていない事。整地の要らない PR
            （振る舞いを変えない: 誤字・記録だけ・版だけ等）は本文に `整地: 不要（<訳>）` の 1 行を書く（訳はレビューが照らす）
            雛形が見つからない・読めない時は止めず（PR 本文まで止めない）、出した後に知らせる
  words   … PR の題・本文に、窓の id（`session_01…`）がそのまま出ていない事。本文の頭の欄の塊（1 行目から最初の空行まで）の
            窓の id を書く欄（親窓・書いた窓）・コードの囲み・`…` の字・URL の中は数えない（job・検査 等の欄や、頭の塊の
            外で同じ字で始まる行は数える）
  public  … 公開の repo（窓の repo の取り出しの workflow が action public-guard を呼ぶ／値の表 public_repos_extra）なら、
            題・本文を `public-guard/guard.py --text` に渡す（置かない語の表はその workflow の deny-words-file）。当たれば止める。
            検査が見つからない・壊れた時も止める（公開の repo へは、照らせない文を出さない＝核 §1 の公開の守り。安全の守りなので
            判定の道具・整地の雛形と違い、知らせるだけにしない）
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

HOOKS = {"pre": "check", "post": "notice"}

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

NOT_NEEDED = re.compile(r"^\s*(?:[-*]\s*)?\**整地\**\s*[:：]\s*(?:不要|要らない)\s*[（(]\s*(?![<＜〔])\S[^)）]*[)）]", re.M)
TEMPLATE_HEAD = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)
PLACEHOLDER = re.compile(r"〔[^〕\n]{4,}〕")
HEAD_FIELD = re.compile(r"^\s*(?:親窓|書いた窓)\s*[:：]")   # 窓の id を書く頭の欄（本文の頭の塊の中だけ数えない）
SESSION_ID = re.compile(r"(?<![A-Za-z0-9_/])" + G.W.SESSION_ID_PAT)   # 窓の id の形の正本は window_shape
URL = re.compile(r"https?://\S+")
FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
INLINE = re.compile(r"`[^`\n]+`")
COMMENT = re.compile(r"<!--.*?-->", re.S)


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


# ── verdict（レビューの判定の形）──
WRITER_LINE = re.compile(r"^\s*書いた窓\s*[:：]\s*(%s)" % G.W.SESSION_ID_PAT, re.M)
COMMIT_SESSION = G.W.COMMIT_SESSION   # commit の書き手の記録の形の正本は window_shape（PR の commit 全部から書いた窓の組を読む）
# 窓の環境の記録（harness が hook に渡す。cse_<x> → session_<x>）。道具の呼び出しの文では変えられない
REMOTE_ID = re.compile(r"^cse_([A-Za-z0-9]+)$")
NUMBER_KEYS = ("issue_number", "pullNumber", "pull_number")


def _gh(args):
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=TIMEOUT)


def poster_id(env=None):
    """判定を出す窓の本物の session id（窓の環境の記録 CLAUDE_CODE_REMOTE_SESSION_ID の cse_<x> → session_<x>）か ""。
    hook の入力の session_id は手元の会話ログの id（UUID）で、commit の Claude-Session・判定の名乗りの形と違うので使えない。"""
    m = REMOTE_ID.match(str((os.environ if env is None else env).get("CLAUDE_CODE_REMOTE_SESSION_ID") or "").strip())
    return "session_" + m.group(1) if m else ""


def pr_facts(repo, ti):
    """判定を出す先の PR の (先端の SHA, 書いた窓の組, 誤り)。GitHub から引く（判定の形の道具が要る材料・写さない）。

    書いた窓の組は PR の commit 全部の `Claude-Session:` の窓（記録）と、本文の頭の `書いた窓:`（写し）を合わせた物。
    途中の commit を書いた窓も入る。commit に記録が 1 つも無ければ誤り（本文の写しだけで書いた窓を決めない）。
    引けない時は誤りを返す（欠けた材料で判定を通さない）。"""
    if not repo:
        return "", [], "出す先の repo（owner・repo）が道具の入力に無い"
    number = next((ti.get(k) for k in NUMBER_KEYS if ti.get(k)), None)
    try:
        if not number and ti.get("comment_id"):
            p = _gh(["repos/%s/issues/comments/%s" % (repo, ti["comment_id"]), "--jq", ".issue_url"])
            number = p.stdout.strip().rsplit("/", 1)[-1] if p.returncode == 0 else None
        if not number:
            return "", [], "判定を出す先の PR の番号が分からない"
        p = _gh(["repos/%s/pulls/%s" % (repo, number), "--jq", '.head.sha + "\\n" + (.body // "")'])
    except FileNotFoundError:
        return "", [], "GitHub の CLI（gh）が無く、PR の先端と書いた窓を引けない"
    except (OSError, subprocess.SubprocessError) as e:
        return "", [], "PR を引けなかった（%s）" % e.__class__.__name__
    if p.returncode != 0:
        return "", [], "PR #%s を引けなかった（判定は PR に出す・gh の認証か網を確かめる）: %s" % (
            number, (p.stderr or "").strip().splitlines()[-1:] or "")
    head, _, body = p.stdout.partition("\n")
    if not re.fullmatch(r"[0-9a-f]{40}", head.strip()):
        return "", [], "PR #%s の先端の SHA が読めない" % number
    try:
        c = _gh(["--paginate", "repos/%s/pulls/%s/commits" % (repo, number), "--jq", ".[].commit.message"])
    except (OSError, subprocess.SubprocessError) as e:
        return "", [], "PR #%s の commit を引けなかった（%s）" % (number, e.__class__.__name__)
    if c.returncode != 0:
        return "", [], "PR #%s の commit を引けなかった: %s" % (number, (c.stderr or "").strip().splitlines()[-1:] or "")
    writers = list(dict.fromkeys(COMMIT_SESSION.findall(c.stdout)))
    if not writers:
        return head.strip(), [], ("PR #%s の commit に `Claude-Session:` の行が 1 つも無く、書いた窓が記録から決まらない"
                                  "（本文の `書いた窓:` の写しだけで別の目を照らさない）" % number)
    m = WRITER_LINE.search(body)
    if m and m.group(1) not in writers:
        writers.append(m.group(1))
    return head.strip(), writers, ""


def looks_verdict(body, data):
    """(見分け, 道具の path, 見分けられない訳)。見分けは "verdict"／"other"／""（道具が無い・古い・壊れた＝見分けられない）。
    判定のコメントかの見分けは判定の形の正本（checker の verdict_form.py --looks）を直に呼ぶ＝写さない。"""
    tool = _find_sibling(*VERDICT_FORM, data)
    if not tool:
        return "", "", "判定の形の道具（checker の verdict_form.py）が見つからない"
    try:
        p = _run([sys.executable, tool, "--looks", _tmp_file(body, "looks")])
    except (OSError, subprocess.SubprocessError) as e:
        return "", tool, "判定の形の道具が走らなかった（%s）" % e.__class__.__name__
    looks = p.stdout.strip()
    if p.returncode != 0 or looks not in ("verdict", "other"):
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-1:]
        return "", tool, "判定の形の道具が --looks に答えない（古い版か壊れた・exit %d）: %s" % (p.returncode, " / ".join(tail))
    return looks, tool, ""


def check_verdict(body, data):
    # 判定かどうか見分けられない時（道具が無い・古い・壊れた）は止めない＝判定でないふつうのコメントまで止めない。
    # 出した後に post の notice が知らせる（オーナーの同意の無い止める範囲の広がりを作らない）。
    looks, tool, _why = looks_verdict(body, data)
    if looks != "verdict":
        return []
    body_file = _tmp_file(body, "verdict")
    ti = data.get("tool_input") or {}
    poster = poster_id()
    if not poster:
        return ["判定の材料: 判定を出す窓の id が窓の環境の記録（CLAUDE_CODE_REMOTE_SESSION_ID）に無く、名乗りを照らせない"
                "（判定はクラウドの窓で出す）"]
    head, writers, err = pr_facts(_repo_name(ti), ti)
    if err:
        return ["判定の材料: " + err]
    try:
        p = _run([sys.executable, tool, body_file, "--writer", ",".join(writers), "--head", head, "--reviewer", poster])
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
    holders = sorted({m.group(0)[:14] for m in PLACEHOLDER.finditer(strip_notes(text))})
    return heads, holders


def cleanup_parts(data):
    """((見出しの並び, 置き場の字の並び), "") か (None, 読めない訳)。雛形は dev-flow の正本を直に読む。"""
    tpl = _find_sibling(*CLEANUP_TEMPLATE, data)
    if not tpl:
        return None, "整地の雛形（dev-flow の preimpl-cleanup の 整地受領証.template.md）が見つからない"
    try:
        return template_parts(tpl), ""
    except (OSError, ValueError) as e:
        return None, "整地の雛形が読めない: %s" % e


def strip_notes(body):
    """注記（<!-- -->）とコードの囲みの中を消した文。消すのはここ 1 か所（整地の欄も言葉の照らしもここを読む）。"""
    return FENCE.sub(" ", COMMENT.sub(" ", body))


def cleanup_text(body, repo, vals):
    """整地の欄を照らす本文（注記〔雛形の説明〕とコードの囲みの中を消した物）か ""（外す repo・`整地: 不要` の 1 行＝当たらない）。
    消すのはここ 1 か所（pre の check_cleanup と post の notice が同じ物を読む）。"""
    if repo and _matches(vals.get("pr_cleanup_exempt_repos"), repo):
        return ""
    text = strip_notes(body)
    return "" if NOT_NEEDED.search(text) else text


def check_cleanup(body, repo, data, vals):
    body = cleanup_text(body, repo, vals)
    if not body:
        return []
    parts, _why = cleanup_parts(data)
    if not parts:
        return []        # 雛形が無い・読めない時は止めない（PR 本文まで止めない）。出した後に notice が知らせる
    heads, holders = parts
    out = []
    lack = [("%s. %s" % (no, name)) for no, name in heads
            if not re.search(r"^#{1,6}\s*(?:%s\.\s*)?%s" % (no, re.escape(name)), body, re.M)]
    if lack:
        out.append("整地の見出しが無い: %s（雛形の見出し %d つ）" % ("・".join(lack), len(heads)))
    left = [h for h in holders if h in body]
    if left:
        out.append("整地の雛形の `〔…〕` が残っている: %s" % "・".join(h + "…" for h in left[:3]))
    return out


# ── words（PR の題・本文の言葉）──
def visible_prose(body):
    """数えない所（本文の頭の塊の窓の id の欄・コード・URL・注記）を除いた文。"""
    body = strip_notes(body)
    lines, top = [], True
    for ln in body.splitlines():
        if not ln.strip():
            top = False
        if top and HEAD_FIELD.match(ln):
            continue
        lines.append(ln)
    return URL.sub(" ", INLINE.sub(" ", "\n".join(lines)))


def check_words(texts, repo, vals):
    if repo and _matches(vals.get("pr_words_exempt_repos"), repo):
        return []
    out = []
    for where, text in texts:
        ids = list(dict.fromkeys(SESSION_ID.findall(visible_prose(text))))
        if ids:
            out.append("%sに窓の id がそのまま %d 個: %s" % (where, len(ids), "・".join(ids[:3]) + ("…" if len(ids) > 3 else "")))
    return out


# ── public（公開の repo に置かない物）──
WORKFLOW_DIR = os.path.join(".github", "workflows")
DENY_FILE = re.compile(r"deny-words-file\s*:\s*[\"']?([^\s\"'#]+)")
USES_GUARD = re.compile(r"(?:uses\s*:\s*\S*public-guard\b|^\s*public-guard\s*:)", re.M)


def _checkout_of(repo, data):
    """窓の repo の取り出しが owner/repo なら、その根。"""
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
    path = re.sub(r"\.git$", "", url.rstrip("/")).lower()
    return top if top and path.endswith("/" + repo.lower()) else ""


def public_target(repo, data, vals):
    """(公開か, 取り出しの根, 置かない語の表の path)。"""
    top = _checkout_of(repo, data)
    if top:
        for wf in sorted(glob.glob(os.path.join(top, WORKFLOW_DIR, "*.y*ml"))):
            try:
                with open(wf, encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue
            if USES_GUARD.search(raw):
                m = DENY_FILE.search(raw)
                return True, top, (os.path.join(top, m.group(1)) if m else "")
    if repo and _matches(vals.get("public_repos_extra"), repo):
        return True, top, ""
    return False, top, ""


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
    "verdict": "判定のコメントは skill `checker:review-pr` の「判定の形」で書き直す（形の正本はその SKILL.md と verdict_form.py・"
               "ここに写さない）。`python3 <verdict_form.py> <下書き> --writer <書いた窓> --head <PR の先端>` が exit 0 になってから出す。",
    "cleanup": "PR 本文の「何をどう変えたか」の後に `## 整地（根治の 4 段）` を置き、skill `dev-flow:preimpl-cleanup` の雛形の 4 つの見出しで"
               "書く（中身は頭が書く・`〔…〕` を残さない）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）なら、4 欄の代わりに "
               "`整地: 不要（<なぜ要らないか>）` の 1 行を書く（訳はレビューが照らす）。",
    "words": "窓の id は、読む人が開けるリンク（https://claude.ai/code/<id>）にして役の名を添える（例: 「直す窓（リンク）」）か、役の名だけに"
             "する。決まった欄（親窓・書いた窓）とコードの囲みの中は数えない。",
    "public": "当たった所を書き直す（秘密・個人の情報は消す・作り物の例は example.com などにする・置かない語と顧客の語は一般の言葉に言い換える）。"
              "GitHub の本文は書き替えても古い版が編集の履歴に公開で残るので、出す前に直す。",
}
HEAD = {
    "broken": "照らしが壊れた",
    "verdict": "レビューの判定の形が崩れている",
    "cleanup": "PR 本文の整地の欄が雛形と合わない",
    "words": "PR の題・本文に AI の中の呼び名が出ている",
    "public": "公開の repo に置かない物がある",
}


def notice(data, vals):
    """PostToolUse: 正本が読めず照らさずに通した時だけ知らせる（止めない）。判定の道具（コメント）と整地の雛形（PR 本文）。"""
    kind = tool_kind(data.get("tool_name"))
    ti = data.get("tool_input")
    body = ti.get("body") if isinstance(ti, dict) and isinstance(ti.get("body"), str) else ""
    if not body.strip():
        return ""
    if kind == "comment":
        looks, _tool, why = looks_verdict(body, data)
        if looks:
            return ""
        return ("[guard] 出したコメントがレビューの判定かどうか見分けられず、判定の形を照らさずに通した（止めていない）: %s。"
                "plugin checker を guard と同じ版で入れる（または AF_VERDICT_FORM に path）。このコメントが判定なら、"
                "checker の verdict_form.py で形を照らし、崩れていれば出し直す。" % why)
    if kind == "pr" and cleanup_text(body, _repo_name(ti), vals):
        parts, why = cleanup_parts(data)
        if parts:
            return ""
        return ("[guard] PR 本文の整地の欄を照らさずに通した（止めていない）: %s。plugin dev-flow を guard と同じ版で入れる"
                "（または AF_CLEANUP_TEMPLATE に path）。本文の整地の 4 欄は skill dev-flow:preimpl-cleanup の雛形と照らして直す。" % why)
    return ""


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
    out = []
    if kind == "comment" and body.strip():
        out += [("verdict", m) for m in check_verdict(body, data)]
    if kind == "pr":
        if body.strip():
            out += [("cleanup", m) for m in check_cleanup(body, repo, data, vals)]
        out += [("words", m) for m in check_words(texts, repo, vals)]
    out += [("public", m) for m in check_public(texts, repo, data, vals)]
    return out


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
    lines.append("誤って止めた時: 整地を PR 本文の外に置く repo・言葉の照らしが合わない repo は、値の表の guard.pr_cleanup_exempt_repos・"
                 "guard.pr_words_exempt_repos（owner/repo に当てる正規表現）に足す（PR とレビューを通す）。判定の形と公開の検査は"
                 "外さない（決まりの正本を直す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)
