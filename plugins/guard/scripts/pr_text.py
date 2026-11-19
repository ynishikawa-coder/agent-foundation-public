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
照らす物（見分けは正本を直に読む・呼ぶ。ここに決まりを写さない）:
  verdict … コメントがレビューの判定（頭の行が `レビューした窓:` か、頭 5 行に `判定: green|red`）なら、checker の
            `scripts/verdict_form.py` をそのまま呼ぶ。赤なら止める。道具が見つからない・壊れた時も止める
  cleanup … PR の本文（本文を渡す時だけ）に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し
            （`## 1.`〜`## 4.`。見出しの名は雛形から読む）が全部在り、雛形の `〔…〕` が残っていない事。整地の要らない PR
            （振る舞いを変えない: 誤字・記録だけ・版だけ等）は本文に `整地: 不要（<訳>）` の 1 行を書く（訳はレビューが照らす）
  words   … PR の題・本文に、窓の id（`session_01…`）がそのまま出ていない事。頭の決まった欄（親窓・書いた窓・job・
            触る path・検査）・コードの囲み・`…` の字・URL の中は数えない
  public  … 公開の repo（窓の repo の取り出しの workflow が action public-guard を呼ぶ／値の表 public_repos_extra）なら、
            題・本文を `public-guard/guard.py --text` に渡す（置かない語の表はその workflow の deny-words-file）。当たれば止める。
            検査が見つからない・壊れた時も止める（公開の repo へは、照らせない文を出さない）
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

TIMEOUT = 30
SHOWN = 12

PR_TOOLS = ("create_pull_request", "update_pull_request")
COMMENT_TOOLS = ("add_issue_comment", "update_issue_comment", "add_reply_to_pull_request_comment",
                 "pull_request_review_write", "add_comment_to_pending_review")
ISSUE_TOOLS = ("issue_write",)

VERDICT_FORM = ("checker", os.path.join("scripts", "verdict_form.py"), "AF_VERDICT_FORM")
CLEANUP_TEMPLATE = ("dev-flow", os.path.join("skills", "preimpl-cleanup", "整地受領証.template.md"), "AF_CLEANUP_TEMPLATE")

LOOKS_VERDICT = re.compile(r"判定\s*[:：]\s*(?:green|red)\b")
NOT_NEEDED = re.compile(r"^\s*(?:[-*]\s*)?\**整地\**\s*[:：]\s*(?:不要|要らない)\s*[（(]\s*(?![<＜〔])\S[^)）]*[)）]", re.M)
TEMPLATE_HEAD = re.compile(r"^## (\d+)\. (.+?)\s*$", re.M)
PLACEHOLDER = re.compile(r"〔[^〕\n]{4,}〕")
HEAD_FIELD = re.compile(r"^\s*(?:親窓|書いた窓|job|触る path|検査)\s*[:：]")
SESSION_ID = re.compile(r"(?<![A-Za-z0-9_/])session_0[A-Za-z0-9]{15,}")
URL = re.compile(r"https?://\S+")
FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
INLINE = re.compile(r"`[^`\n]+`")
COMMENT = re.compile(r"<!--.*?-->", re.S)


def tool_kind(name):
    name = str(name or "")
    for kind, names in (("pr", PR_TOOLS), ("comment", COMMENT_TOOLS), ("issue", ISSUE_TOOLS)):
        if any(name == n or name.endswith("__" + n) for n in names):
            return kind
    return ""


def _repo_name(ti):
    owner, repo = str(ti.get("owner") or "").strip(), str(ti.get("repo") or "").strip()
    return "%s/%s" % (owner, repo) if owner and repo else ""


def _matches(patterns, text):
    return any(isinstance(p, str) and p and re.search(p, text) for p in patterns or [])


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
def looks_verdict(body):
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return bool(lines) and (lines[0].startswith("レビューした窓") or any(LOOKS_VERDICT.search(ln) for ln in lines[:5]))


