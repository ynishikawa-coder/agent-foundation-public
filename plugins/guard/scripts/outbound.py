"""PreToolUse — 人や他の窓へ渡る道具の入力を、出る前に照らす。崩れていれば AI の呼び出しだけを止めて書き直させる。

意図: 秘密を出さない（核 §1）・番号でなく物の名で頼む（核 §2）・窓の題の形と手の窓の 4 欄（細目 §4）を、外へ渡す前に照らす
（オーナー同意 2026-11-19: 文で知らせるだけで、AI が読み飛ばすとそのままオーナーに届く所は、AI だけ止めて書き直させてよい）。
止まるのは AI の呼び出しだけ。人の操作は何も止めない。
課題: 鍵が他の窓・PR・Notion へ渡り、受けた窓とオーナーが「#3 やって」の中身を
知らず、形の崩れた題がオーナーの窓の一覧に出た。
原因: これらの決まりは文で知らせるだけで、AI が読み飛ばすと照らす物が無かった。

照らす物（見分けはどれも正本を直に呼ぶ＝写さない）:
  secret  … MCP の道具（名が mcp__ で始まる物）・Artifact・SendMessage の入力の全部の字と、Artifact で出す file の中身に、
            鍵・トークンの形がある。形の正本は公開の検査（public-guard/guard.py の SECRET_PATTERNS）。
            見つからない時は止める（照らせない物は外へ出さない）。在り処は AF_PUBLIC_GUARD → 土台の repo の根 → 市場の取り出し。
            大きすぎる（MAX_READ 超）・開けない file は「照らした」扱いにせず、出した後（PostToolUse の notice）に名と訳を知らせる
            （止めに変えるかはオーナーの同意待ち）。
  number  … send_message（MCP）・SendMessage の文と create_session の頼みの文に、番号（E02・#3 の形）だけで中身の
            名の無い文がある（「#3 やって」「E02 の件」）。番号の見分けは ask_shape の中の言葉の見分け（INNER の「番号」）、
            中身の語の見分けは ask_shape の話題の語（_words）を直に呼ぶ。
  title   … set_session_title と create_session の title が題の形（`<種類><状態> <作業名>`・種類×状態の表に在る組み合わせ）
            でない。手の窓の題（`✋ <何を>`）で窓を立てるのに、頼みの文に 目的・手順・済んだ目印・済んだ後 が揃っていない。
            形の正本は session-watch の session_watch.py（TITLE_TABLE・title_shape・HAND_PARTS）。見つからない時は題を照らさない。
誤って止めた時: 値の表 config/skill-values.json の "guard" の outbound_secret_allow（当たった字の塊の全体に当てる正規表現・各行 ^…$・
作り物の見本だけ）・number_request_exempt（文に当てる正規表現）で外す。値の表は PR とレビューを通る＝窓の一存では外れない。
"""
from __future__ import annotations

import os
import re

import ask_shape
import guard_common as G

HOOKS = {"pre": "check", "post": "notice"}

SEND_TOOLS = ("SendMessage",)
SEND_SUFFIX = "__send_message"
CREATE_SUFFIX = "__create_session"
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
    path = os.environ.get("AF_SESSION_WATCH") or G.sibling_plugin_file(
        "session-watch", os.path.join("scripts", "session_watch.py"))
    if not path or not os.path.isfile(path):
        return None
    sw = G.load_module("af_session_watch", path)
    # 版がずれて正本に題の形の見分けが無い時は「読めない」と同じ扱い
    return sw if all(hasattr(sw, n) for n in ("title_shape", "split_title", "HAND", "HAND_PARTS", "KINDS", "KIND_NAMES", "table_doc")) else None


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


def _unreadable(path):
    """Artifact で出す file を照らせない訳（照らせれば ""）。大きすぎる・開けない物を「照らした」扱いにしない。"""
    try:
        size = os.path.getsize(path)
        if size > MAX_READ:
            return "大きすぎる（%d バイト・照らす上限 %d バイト）" % (size, MAX_READ)
        with open(path, "rb"):
            pass
    except OSError as e:
        return "開けない（%s）" % (e.strerror or e.__class__.__name__)
    return ""


def unread_files(data):
    """[(path, 訳)]。Artifact の publish で出す file のうち、鍵の形を照らせない物。"""
    ti = data.get("tool_input")
    if str(data.get("tool_name") or "") != "Artifact" or not isinstance(ti, dict):
        return []
    return [(p, why) for p, why in ((p, _unreadable(p)) for p in _artifact_files(ti, data)) if why]


