"""PreToolUse — PR の題・本文と、PR・issue へのコメントを、GitHub へ出す前に照らす。崩れていれば AI だけを止めて書き直させる。

意図: レビューの判定の形・PR 本文の整地の欄・人が読む文の言葉・公開の repo に置かない物を、GitHub に出る前に照らす
（オーナー同意 2026-11-19: 決まりが文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい）。
止まるのは AI の道具の呼び出しだけ（文はまだ GitHub に出ていない）。人の操作は何も止めない。
課題: 形の崩れた判定が合流の材料になり、欄の欠けた PR 本文がレビューで初めて見つかり、
公開の repo の PR 本文に置かない語が出て GitHub の編集の履歴に残った。
原因: 決まりと道具はあるのに、AI が自分で回すか、出した後に CI やレビューが拾うだけだった。
公開かの見分けは手元の取り出しの workflow だけを読み、取り出しが無い・workflow が読めない時を「公開でない」と読んで照らしを
飛ばしていた（決められない時に通す側へ倒れていた）。

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
            渡す。判定の 1 行目の名乗りは手で書いた写しで、照らされる側。本文の `書いた窓:` は読まない。PR のコメントから初めの判定の
            決まりの版を verdict_form.first_rules で読み --first で渡す〔無ければ なし〕。どれかが引けなければ止める）
            コメントがレビューの判定（どの行かに `レビューした窓: … 判定: green|red` が揃うか、verdict の見出しが在る）なら、checker の
            `scripts/verdict_form.py` をそのまま呼ぶ。赤なら止める。道具が見つからない・壊れた時も止める
  cleanup … PR の本文（本文を渡す時だけ）に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の見出し
            （`## 1.` からの番号つき。見出しの名と数は雛形から読む）が全部在り、雛形の `〔…〕` が残っていない事。整地の要らない PR
            （振る舞いを変えない: 誤字・記録だけ・版だけ等）は本文に `整地: 不要（<訳>）` の 1 行を書く（訳はレビューが照らす）
  words   … PR の題・本文に、窓の id（`session_01…`）がそのまま出ていない事。本文の頭の欄の塊（1 行目から最初の空行まで）の
            窓の id を書く欄（PR の型から畳んだ書いた窓・親窓の欄。使う側の型に残る間は）・コードの囲み・`…` の字・URL の中は
            数えない（job・検査 等の欄や、頭の塊の外で同じ字で始まる行は数える。親窓は照らせない写しなので PR の型に置かない＝
            窓の親はサーバの記録 get_session を読む）
  public  … 公開の repo（窓の repo の取り出しの workflow が action public-guard を呼ぶ／値の表 public_repos_extra）なら、
            題・本文を `public-guard/guard.py --text` に渡す（呼び口の見分けと置かない語の表は workflow の読み手
            public-guard/workflow_reader.py が正本: PR・push で走る job の step の呼び口だけを数え、語の表は全部の呼び口の with: の
            deny-words-file の和）。当たれば止める。
            公開かを決められない時は公開として照らす（既定で止める側）: 出す先の取り出しが手元に無ければ GitHub の記録
            （gh api repos/<owner>/<repo> の visibility）を引き、private・internal の時だけ公開でないと読む（引けない・答えが
            分からない時は公開）。取り出しに開けない・壊れた workflow が 1 つでも在れば公開として照らす（その分の語の表は読めない）
            検査が見つからない・壊れた時も止める（公開の repo へは、照らせない文を出さない）
            開けない・壊れた workflow は出した後（PostToolUse の notice）にも名と訳を知らせる
誤って止めた時: 値の表 pr_cleanup_exempt_repos・pr_words_exempt_repos（owner/repo の名の全体に当てる正規表現・^ で始め $ で終える＝
型 repo_names）で repo ごとに外す。
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

# 判定の形の印（review-pr の形）: 名乗りの欄と判定が 1 行に揃う行（どの行でも・`:` の全角半角を問わない）か、verdict の見出し
# （# の数・大小文字を問わない）。引用（行頭の `>`）の中は、前の判定を引いた返事なので数えない。
VERDICT_LINE = re.compile(r"^[ \t]*レビューした窓\s*[:：].*判定\s*[:：]\s*(?:green|red)\b", re.M | re.I)
VERDICT_HEAD = re.compile(r"^[ \t]*#{1,6}\s*verdict\s*$", re.M | re.I)
NOT_NEEDED = re.compile(r"^\s*(?:[-*]\s*)?\**整地\**\s*[:：]\s*(?:不要|要らない)\s*[（(]\s*(?![<＜〔])\S[^)）]*[)）]", re.M)
TEMPLATE_HEAD = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)
PLACEHOLDER = re.compile(r"〔[^〕\n]{4,}〕")
HEAD_FIELD = re.compile(r"^\s*(?:書いた窓|親窓)\s*[:：]")   # 窓の id を書く頭の欄（本文の頭の塊の中だけ数えない）。
# 親窓は畳んだ欄（照らせない写し）。使う側の PR の型に残る間は古い本文も通す（壊れる 1 段目・古い形 pr-parent-field）
SESSION_ID = re.compile(r"(?<![A-Za-z0-9_/])session_0[A-Za-z0-9]{15,}")
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


def _exempt(key, repo, data, vals):
    """外す側の鍵（pr_cleanup_exempt_repos・pr_words_exempt_repos）に repo が在るか。名の全体の形の行だけで当てる
    （形の違う行は外さず照らす向き＝値の表の照らしが名指す）。"""
    good, _ = _repo_rows(key, data, vals)
    return _matches(good, repo)


def _public_extra(repo, data, vals):
    """値の表 public_repos_extra に repo が在るか。名の全体の形の行は全体の一致で当てる。形の違う行は、名の一部にでも
    当たれば公開と見る（公開の照らしを黙って外さない＝安全の守り。形の違いは値の表の照らしが名指す）。"""
    if G.broken_stop_key("public_repos_extra", data or {}, rows=False):
        return True   # 表・鍵を読めない時は公開と見る（読めない時に既定の [] へ落ちて公開の照らしを外さない）。行の違いは下で行ごとに扱う
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


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)


# ── verdict（レビューの判定の形）──
def looks_verdict(body):
    """判定のコメントか。判定の形そのものの印（名乗りと判定が揃う行か verdict の見出し）だけで見分ける。
    文中に「判定: green」と書いた普通のコメントや「レビューした窓は…」で始まる文は判定と見なさない。"""
    body = FENCE.sub(" ", COMMENT.sub(" ", body))
    return bool(VERDICT_LINE.search(body) or VERDICT_HEAD.search(body))


# commit の書き手の記録（窓が commit の度に付ける行）。PR の commit 全部から読み、書いた窓の組にする
COMMIT_SESSION = re.compile(r"^Claude-Session:\s*\S*?(session_[A-Za-z0-9]+)\s*$", re.M)
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


def pr_number(repo, ti):
    number = next((ti.get(k) for k in NUMBER_KEYS if ti.get(k)), None)
    if not number and ti.get("comment_id"):
        p = _gh(["repos/%s/issues/comments/%s" % (repo, ti["comment_id"]), "--jq", ".issue_url"])
        number = p.stdout.strip().rsplit("/", 1)[-1] if p.returncode == 0 else None
    return number


def first_rules(repo, ti, tool):
    """PR のコメントから初めの判定の決まりの版（SHA12）か NO_FIRST の `なし`、と誤り。読み方は判定の形の道具の
    first_rules をそのまま呼ぶ（写さない）。コメントを引けない時は誤り（初めの版を照らさずに判定を通さない）。
    道具が first_rules を持たない古い checker なら (None, "")＝--first を渡さず前の形で照らす（壊れる変更の 1 段目の間）。"""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("af_verdict_form", tool)
        vf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vf)
    except (Exception, SystemExit) as e:  # noqa: BLE001  読めない・読むと抜ける道具で版を決めない（hook ごと落ちない）
        return "", "判定の形の道具が壊れた（読むと %s）。初めの判定の決まりの版を読めない" % e.__class__.__name__
    if not hasattr(vf, "first_rules"):
        return None, ""   # 1 段目の間: 決まりの版を知らない古い checker は --first を渡さず前の形で照らす（CONTRIBUTING.md §8）
    try:
        number = pr_number(repo, ti)
        c = _gh(["--paginate", "repos/%s/issues/%s/comments" % (repo, number), "--jq", ".[].body | @json"]) \
            if number else None
    except (OSError, subprocess.SubprocessError) as e:
        return "", "PR のコメントを引けなかった（%s）" % e.__class__.__name__
    if c is None or c.returncode != 0:
        return "", "PR のコメントを引けず、初めの判定の決まりの版を読めない"
    try:
        bodies = [json.loads(ln) for ln in c.stdout.splitlines() if ln.strip()]
    except ValueError:
        return "", "PR のコメントが読めない"
    return vf.first_rules(bodies) or vf.NO_FIRST, ""


def pr_facts(repo, ti):
    """判定を出す先の PR の (先端の SHA, 書いた窓の組, 誤り)。GitHub から引く（判定の形の道具が要る材料・写さない）。

    書いた窓の組は PR の commit 全部の `Claude-Session:` の窓（記録）だけ。途中の commit を書いた窓も入る。本文の頭の
    `書いた窓:` は手の写しなので読まない（PR の型から畳んだ・写しが記録とずれるとレビューの窓を書いた窓に数えて弾いた）。
    commit に記録が 1 つも無ければ誤り。
    引けない時は誤りを返す（欠けた材料で判定を通さない）。"""
    if not repo:
        return "", [], "出す先の repo（owner・repo）が道具の入力に無い"
    try:
        number = pr_number(repo, ti)
        if not number:
            return "", [], "判定を出す先の PR の番号が分からない"
        p = _gh(["repos/%s/pulls/%s" % (repo, number), "--jq",
                 '.head.sha + "\\n" + (.commits | tostring) + "\\n" + (.body // "")'])
    except FileNotFoundError:
        return "", [], "GitHub の CLI（gh）が無く、PR の先端と書いた窓を引けない"
    except (OSError, subprocess.SubprocessError) as e:
        return "", [], "PR を引けなかった（%s）" % e.__class__.__name__
    if p.returncode != 0:
        return "", [], "PR #%s を引けなかった（判定は PR に出す・gh の認証か網を確かめる）: %s" % (
            number, (p.stderr or "").strip().splitlines()[-1:] or "")
    head, _, rest = p.stdout.partition("\n")
    total, _, body = rest.partition("\n")
    if not re.fullmatch(r"[0-9a-f]{40}", head.strip()):
        return "", [], "PR #%s の先端の SHA が読めない" % number
    try:
        c = _gh(["--paginate", "repos/%s/pulls/%s/commits" % (repo, number), "--jq", ".[].commit.message | @json"])
    except (OSError, subprocess.SubprocessError) as e:
        return "", [], "PR #%s の commit を引けなかった（%s）" % (number, e.__class__.__name__)
    if c.returncode != 0:
        return "", [], "PR #%s の commit を引けなかった: %s" % (number, (c.stderr or "").strip().splitlines()[-1:] or "")
    try:
        msgs = [json.loads(ln) for ln in c.stdout.splitlines() if ln.strip()]
    except ValueError:
        return "", [], "PR #%s の commit の説明が読めない" % number
    if not total.strip().isdigit() or len(msgs) < int(total):
        # GitHub の PR の commit の一覧は 250 本で切れる。引けなかった commit を書いた窓を組から落としたまま通さない
        return "", [], ("PR #%s の commit を全部は引けない（%s 本のうち %d 本・GitHub の一覧の上限）。書いた窓の組が欠けるので"
                        "判定を通さない。PR を小さく分けるか、手元の取り出しで plugin checker の pr_writer.py --writers を回して照らす"
                        % (number, total.strip() or "?", len(msgs)))
    writers = list(dict.fromkeys(w for m in msgs for w in COMMIT_SESSION.findall(m)))
    if not writers:
        return head.strip(), [], ("PR #%s の commit に `Claude-Session:` の行が 1 つも無く、書いた窓が記録から決まらない"
                                  "（本文の `書いた窓:` の写しだけで別の目を照らさない）" % number)
    return head.strip(), writers, ""


def check_verdict(body, data):
    if not looks_verdict(body):
        return []
    tool = _find_sibling(*VERDICT_FORM, data)
    if not tool:
        return ["判定の形の道具（checker の verdict_form.py）が見つからず、形を確かめられない。plugin checker を入れる"
                "（または AF_VERDICT_FORM に path）"]
    ti = data.get("tool_input") or {}
    poster = poster_id()
    if not poster:
        return ["判定の材料: 判定を出す窓の id が窓の環境の記録（CLAUDE_CODE_REMOTE_SESSION_ID）に無く、名乗りを照らせない"
                "（判定はクラウドの窓で出す）"]
    head, writers, err = pr_facts(_repo_name(ti), ti)
    if err:
        return ["判定の材料: " + err]
    first, err = first_rules(_repo_name(ti), ti, tool)
    if err:
        return ["判定の材料: " + err]
    try:
        p = _run([sys.executable, tool, _tmp_file(body, "verdict"), "--writer", ",".join(writers), "--head", head]
                 + (["--first", first] if first is not None else []) + ["--reviewer", poster])
    except (OSError, subprocess.SubprocessError) as e:
        return ["判定の形の道具が走らなかった: %s" % e.__class__.__name__]
    if p.returncode == 0:
        return []
    errs = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    if p.returncode != 1 or not errs:
        tail = (p.stderr or p.stdout or "").strip().splitlines()[-2:]
        return ["判定の形の道具が壊れた（exit %d）: %s" % (p.returncode, " / ".join(tail))]
    return ["判定の形: " + e for e in errs]


# ── cleanup（PR 本文の整地の欄）──
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
    if repo and _exempt("pr_cleanup_exempt_repos", repo, data, vals):
        return []
    body = FENCE.sub(" ", COMMENT.sub(" ", body))      # 注記（雛形の説明）とコードの囲みの中は数えない
    if NOT_NEEDED.search(body):
        return []
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


# ── words（PR の題・本文の言葉）──
def visible_prose(body):
    """数えない所（本文の頭の塊の窓の id の欄・コード・URL・注記）を除いた文。"""
    body = FENCE.sub(" ", COMMENT.sub(" ", body))
    lines, top = [], True
    for ln in body.splitlines():
        if not ln.strip():
            top = False
        if top and HEAD_FIELD.match(ln):
            continue
        lines.append(ln)
    return URL.sub(" ", INLINE.sub(" ", "\n".join(lines)))


def check_words(texts, repo, vals, data=None):
    if repo and _exempt("pr_words_exempt_repos", repo, data, vals):
        return []
    out = []
    for where, text in texts:
        ids = list(dict.fromkeys(SESSION_ID.findall(visible_prose(text))))
        if ids:
            out.append("%sに窓の id がそのまま %d 個: %s" % (where, len(ids), "・".join(ids[:3]) + ("…" if len(ids) > 3 else "")))
    return out


# ── public（公開の repo に置かない物）──
WORKFLOW_DIR = os.path.join(".github", "workflows")
# 取り出しの origin の URL（https・ssh://・scp の形 <利用者>@github.com:o/r）から owner/repo を読む。host は github.com だけ。
REMOTE = re.compile(r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?github\.com(?::\d+)?/|(?:[^@/:]+@)?github\.com:)"
                    r"([^/\s]+)/([^/\s]+?)(?:\.git)?/*$", re.I)


def _reader():
    """workflow の読み手（正本 public-guard/workflow_reader.py・見回りと手元の検査も同じ物を読む）。見つからなければ例外
    （公開の repo の取り出しで照らせない時は、黙って通さず止める＝check の broken）。"""
    path = G.foundation_file(os.path.join("public-guard", "workflow_reader.py"))
    if not path:
        raise RuntimeError("workflow の読み手（public-guard/workflow_reader.py）が見つからない")
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
                "入れ直す（または AF_PUBLIC_GUARD に path）"]
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
    "verdict": "判定のコメントは skill `checker:review-pr` の「判定の形」で書き直す（形の正本はその SKILL.md と verdict_form.py・"
               "ここに写さない）。`python3 <verdict_form.py> <下書き> --writer <書いた窓> --head <PR の先端> --first <関所が出した値>` が "
               "exit 0 になってから出す。",
    "cleanup": "PR 本文の「何をどう変えたか」の後に `## 整地（根治の段）` を置き、skill `dev-flow:preimpl-cleanup` の雛形の見出しで"
               "書く（中身は頭が書く・`〔…〕` を残さない）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）なら、欄の代わりに "
               "`整地: 不要（<なぜ要らないか>）` の 1 行を書く（訳はレビューが照らす）。",
    "words": "窓の id は、読む人が開けるリンク（https://claude.ai/code/<id>）にして役の名を添える（例: 「直す窓（リンク）」）か、役の名だけに"
             "する。決まった欄（頭の塊の書いた窓）とコードの囲みの中は数えない。親窓の欄は PR の型から畳んだ（窓の親はサーバの記録 get_session の parent_session_id）。",
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
        out += [("words", m) for m in check_words(texts, repo, vals, data)]
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
                 "guard.pr_words_exempt_repos（owner/repo の名の全体に当てる正規表現・repo 1 つなら ^owner/repo$・owner ごとなら ^owner/.*$）に足す（PR とレビューを通す）。判定の形と公開の検査は"
                 "外さない（決まりの正本を直す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)