def check_verdict(body, data):
    if not looks_verdict(body):
        return []
    tool = G.find_plugin_file(*VERDICT_FORM[:2], env_name=VERDICT_FORM[2], payload=data)
    if not tool:
        return ["判定の形の道具（checker の verdict_form.py）が見つからず、形を確かめられない。plugin checker を入れる"
                "（または AF_VERDICT_FORM に path）"]
    try:
        p = _run([sys.executable, tool, _tmp_file(body, "verdict")])
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


def check_cleanup(body, repo, data, vals):
    if repo and _matches(vals.get("pr_cleanup_exempt_repos"), repo):
        return []
    body = FENCE.sub(" ", COMMENT.sub(" ", body))      # 注記（雛形の説明）とコードの囲みの中は数えない
    if NOT_NEEDED.search(body):
        return []
    tpl = G.find_plugin_file(*CLEANUP_TEMPLATE[:2], env_name=CLEANUP_TEMPLATE[2], payload=data)
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
    """数えない所（頭の決まった欄・コード・URL・注記）を除いた文。"""
    body = FENCE.sub(" ", COMMENT.sub(" ", body))
    lines = [ln for ln in body.splitlines() if not HEAD_FIELD.match(ln)]
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
                words = os.path.join(top, m.group(1)) if m else ""
                return True, top, (words if words and os.path.isfile(words) else "")
    if repo and _matches(vals.get("public_repos_extra"), repo):
        return True, top, ""
    return False, top, ""


def find_public_guard(top="", guard_root=None):
    """public-guard/guard.py の path か ""（土台の repo の根に在る・plugin の外）。"""
    env = os.environ.get("AF_PUBLIC_GUARD") or ""
    if env:
        return env if os.path.isfile(env) else ""
    here = guard_root or G.GUARD_ROOT
    rel = os.path.join("public-guard", "guard.py")
    cands = [os.path.join(top, rel)] if top else []
    cands.append(os.path.join(os.path.dirname(os.path.dirname(here)), rel))          # repo の形: plugins/guard の 2 つ上
    market = os.path.dirname(os.path.dirname(here))                                    # 入れた形: cache/<市場>/guard/<版>
    cands.append(os.path.join(os.path.dirname(os.path.dirname(market)), "marketplaces", os.path.basename(market), rel))
    for c in cands:
        if os.path.isfile(c):
            return c
    return ""


def check_public(texts, repo, data, vals):
    is_public, top, words = public_target(repo, data, vals)
    if not is_public:
        return []
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
    "verdict": "判定のコメントは skill `checker:review-pr` の形で書き直す（1 行目 `レビューした窓: <session id> 判定: green|red`・"
               "2 行目 `見た先端: <SHA12>`・`## verdict`・`## 点`〔見る点の表の全部〕・`## 所見`〔札 `- [止める|後の便|直った｜<段>]`〕）。"
               "`python3 <verdict_form.py> <下書き> --writer <書いた窓> --head <PR の先端>` が exit 0 になってから出す。",
    "cleanup": "PR 本文の「何をどう変えたか」の後に `## 整地（根治の 4 段）` を置き、skill `dev-flow:preimpl-cleanup` の雛形の 4 つの見出しで"
               "書く（中身は頭が書く・`〔…〕` を残さない）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）なら、4 欄の代わりに "
               "`整地: 不要（<なぜ要らないか>）` の 1 行を書く（訳はレビューが照らす）。",
    "words": "窓の id は、読む人が開けるリンク（https://claude.ai/code/<id>）にして役の名を添える（例: 「直す窓（リンク）」）か、役の名だけに"
             "する。決まった欄（親窓・書いた窓）とコードの囲みの中は数えない。",
    "public": "当たった所を書き直す（秘密・個人の情報は消す・作り物の例は example.com などにする・置かない語と顧客の語は一般の言葉に言い換える）。"
              "GitHub の本文は書き替えても古い版が編集の履歴に公開で残るので、出す前に直す。",
}
HEAD = {
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
    """止めるなら理由、通すなら ""。"""
    found = findings(data, vals)
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