def secret_hits(data, vals, pg, unread=None):
    """[(場所, 札)]。当たった字そのものは返さない（止めた文にも鍵を出さない）。
    照らせなかった file は黙って飛ばさず、unread（渡されれば）に (path, 訳) で積む。"""
    ti = data.get("tool_input")
    texts = _strings(ti)
    if str(data.get("tool_name") or "") == "Artifact" and isinstance(ti, dict):
        for path in _artifact_files(ti, data):
            why = _unreadable(path)
            if not why:
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        texts.append(("file %s" % path, f.read()))
                    continue
                except OSError as e:
                    why = "開けない（%s）" % (e.strerror or e.__class__.__name__)
            if unread is not None:
                unread.append((path, why))
    if G.SV.bad_pattern_rows(vals.get("outbound_secret_allow") or []):
        raise re.error("outbound_secret_allow に読めない形")   # 外す形が壊れたら鍵を外さず照らせないと止める
    allow = G.patterns(vals, "outbound_secret_allow")
    hits = []
    for where, text in texts:
        for label, pat in pg.SECRET_PATTERNS.items():
            for m in re.finditer(pat, text):
                if G.SV.hit(allow, m.group(0)) is not None:
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
    unread = []
    hits = secret_hits(data, vals, pg, unread)
    if not hits:
        return ""
    lines = ["[guard] 外へ渡す道具（%s）の入力に鍵・認証情報の形があるので、出す前に止めた（核 §1・オーナー同意 2026-11-19・"
             "人の操作は止めていない）。" % name]
    lines += ["- %s に %s の形" % (w, label) for w, label in hits[:8]]
    lines.append("直し方: 鍵の値を文から抜き、「<鍵の名> は環境の秘密に入れた」のように名だけで書いて出し直す。鍵が要る相手には"
                 "値を渡さず、環境の秘密（request_credential）で渡す。Artifact の file に入っていれば file から抜く。")
    lines += unread_lines(unread)
    lines.append("誤って止めた時（作り物の見本の字が形に当たった等）: 値の表の guard.outbound_secret_allow に、その字に当てる"
                 "正規表現を足す（PR とレビューを通す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)



def unread_lines(unread):
    if not unread:
        return []
    out = ["- 照らせなかった file（鍵が無いと確かめていない）:"]
    out += ["  - %s — %s" % (p, why) for p, why in unread[:8]]
    if len(unread) > 8:
        out.append("  - （ほか %d 件）" % (len(unread) - 8))
    return out


def notice(data, vals):
    """PostToolUse: Artifact で出した file に、鍵の形を照らせなかった物があれば名と訳を知らせる（止めない＝止めに変えるかは
    オーナーの同意を待つ）。照らせなかった file を「照らした」扱いで黙って通さない。"""
    unread = unread_files(data)
    if not unread:
        return ""
    lines = ["[guard] Artifact で出した file のうち、鍵・認証情報の形を照らせなかった物がある（知らせるだけ・止めていない。"
             "照らせた物だけを照らした）:"]
    lines += unread_lines(unread)[1:]
    lines.append("直し方: その file に鍵が無いかを自分で確かめる（大きすぎる物は分けるか小さくして出し直す・開けない物は path と"
                 "権限を直して出し直す）。鍵が入っていれば file から抜き、出した Artifact を出し直す。")
    return "\n".join(lines)

# ── number ──
def number_only(text, vals):
    """番号だけで中身の名の無い文の並び。"""
    exempt = G.patterns(vals, "number_request_exempt")
    v2 = dict(vals)
    v2["ask_topic_stopwords_extra"] = list(vals.get("ask_topic_stopwords_extra") or []) + sorted(REQUEST_WORDS)
    v2["ask_inner_terms_extra"] = []
    out = []
    for raw in _SENT.findall(text or ""):
        s = raw.strip()
        if not s or G.SV.hit(exempt, s) is not None:
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


def check_number(data, vals):
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return ""
    if name in SEND_TOOLS or name.endswith(SEND_SUFFIX):
        text = ti.get("message")
    elif name.endswith(CREATE_SUFFIX):
        text = ti.get("prompt")
    else:
        return ""
    bad = number_only(text if isinstance(text, str) else "", vals)
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
    name = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or not (name.endswith(TITLE_SUFFIX) or name.endswith(CREATE_SUFFIX)):
        return []
    title = ti.get("title")
    if not isinstance(title, str) or not title.strip():
        return []            # 題の無い窓立ては、立った窓が自分で付ける（UserPromptSubmit の知らせが受け持つ）
    out = list(sw.title_shape(title))
    kind, _, _ = sw.split_title(title)
    if name.endswith(CREATE_SUFFIX) and kind == sw.HAND:
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
    lines.append("直し方: 題は `<種類><状態> <作業名>`。種類は %s。状態は次の表の組み合わせだけ（表の正本は "
                 "session-watch の TITLE_TABLE）:" % "／".join("%s＝%s" % (k, sw.KIND_NAMES[k]) for k in sw.KINDS))
    lines.append(sw.table_doc())
    lines.append("手の窓は `%s <何を>` で、頼みの文に目的・手順・済んだ目印・済んだ後を書く。細目は skill `session-watch:title-mark`。"
                 % sw.HAND)
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
