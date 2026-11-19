"""PreToolUse — 人や他の窓・外へ渡る道具の入力を、出る前に照らす。崩れていれば AI の呼び出しだけを止めて書き直させる。

なぜ在るか: 秘密を出さない（核 §1）・番号でなく物の名で頼む（核 §2）・窓の題の形と手の窓の 4 欄（細目 §4）は、文で
知らせるだけだった。AI が読み飛ばすと、鍵が他の窓・PR・Notion へ渡り、受けた窓とオーナーが「#3 やって」の中身を
知らず、形の崩れた題がオーナーの窓の一覧に出た（オーナー同意 2026-11-19: 文で知らせるだけで、AI が読み飛ばすと
そのままオーナーに届く所は、AI だけ止めて書き直させてよい）。止まるのは AI の呼び出しだけ。人の操作は何も止めない。

出口の見分けは道具の名で口を切らない（1 つの表 = 下の 3 つの関数）:
  secret_texts  … 照らす字は、どの道具でも入力の全部の字（Bash の命令の文・Write の中身も含む）と、入力が指す手元の
                  file の中身（Artifact で出す file・gh の --body-file・curl の -d @file）。鍵はどこにも書かない（核 §1）。
  request_texts … 人や他の窓が読む頼みの文: どの MCP の道具・SendMessage でも、欄の名が message・prompt・body・text・
                  title の字（窓へ送る・窓や予定を立てる・PR や issue やコメントを書く・メールを書く）と、Bash の gh の
                  題・本文（--title・--body・--body-file・api の -f body=）・curl で送る JSON や form の text・message・
                  body・content。選択肢の画面（AskUserQuestion）は ask_shape が番号を見る。
  is_exit       … 鍵の形の正本が読めない時に止める出口（MCP・Artifact・SendMessage・外へ送る Bash の命令）。

照らす物（見分けはどれも正本を直に呼ぶ＝写さない）:
  secret  … 上の字に鍵・トークンの形がある。形の正本は公開の検査（public-guard/guard.py の SECRET_PATTERNS）。
            見つからない時は出口だけ止める（照らせない物は外へ出さない）。在り処は AF_PUBLIC_GUARD → 土台の repo の根 →
            市場の取り出し。
  number  … 頼みの文に、番号（E02・#3 の形）だけで中身の名の無い頼みがある（「#3 やって」「E02 の件」）。済んだ事を知らせる
            文（「#3 を合流した」）は頼みでないので見ない。番号の見分けは ask_shape の中の言葉の見分け（INNER の「番号」＝
            土台の shared/number_shapes.json）、中身の語の見分けは ask_shape の話題の語（_words）を直に呼ぶ。
  title   … set_session_title と create_session の title が題の形（`<種類><状態> <作業名>`）でない。手の窓の題
            （`🙋⏳ 手: <何を>`）で窓を立てるのに、頼みの文に 目的・手順・済んだ目印・済んだ後 の見出しが揃っていない
            （4 つの見出しの語は細目 §4 の決まった形。言い換えは受けない）。
            形の正本は session-watch の session_watch.py（title_shape・HAND_PARTS）。見つからない時は題を照らさない。
射程の外（正直に書く）: 命令の外で作った文（別の script の中で送る・パイプで渡す中身）は見えない。
誤って止めた時: 値の表 config/skill-values.json の "guard" の outbound_secret_allow（当たった字に当てる正規表現・
作り物の見本だけ）・number_request_exempt（文に当てる正規表現）で外す。値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import json
import os
import re
import shlex

import guard_common as G

HOOKS = {"pre": "check"}

SEND_TOOLS = ("SendMessage",)
CREATE_SUFFIX = "__create_session"
REQUEST_FIELDS = ("message", "prompt", "body", "text", "title")
CURL_FIELDS = ("text", "message", "body", "content")
# 外へ送る Bash の命令（鍵の形の正本が読めない時に止める物）
OUT_BASH = re.compile(r"(?:^|[\s;&|(`])(?:gh|curl|wget|ssh|scp|rsync|nc|ncat|http|https|xh)\s|\bgit\s+push\b")
GH_TEXT = re.compile(r"^(?:pr|issue)$")
GH_WRITE = ("create", "comment", "edit", "review")
# 済んだ事を知らせる文の終わり（頼みでない）
REPORT_END = re.compile(r"(?:した|った|んだ|いた|いだ|えた|れた|せた|てた|ました|でした|済み|済んだ|終わった|完了|合流済|done|merged|closed)"
                        r"\s*[)）」』]*\s*$", re.I)
TITLE_SUFFIX = "__set_session_title"
MAX_READ = 2_000_000          # Artifact で出す file を照らす上限（バイト）
MAX_STRINGS = 2000

# 頼みの動きの語（番号の横にあっても中身の名にならない）。話題の語の止め語に足して使う。
REQUEST_WORDS = {
    "着手", "実施", "完了", "修正", "対応", "作業", "処理", "検討", "実行", "合流", "反映", "確認", "続行", "再開", "優先",
    "レビュー", "マージ", "チェック", "お願い", "よろしく",
    "merge", "review", "fix", "check", "close", "done", "please", "thanks",
}
_SENT = re.compile(r"[^\n。．！!？?]+")


# ── 正本の在り処 ──
def _public_guard():
    path = os.environ.get("AF_PUBLIC_GUARD") or G.foundation_file(os.path.join("public-guard", "guard.py"))
    if not path or not os.path.isfile(path):
        return None
    return G.load_module("af_public_guard", path)


def _session_watch():
    # 版がずれて正本に題の形の見分けが無い時は、check の try が受けて題の照らしだけを通す（ここで二重に確かめない）
    return G.session_watch()


# ── secret ──
def _strings(v, where="", out=None):
    """入力の中の字を (場所, 字) で全部。"""
    out = [] if out is None else out
    if len(out) >= MAX_STRINGS:
        return out
    if isinstance(v, str):
        out.append((where or "入力", v))
    elif isinstance(v, dict):
        for k, x in v.items():
            _strings(x, "%s.%s" % (where, k) if where else str(k), out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _strings(x, "%s[%d]" % (where, i), out)
    return out


def _artifact_files(ti, data):
    """Artifact の publish で出る手元の file（file_path・file_paths・files の元）。"""
    import qa_page
    paths = qa_page._sources(ti, data)
    for p in ti.get("file_paths") or []:
        if isinstance(p, str):
            paths.append(qa_page._resolve(p, data))
    return paths


def _words(cmd):
    try:
        return shlex.split(cmd, comments=False, posix=True)
    except ValueError:
        return []


def _opt_values(words, names):
    """命令の語の並びから、印 names の値の並び（`--x v`・`--x=v`・`-xv` を読む）。"""
    out = []
    for i, w in enumerate(words):
        for n in names:
            if w == n and i + 1 < len(words):
                out.append(words[i + 1])
            elif n.startswith("--") and w.startswith(n + "="):
                out.append(w[len(n) + 1:])
            elif not n.startswith("--") and len(n) == 2 and w.startswith(n) and len(w) > 2 and not w.startswith("--"):
                out.append(w[2:])
    return out


def _segments(words):
    seg = []
    for w in words:
        if w in (";", "&&", "||", "|", "&"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(w)
    if seg:
        yield seg


def _resolve(path, data):
    if os.path.isabs(path):
        return path
    return os.path.join(str(data.get("cwd") or G.project_dir(data) or "."), path)


def _read(path):
    try:
        if os.path.getsize(path) > MAX_READ:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def bash_out(cmd, data):
    """Bash の命令が外へ送る (場所, 字, 頼みの文か) の並び。gh の題・本文と curl で送る中身。"""
    out = []
    for seg in _segments(_words(cmd)):
        prog = os.path.basename(seg[0]) if seg else ""
        if prog == "gh" and len(seg) > 2 and GH_TEXT.match(seg[1]) and seg[2] in GH_WRITE:
            for v in _opt_values(seg, ("--title", "-t", "--body", "-b")):
                out.append(("gh %s %s の文" % (seg[1], seg[2]), v, True))
            for f in _opt_values(seg, ("--body-file", "-F")):
                text = _read(_resolve(f, data)) if f != "-" else None
                if text is not None:
                    out.append(("gh %s %s の本文 file %s" % (seg[1], seg[2], f), text, True))
        elif prog == "gh" and len(seg) > 1 and seg[1] == "api":
            for v in _opt_values(seg, ("-f", "--raw-field", "-F", "--field")):
                k, _, val = v.partition("=")
                if k in ("body", "title"):
                    out.append(("gh api の %s" % k, val, True))
        elif prog == "curl":
            for v in _opt_values(seg, ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "--json",
                                       "--form-string", "--form")):
                if v.startswith("@"):
                    text = _read(_resolve(v[1:], data))
                    if text is None:
                        continue
                    out.append(("curl で送る file %s" % v[1:], text, False))
                    v = text
                for k, val in _sent_fields(v):
                    out.append(("curl で送る %s" % k, val, True))
    return out


def _sent_fields(v):
    """curl で送る中身から、人が読む欄（text・message・body・content）の字。"""
    try:
        obj = json.loads(v)
    except ValueError:
        obj = None
    found = []
    if obj is not None:
        def walk(x):
            if isinstance(x, dict):
                for k, y in x.items():
                    if k in CURL_FIELDS and isinstance(y, str):
                        found.append((k, y))
                    else:
                        walk(y)
            elif isinstance(x, list):
                for y in x:
                    walk(y)
        walk(obj)
        return found
    for part in re.split(r"[&\n]", v):
        k, sep, val = part.partition("=")
        if sep and k.strip() in CURL_FIELDS:
            found.append((k.strip(), val))
    return found


def secret_texts(data):
    """鍵を照らす (場所, 字) の全部。道具の名で口を切らない。"""
    ti = data.get("tool_input")
    texts = _strings(ti)
    name = str(data.get("tool_name") or "")
    if name == "Artifact" and isinstance(ti, dict):
        for path in _artifact_files(ti, data):
            text = _read(path)
            if text is not None:
                texts.append(("file %s" % path, text))
    if name == "Bash" and isinstance(ti, dict) and isinstance(ti.get("command"), str):
        texts += [(w, t) for w, t, _ in bash_out(ti["command"], data) if " file " in w]
    return texts


def is_exit(data):
    name = str(data.get("tool_name") or "")
    if name.startswith("mcp__") or name in ("Artifact",) + SEND_TOOLS:
        return True
    ti = data.get("tool_input")
    return name == "Bash" and isinstance(ti, dict) and bool(OUT_BASH.search(str(ti.get("command") or "")))


def secret_hits(data, vals, pg):
    """[(場所, 札)]。当たった字そのものは返さない（止めた文にも鍵を出さない）。"""
    allow = [p for p in (vals.get("outbound_secret_allow") or []) if isinstance(p, str) and p]
    hits = []
    for where, text in secret_texts(data):
        for label, pat in pg.SECRET_PATTERNS.items():
            for m in re.finditer(pat, text):
                if any(re.search(a, m.group(0)) for a in allow):
                    continue
                if (where, label) not in hits:
                    hits.append((where, label))
                break
    return hits


def check_secret(data, vals):
    name = str(data.get("tool_name") or "")
    try:
        pg = _public_guard()
    except Exception as e:      # noqa: BLE001
        pg, err = None, str(e)
    else:
        err = ""
    if pg is None:
        if not is_exit(data):
            return ""            # 手元だけで閉じる道具は、照らせなくても通す（入れ直しの命令まで止めない）
        return ("[guard] 外へ渡す道具の入力の鍵を照らせないので、出す前に止めた（照らせない物は外へ出さない）。\n"
                "  鍵の形の正本 public-guard/guard.py が見つからない／読めない%s。\n"
                "  直し方: 土台の plugin を市場（marketplace）から入れ直す。手元の置き場が違う時は環境変数 AF_PUBLIC_GUARD に"
                " guard.py の path を入れる。" % ((": " + err) if err else ""))
    hits = secret_hits(data, vals, pg)
    if not hits:
        return ""
    lines = ["[guard] 道具（%s）の入力に鍵・認証情報の形があるので、出す前に止めた（鍵はどこにも書かない＝核 §1・"
             "オーナー同意 2026-11-19・人の操作は止めていない）。" % name]
    lines += ["- %s に %s の形" % (w, label) for w, label in hits[:8]]
    lines.append("直し方: 鍵の値を文から抜き、「<鍵の名> は環境の秘密に入れた」のように名だけで書いて出し直す。鍵が要る相手には"
                 "値を渡さず、環境の秘密（request_credential）で渡す。file に入っていれば file から抜く。")
    lines.append("誤って止めた時（作り物の見本の字が形に当たった等）: 値の表の guard.outbound_secret_allow に、その字に当てる"
                 "正規表現を足す（PR とレビューを通す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)


# ── number ──
def number_only(text, vals):
    """番号だけで中身の名の無い文の並び。"""
    import ask_shape     # ここで読む: 番号の形の正本が欠けて落ちても、鍵の照らしは道連れにしない
    exempt = [p for p in (vals.get("number_request_exempt") or []) if isinstance(p, str) and p]
    v2 = dict(vals)
    v2["ask_topic_stopwords_extra"] = list(vals.get("ask_topic_stopwords_extra") or []) + sorted(REQUEST_WORDS)
    v2["ask_inner_terms_extra"] = []
    out = []
    for raw in _SENT.findall(text or ""):
        s = raw.strip()
        if not s or any(re.search(p, s) for p in exempt) or REPORT_END.search(s):
            continue
        nums = [tok for name, tok in ask_shape._inner_hits(s, v2) if name == "番号"]
        if not nums:
            continue
        rest = ask_shape._URL.sub(" ", s)
        for tok in nums:
            rest = rest.replace(tok, " ")
        if not ask_shape._words({"question": rest}, v2):
            out.append(s[:60])
    return out


def request_texts(data):
    """人や他の窓が読む頼みの文の (場所, 字) の並び。欄の名で拾う（道具の名で口を切らない）。"""
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return []
    if name == "Bash":
        return [(w, t) for w, t, req in bash_out(str(ti.get("command") or ""), data) if req]
    if not (name.startswith("mcp__") or name in SEND_TOOLS):
        return []
    return [(k, ti[k]) for k in REQUEST_FIELDS if isinstance(ti.get(k), str)]


def check_number(data, vals):
    name = str(data.get("tool_name") or "")
    bad = []
    for _, text in request_texts(data):
        bad += number_only(text, vals)
    if not bad:
        return ""
    lines = ["[guard] 人や他の窓へ渡す頼み（%s）に、番号だけで中身の名の無い文があるので、送る前に止めた（核 §2・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。受けた窓とそれを見るオーナーは、番号が何を指すか知らない。" % name]
    lines += ["- 「%s」" % s for s in bad[:6]]
    lines.append("直し方: 番号に、それが何か（物の名と中身）を同じ文で添える（例: 「#3 やって」→「#3（請求書の送り先を"
                 "顧客ごとに変える直し）を進めて」）。番号を出さずに物の名だけで書いてもよい。")
    lines.append("誤って止めた時: 値の表の guard.number_request_exempt に、その文に当てる正規表現を足す（PR とレビューを通す）。")
    return "\n".join(lines)


# ── title ──
def title_findings(data, sw):
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or not (name.endswith(TITLE_SUFFIX) or name.endswith(CREATE_SUFFIX)):
        return []
    title = ti.get("title")
    if not isinstance(title, str) or not title.strip():
        return []            # 題の無い窓立ては、立った窓が自分で付ける（UserPromptSubmit の知らせが受け持つ）
    out = list(sw.title_shape(title))
    _, mark, work = sw.split_title(title)
    if name.endswith(CREATE_SUFFIX) and sw.HAND_TITLE.match(work):
        prompt = ti.get("prompt") if isinstance(ti.get("prompt"), str) else ""
        lack = [p for p in sw.HAND_PARTS if p not in prompt]
        if lack:
            out.append("手の窓を立てる頼みの文に %s が無い（①目的 ②手順 ③済んだ目印 ④済んだ後 を書いて渡す）" % "・".join(lack))
    return out


def check_title(data, vals):
    name = str(data.get("tool_name") or "")
    if not (name.endswith(TITLE_SUFFIX) or name.endswith(CREATE_SUFFIX)):
        return ""
    try:
        sw = _session_watch()
    except Exception:           # noqa: BLE001
        sw = None
    if sw is None:
        return ""                # 題の形は窓の一覧の見え方の話＝照らせない時は通す（鍵と違い外へ漏れる物ではない）
    found = title_findings(data, sw)
    if not found:
        return ""
    lines = ["[guard] 窓の題か手の窓の頼みが決まりの形でないので、出す前に止めた（細目 §4・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。"]
    lines += ["- " + m for m in found]
    lines.append("直し方: 題は `<種類><状態> <作業名>`（種類 🙋＝オーナーと話す窓／🤖＝別の窓へ返す窓・状態 ❓⏳✅〔✅ は 🤖 だけ〕"
                 "か無し）。手の窓は `🙋⏳ 手: <何を>` で、頼みの文に目的・手順・済んだ目印・済んだ後を書く。"
                 "細目は skill `session-watch:title-mark`。")
    return "\n".join(lines)


def check(data, vals):
    """止めるなら理由、通すなら ""。3 つは別々に走らせる（1 つが壊れても鍵の照らしを捨てない）。
    secret が壊れた時は止める（照らせない物は外へ出さない）。number と title が壊れた時はその見分けだけを通す。"""
    outs = []
    try:
        outs.append(check_secret(data, vals))
    except Exception as e:      # noqa: BLE001
        outs.append("[guard] 外へ渡す道具の入力の鍵を照らせないので、出す前に止めた（照らせない物は外へ出さない）: %s\n"
                    "  直し方: 値の表の guard.outbound_secret_allow の正規表現が崩れていないか見る。土台の plugin を市場から"
                    "入れ直す。" % type(e).__name__)
    for f in (check_number, check_title):
        try:
            outs.append(f(data, vals))
        except Exception as e:  # noqa: BLE001
            import sys
            sys.stderr.write("[guard] outbound.%s: %s\n" % (f.__name__, e))
    return "\n\n".join(o for o in outs if o)
