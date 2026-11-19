"""PreToolUse — 人や他の窓へ渡る道具の入力を、出る前に照らす。崩れていれば AI の呼び出しだけを止めて書き直させる。

なぜ在るか: 秘密を出さない（核 §1）・番号でなく物の名で頼む（核 §2）・窓の題の形と手の窓の 4 欄（細目 §4）は、文で
知らせるだけだった。AI が読み飛ばすと、鍵が他の窓・PR・Notion へ渡り、受けた窓とオーナーが「#3 やって」の中身を
知らず、形の崩れた題がオーナーの窓の一覧に出た（オーナー同意 2026-11-19: 文で知らせるだけで、AI が読み飛ばすと
そのままオーナーに届く所は、AI だけ止めて書き直させてよい）。止まるのは AI の呼び出しだけ。人の操作は何も止めない。

照らす物（見分けはどれも正本を直に呼ぶ＝写さない）:
  secret  … MCP の道具（名が mcp__ で始まる物）・Artifact・SendMessage の入力の全部の字と、Artifact で出す file の中身に、
            鍵・トークンの形がある。形の正本は公開の検査（public-guard/guard.py の SECRET_PATTERNS）。
            見つからない時は止める（照らせない物は外へ出さない）。在り処は AF_PUBLIC_GUARD → 土台の repo の根 → 市場の取り出し。
  どの道具が「人や他の窓へ頼みを渡す」「窓を立てる・題を付ける」かは、道具の名の末尾の列挙でなく、guard_common の
  1 つの読み手（read_call）が名を語に割った動詞の類（送る・投稿・作る・立てる・付ける）と、名の語が窓の類か、入力に文が
  在るかで読む（notion-spawn-session・Slack の投稿・別の名の窓立ても同じに見る）。
  number  … 人や他の窓へ頼みを渡す呼び出し（送る・窓を立てる）の入力の文に、番号（E02・#3 の形）だけで中身の名の無い
            文がある（「#3 やって」「#3 を実装して」「E02 の件」）。番号の見分けは ask_shape の中の言葉の見分け（INNER の
            「番号」）。中身の名とは、番号に添えた括弧・引用・「:」の後の説明か、番号の外の内容の語（ask_shape の語の切り方と
            止め語で数える）が NAME_MIN 個以上ある事（物の名と中身＝2 つ）。頼みの動きの語を並べた表は持たない。
  title   … 窓を立てる・窓に題を付ける呼び出しの title が題の形（`<種類><状態> <作業名>`）でない。手の窓の題
            （`🙋⏳ 手: <何を>`）で窓を立てるのに、頼みの文に 目的・手順・済んだ目印・済んだ後 が揃っていない。
            形の正本は session-watch の session_watch.py（title_shape・split_title・HAND_TITLE・hand_lack）。
            見つからない・版がずれて名が欠ける時は、題を付ける呼び出しを止める（照らせない物を黙って通さない）。
誤って止めた時: 値の表 config/skill-values.json の "guard" の outbound_secret_allow（当たった字に当てる正規表現・
作り物の見本だけ）・number_request_exempt（文に当てる正規表現）で外す。値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import os
import re

import ask_shape
import guard_common as G

HOOKS = {"pre": "check"}

SEND_TOOLS = ("SendMessage",)   # 鍵の照らしの口（mcp でない外へ渡す道具）
SW_NAMES = ("title_shape", "split_title", "HAND_TITLE", "hand_lack")   # 題の形の正本から呼ぶ名
NAME_MIN = 2                    # 番号の外に要る内容の語の数（物の名と中身）
MAX_READ = 2_000_000          # Artifact で出す file を照らす上限（バイト）
MAX_STRINGS = 2000

# 番号に添えた説明（括弧・引用・「:」の後に字が在る）
_ATTACHED = r"\s*(?:[(（「『【\[][^)）」』】\]]{2,}|[:：]\s*\S{2,})"


# ── 正本の在り処 ──
def _public_guard():
    path = os.environ.get("AF_PUBLIC_GUARD") or G.foundation_file(os.path.join("public-guard", "guard.py"))
    if not path or not os.path.isfile(path):
        return None
    return G.load_module("af_public_guard", path)


def _session_watch():
    path = os.environ.get("AF_SESSION_WATCH") or G.sibling_plugin_file(
        "session-watch", os.path.join("scripts", "session_watch.py"))
    if not path or not os.path.isfile(path):
        return None
    sw = G.load_module("af_session_watch", path)
    # 版がずれて正本に題の形の見分けが無い時は「読めない」と同じ扱い（古い語だけの照らしへ倒さない）
    return sw if all(hasattr(sw, n) for n in SW_NAMES) else None


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


def secret_hits(data, vals, pg):
    """[(場所, 札)]。当たった字そのものは返さない（止めた文にも鍵を出さない）。"""
    ti = data.get("tool_input")
    texts = _strings(ti)
    if str(data.get("tool_name") or "") == "Artifact" and isinstance(ti, dict):
        for path in _artifact_files(ti, data):
            try:
                if os.path.getsize(path) > MAX_READ:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    texts.append(("file %s" % path, f.read()))
            except OSError:
                continue
    allow = [p for p in (vals.get("outbound_secret_allow") or []) if isinstance(p, str) and p]
    hits = []
    for where, text in texts:
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
    if not (name.startswith("mcp__") or name in ("Artifact",) + SEND_TOOLS):
        return ""
    try:
        pg = _public_guard()
    except Exception as e:      # noqa: BLE001
        pg, err = None, str(e)
    else:
        err = ""
    if pg is None:
        return ("[guard] 外へ渡す道具の入力の鍵を照らせないので、出す前に止めた（照らせない物は外へ出さない）。\n"
                "  鍵の形の正本 public-guard/guard.py が見つからない／読めない%s。\n"
                "  直し方: 土台の plugin を市場（marketplace）から入れ直す。手元の置き場が違う時は環境変数 AF_PUBLIC_GUARD に"
                " guard.py の path を入れる。" % ((": " + err) if err else ""))
    hits = secret_hits(data, vals, pg)
    if not hits:
        return ""
    lines = ["[guard] 外へ渡す道具（%s）の入力に鍵・認証情報の形があるので、出す前に止めた（核 §1・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。" % name]
    lines += ["- %s に %s の形" % (w, label) for w, label in hits[:8]]
    lines.append("直し方: 鍵の値を文から抜き、「<鍵の名> は環境の秘密に入れた」のように名だけで書いて出し直す。鍵が要る相手には"
                 "値を渡さず、環境の秘密（request_credential）で渡す。Artifact の file に入っていれば file から抜く。")
    lines.append("誤って止めた時（作り物の見本の字が形に当たった等）: 値の表の guard.outbound_secret_allow に、その字に当てる"
                 "正規表現を足す（PR とレビューを通す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)


# ── number ──
def _content_runs(text, vals):
    """番号の外の内容の語（ask_shape の語の切り方＝漢字・カナの 2 字以上・英字 3 字以上、送り仮名を詰め、止め語を除く）と、
    番号でない中の言葉（file 名・path・コードの字）の並び。"""
    stop = ask_shape.STOP | {w for w in (vals.get("ask_topic_stopwords_extra") or []) if isinstance(w, str)}
    terms = [t for n, t in ask_shape._inner_hits(text, vals) if n != "番号"]
    body = text
    for t in terms:
        body = body.replace(t, " ")
    runs = [r for r in ask_shape._RUN.findall(ask_shape._OKURI.sub("", body)) if r.lower() not in stop]
    return runs + terms


def number_only(text, vals):
    """番号だけで中身の名の無い文の並び。"""
    exempt = [p for p in (vals.get("number_request_exempt") or []) if isinstance(p, str) and p]
    v2 = dict(vals)
    v2["ask_inner_terms_extra"] = []
    out = []
    for raw in ask_shape.sentences(text):      # 文の区切りの正本（ask_shape）を直に呼ぶ
        s = raw.strip()
        if not s or any(re.search(p, s) for p in exempt):
            continue
        nums = [tok for name, tok in ask_shape._inner_hits(s, v2) if name == "番号"]
        if not nums:
            continue
        if any(re.search(re.escape(tok) + _ATTACHED, s) for tok in nums):
            continue                       # 番号に説明を添えてある
        rest = ask_shape._URL.sub(" ", s)
        for tok in nums:
            rest = rest.replace(tok, " ")
        if len(_content_runs(rest, v2)) < NAME_MIN:
            out.append(s[:60])
    return out


def check_number(data, vals):
    call = G.read_call(data.get("tool_name"), data.get("tool_input"))
    if not call.asks:
        return ""
    text = "\n".join(t for w, t in call.texts if w != "title")    # 題の形は check_title が受け持つ
    bad = number_only(text, vals)
    if not bad:
        return ""
    lines = ["[guard] 他の窓へ渡す頼みに、番号だけで中身の名の無い文があるので、送る前に止めた（核 §2・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。受けた窓とそれを見るオーナーは、番号が何を指すか知らない。"]
    lines += ["- 「%s」" % s for s in bad[:6]]
    lines.append("直し方: 番号に、それが何か（物の名と中身）を同じ文で添える（例: 「#3 やって」→「#3（請求書の送り先を"
                 "顧客ごとに変える直し）を進めて」）。番号を出さずに物の名だけで書いてもよい。")
    lines.append("誤って止めた時: 値の表の guard.number_request_exempt に、その文に当てる正規表現を足す（PR とレビューを通す）。")
    return "\n".join(lines)


# ── title ──
def title_findings(data, sw):
    call = G.read_call(data.get("tool_name"), data.get("tool_input"))
    if call.title is None:
        return []            # 題の無い窓立ては、立った窓が自分で付ける（UserPromptSubmit の知らせが受け持つ）
    out = list(sw.title_shape(call.title))
    _, mark, work = sw.split_title(call.title)
    if call.spawns and sw.HAND_TITLE.match(work):
        prompt = "\n".join(t for w, t in call.texts if t is not call.title)
        lack = sw.hand_lack(prompt)
        if lack:
            out.append("手の窓を立てる頼みの文に %s が無い（①目的 ②手順 ③済んだ目印 ④済んだ後 を書いて渡す）" % "・".join(lack))
    return out


def check_title(data, vals):
    call = G.read_call(data.get("tool_name"), data.get("tool_input"))
    if call.title is None:
        return ""
    try:
        sw = _session_watch()
    except Exception as e:      # noqa: BLE001
        sw, err = None, "%s: %s" % (type(e).__name__, e)
    else:
        err = ""
    if sw is None:
        return ("[guard] 窓の題と手の窓の頼みの形を照らせないので、出す前に止めた（照らせない物を黙って通さない・人の操作は"
                "止めていない）。\n  題の形の正本 session-watch の session_watch.py が見つからない／読めない／版がずれて %s の"
                "どれかが無い%s。\n  直し方: 土台の plugin（session-watch と guard）を市場から同じ版で入れ直す。手元の置き場が"
                "違う時は環境変数 AF_SESSION_WATCH に session_watch.py の path を入れる。"
                % ("・".join(SW_NAMES), (": " + err) if err else ""))
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
    secret が壊れた時は止める（照らせない物は外へ出さない）。title の正本が読めない時も止める（check_title）。
    number と title の見分けそのものが壊れた（例外）時は、その見分けだけを通す。"""
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
