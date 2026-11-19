"""PreToolUse — 選択肢の画面（AskUserQuestion）の問いを、画面が人に出る前に照らす。崩れていれば AI だけを止めて書き直させる。

なぜ在るか: 確認ページには qa-html の検査（check.mjs）があるのに、選択肢の画面は文の決まり（核 §2・細目 §4）だけで、
照らす物が無かった。そのため、題が長い（背景を問いの文に詰め込む）・AI の中の言葉や番号や file 名が出る・関係ない話題を
1 画面にまとめる、が人に届いていた（オーナー同意 2026-11-19: 出す直前に照らし、AI だけ止めて書き直させる）。
止まるのは AI の呼び出しだけ（画面はまだ人に出ていない）。人の操作は何も止めない。

照らす物（どれも値の表 config/skill-values.json の "guard" で変えられる・決め打ちしない）:
  long   … 問いの文（question）が ask_question_max_chars 字を越える、または文が ask_question_max_sentences を越える
            （文の区切りは sentences 1 つで読む: 。．？?！!；;…⋯ と改行。字の数は空白を詰めて数える）
  inner  … 問い・見出し・選択肢（label と description）に、AI の中の言葉らしい字が在る
            （番号・版・file 名・path・識別子・窓の id・commit の印・`…` で囲んだ字）。足しは ask_inner_terms_extra
  topic  … 1 画面に 2 問以上あり、問いと見出しの語（漢字・カタカナ・英字の 2 字の並び）を共にしない組に分かれる
  rec    … 推奨の印の付け方が崩れている: 見出しに印（推奨の語か、★◎👍 の類の記号＝Unicode の記号の字）が決まりの形
            （見出しの末の「(推奨)」「（推奨）」「(Recommended)」）以外で在る・1 問に 2 つ以上・1 つ目でない選択肢に在る・
            「分からない」の選択肢に在る（細目 §4「推奨の印」）。印の見分けは rec_marked 1 つ（知らせの rec_kind も同じ物を読む）。
            どの問いに付けてよいか（作り方の分かれ道か）は字の形で見分けられないので見ない（残る穴）
知らせるだけの物（PostToolUse・notice・止めない）:
  rec_kind … 推奨の印が付いた問いの文が、済んだかの確認か意図・考えを聞く形に見える（印は作り方の分かれ道の問いだけ）。
            画面は出た後なので、AI に「印を外すべきだったか」を知らせるだけ（親窓の決定 2026-11-19: 止めずに知らせる）。
            形は値の表 ask_rec_notice_kinds（{名: [正規表現]}）で替え、ask_rec_notice_exempt（問いの文）で外す
誤って止めた時: 値の表 ask_shape_exempt（問いの文に当てる正規表現）に当たる問いは照らさない。ask_term_allow（見つけた字に
当てる正規表現）に当たる字は中の言葉と数えない。値の表は PR とレビューを通る＝窓の一存では外れない。
見分けは字の形の推し量り（意味は読まない）。残る穴は SKILL（guard-rules）と PR に書く。
"""
from __future__ import annotations

import re

ASK_TOOL = "AskUserQuestion"

_URL = re.compile(r"https?://\S+")
# AI の中の言葉らしい字（名 → 形）。人に向けた問いに出るなら日常の言葉に替える。
INNER = (
    ("番号", re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,5}\d{2,}(?:[-_]\d+)*(?![A-Za-z0-9])")),       # E02・Q202611-67
    ("番号", re.compile(r"[#＃]\d+")),                                                            # #616
    ("版の番号", re.compile(r"(?<![A-Za-z0-9])[vV]\d+(?:\.\d+)+")),                              # v0.21.0
    ("file 名", re.compile(r"[\w\-]+\.(?:py|md|json|jsonl|mjs|cjs|js|ts|tsx|jsx|html|ya?ml|sh|txt|csv|tsv|xlsx|toml|ini|cfg)"
                          r"(?![A-Za-z0-9])", re.I)),
    ("path", re.compile(r"(?:^|(?<=[\s(（「]))(?:~|\.{1,2})?/[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]*)*"
                       r"|(?<![A-Za-z0-9_.\-])(?=[A-Za-z0-9_.\-/]*[A-Za-z])[A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+){2,}")),
    ("英字の識別子", re.compile(r"(?<![A-Za-z0-9])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9])")),  # snake_case
    ("識別子", re.compile(r"[ぁ-んァ-ヶ一-龠ー]+_\d+")),                                         # 直し_0020
    ("窓の id", re.compile(r"session_[A-Za-z0-9]+")),
    ("commit の印", re.compile(r"(?<![A-Za-z0-9])(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![A-Za-z0-9])")),
    ("コードの字", re.compile(r"`[^`]+`")),
)
# 推奨の印: 形は 1 つだけ（見出しの末の「(推奨)」「（推奨）」「(Recommended)」）。見出しに推奨の語（推奨・おすすめ・recommend…）が
# それ以外の形で在れば、印の形の崩れとして止める（「非推奨」「推奨なし」「推奨どおり」も見出しには置かず説明へ）。
# 形を 1 つに閉じるので、言い回しの数だけ見分けを足さない（知らない形は既定で止める）。説明（description）の文の中の語は数えない。
# 記号の印（★☆◎⭐👍 等）は語の並びでなく字の種類（Unicode の記号 So）で読む＝記号を足して塞がない。
_REC_WORD = re.compile(r"推奨|おすすめ|お勧め|お薦め|オススメ|おススメ|イチオシ|recommend|suggested", re.I)
_REC_CANON = re.compile(r"\s*[(]\s*(?:推奨|recommended)\s*[)]\s*$", re.I)


def _flat(text):
    """照らす前に字を 1 つの形へ寄せる（全角→半角・互換の字→元の字＝NFKC）。"""
    import unicodedata
    return unicodedata.normalize("NFKC", str(text or ""))


def _rec_sign(text):
    """見出しの中の印らしい物（推奨の語か、記号の字）が在るか。"""
    import unicodedata
    t = _flat(text)
    return bool(_REC_WORD.search(t)) or any(unicodedata.category(c) == "So" for c in t)


def rec_marked(label):
    """選択肢の見出しに推奨の印が在るか（決まりの形でも崩れた形でも）。印の見分けの正本。"""
    return _rec_sign(label)


def rec_canon(label):
    """見出しの印が決まりの形だけか（末の「(推奨)」1 つで、ほかに印らしい物が無い）。"""
    t = _flat(label)
    return bool(_REC_CANON.search(t)) and not _rec_sign(_REC_CANON.sub("", t))
# 「分からない」の選択肢: 見出しの頭がそれである物だけ（「不明点を先に洗う」「unknowns を洗う」は数えない）
_DUNNO = re.compile(r"^\s*(?:(?:よく|まだ|今は)?\s*(?:分から|わから|判ら)(?:ない|ん|ず)|(?:分かり|わかり)ません|知らない|知りません"
                    r"|不明\s*(?:$|[(（])|unknown\s*(?:$|[(（])|(?:i\s+)?don'?t\s+know|not\s+sure)", re.I)
# 文の区切り（文の数を数える 1 つの読み手 sentences が読む）。；・…・改行でつないでも 1 文に数えない。
_SENT_END = re.compile(r"[。．？?！!；;…⋯\n]|\.{3}")


def sentences(text):
    """文の並び（中身の無い切れ端は数えない）。文の数の読み手の正本（session-watch の完了の言い切りも直に呼ぶ）。"""
    return [s.strip() for s in _SENT_END.split(str(text or "")) if s.strip()]
# 送り仮名（置き場・作り物・取り扱い）を詰めて 1 語にする。助詞（の・を・が…）を挟む所は詰めない。
_OKURI = re.compile(r"(?<=[一-龠々])(?:(?![のをがはにでともへやかよ])[ぁ-ゔ]){1,2}(?=[一-龠々])")
_RUN = re.compile(r"[一-龠々]{2,}|[ァ-ヶー]{2,}|[A-Za-z]{3,}")
# 話題を問わず問いに出る語（共にしても同じ話題とは言えない）。足しは ask_topic_stopwords_extra。
STOP = {
    "推奨", "確認", "場合", "今回", "必要", "選択", "選択肢", "問題", "質問", "対応", "作業", "方法", "内容", "理由", "結果",
    "予定", "今後", "現在", "以下", "以上", "前提", "判断", "決定", "変更", "追加", "削除", "一覧", "全部", "両方",
    "可能", "不要", "本当", "今日", "明日", "了解", "希望", "設定",
}



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check", "post": "notice"}

def _text(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


# 返事の本文（人への文）で数える物。核 §2「コード・パス・固有名は英語でよい」に背かないよう、file 名・path・版・
# 英字の識別子・`…` の字は数えない（返事ではコードの囲みと `…` を外してから当てる）。選択肢の画面は全部を数える。
REPLY_KINDS = ("番号", "窓の id", "識別子", "commit の印", "中の言葉")


def inner_terms(text, vals, kinds=None):
    """AI の中の言葉らしい字の一覧 [(名, 字)]。中の言葉の見分けの正本（選択肢の画面と返事の本文が共に呼ぶ）。
    kinds を渡せばその名だけ数える。URL は数えない。ask_term_allow に当たる字は数えない。"""
    return [(n, t) for n, t in _inner_hits(text, vals) if kinds is None or n in kinds]


# 中の言葉の見分けが読む値の表の鍵（型 regex＝読めない形は値の表の読み口 skill_values がその鍵ごと既定に倒し名指しする）
INNER_KEYS = ("ask_term_allow", "ask_inner_terms_extra")


def _patterns(vals, key):
    """値の表の正規表現の並び（型 regex の鍵＝値の表の読み口が読める形だけを渡す）。"""
    return [re.compile(p) for p in vals.get(key) or [] if isinstance(p, str) and p]


def _inner_hits(text, vals):
    allow = _patterns(vals, "ask_term_allow")
    extra = [("中の言葉", p) for p in _patterns(vals, "ask_inner_terms_extra")]
    body = _URL.sub(" ", text)
    hits = []
    for name, pat in INNER + tuple(extra):
        for m in re.finditer(pat, body):
            tok = m.group(0).strip()
            if not tok or any(a.search(tok) for a in allow):
                continue
            if (name, tok) not in hits:
                hits.append((name, tok))
    return hits


def _words(q, vals):
    """問いの文と見出しの語を 2 字の並びにして返す（共にする並びがあれば同じ話題とみなす）。"""
    stop = STOP | {w for w in (vals.get("ask_topic_stopwords_extra") or []) if isinstance(w, str)}
    grams = set()
    body = _OKURI.sub("", _text(q.get("question")) + " " + _text(q.get("header")))
    for run in _RUN.findall(body):
        run = run.lower()
        if run in stop:
            continue
        if run.isascii():
            grams.add(run)
            continue
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g not in stop:
                grams.add(g)
    return grams


def topic_groups(qs, vals):
    """問いを、語を共にする組へ分ける（つながりで束ねる）。戻り値＝組ごとの問いの番号の並び。"""
    ws = [_words(q, vals) for q in qs]
    parent = list(range(len(qs)))
    # 語が 1 つも取れない問い（「どちらにしますか」だけ等）は話題を決められない＝どの組にも数えない（誤って止めない）

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            if ws[i] & ws[j]:
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(qs)):
        if ws[i]:
            groups.setdefault(root(i), []).append(i)
    return sorted(groups.values())


def _rec_findings(q):
    """推奨の印の付け方の崩れ（形・数・位置・「分からない」）。印を付けてよい問いか（作り方の分かれ道か）は見ない。"""
    opts = [o for o in (q.get("options") or []) if isinstance(o, dict)]
    labels = [_text(o.get("label")) for o in opts]
    marked = [(i, lb) for i, lb in enumerate(labels) if rec_marked(lb)]
    why = []
    odd = [lb for _, lb in marked if not rec_canon(lb)]
    if odd:
        why.append("印の形が決まり（見出しの末の「(推奨)」）と違う（%s）" % "・".join("「%s」" % lb[:20] for lb in odd))
    if len(marked) >= 2:
        why.append("%d つの選択肢に在る（%s）" % (len(marked), "・".join("「%s」" % lb[:20] for _, lb in marked)))
    late = [lb for i, lb in marked if i != 0]
    if late:
        why.append("1 つ目でない選択肢に在る（%s）" % "・".join("「%s」" % lb[:20] for lb in late))
    dunno = [lb for _, lb in marked if _DUNNO.search(lb)]
    if dunno:
        why.append("「分からない」の選択肢に在る（%s）" % "・".join("「%s」" % lb[:20] for lb in dunno))
    return why


def _exempt(text, vals):
    return any(isinstance(p, str) and p and re.search(p, text) for p in (vals.get("ask_shape_exempt") or []))


def findings(qs, vals):
    """崩れの一覧 [(札, 文)]。無ければ []。"""
    max_chars = int(vals.get("ask_question_max_chars") or 0)
    max_sent = int(vals.get("ask_question_max_sentences") or 0)
    out = []
    checked = []
    for q in qs:
        if not isinstance(q, dict):
            continue
        text = _text(q.get("question"))
        if not text or _exempt(text, vals):
            continue
        checked.append(q)
        short = text[:40] + ("…" if len(text) > 40 else "")
        sents = sentences(q.get("question"))
        why = []
        if max_chars and len(text) > max_chars:
            why.append("%d 字（上限 %d 字）" % (len(text), max_chars))
        if max_sent and len(sents) > max_sent:
            why.append("%d 文（上限 %d 文）" % (len(sents), max_sent))
        if why:
            out.append(("long", "「%s」— 問いの文が長い: %s" % (short, "・".join(why))))
        fields = [("問い", text), ("見出し", _text(q.get("header")))]
        for o in q.get("options") or []:
            if isinstance(o, dict):
                fields.append(("選択肢「%s」" % _text(o.get("label"))[:20], _text(o.get("label")) + " " + _text(o.get("description"))))
        hits = []
        for where, t in fields:
            for name, tok in _inner_hits(t, vals):
                hits.append("%s の %s「%s」" % (where, name, tok[:40]))
        rec = _rec_findings(q)
        if rec:
            out.append(("rec", "「%s」— 推奨の印の付け方: %s" % (short, "／".join(rec))))
        if hits:
            out.append(("inner", "「%s」— AI の中の言葉らしい字: %s" % (short, "／".join(hits[:6])
                                                                + ("（ほか %d 件）" % (len(hits) - 6) if len(hits) > 6 else ""))))
    if len(checked) >= 2:
        groups = topic_groups(checked, vals)
        if len(groups) >= 2:
            shown = [" と ".join("「%s」" % _text(checked[i].get("question"))[:24] for i in g) for g in groups]
            out.append(("topic", "1 画面の問いが、語を共にしない %d つの話題に分かれている: %s" % (len(groups), "／".join(shown))))
    return out


HOW = {
    "long": "問いの文は「何を決めるか」の 1 文にする。背景・前提・材料は画面を出す前にチャットで見せ、違いと選ぶとどうなるかは"
            "選択肢の説明（description）に書く（細目 §4）。",
    "inner": "番号・版・file 名・path・識別子は、それが何かを日常の言葉で言い換える（例: 「Q202611-67」→「先週聞いた"
             "資料の置き場の問い」・「v0.21.0 の値」→「先週足した不足の時間の数え方」）。どうしても要る時は説明の文と一緒に"
             "チャットで見せ、画面には言い換えだけを出す。",
    "topic": "1 画面は 1 つの話題にする。話題ごとに画面を分けて続けて出す（どれも全部聞く・捨てない）。同じ話題なのに分かれて"
             "見えたなら、問いか見出しにその話題の語（例: 「置き場」）を入れる。",
    "rec": "推奨の印は作り方の分かれ道の問いだけに、1 問に 1 つ、1 つ目の選択肢の見出しの末に「(推奨)」の形で付け、理由はその選択肢の説明に書く"
           "（細目 §4「推奨の印」）。推せる案が 2 つあるなら問いを分けるか印を外す。「分からない」には付けない。"
           "意図・考えを聞く問いと済んだかの確認には印を付けない（付いていれば外す）。見出しの中身として推奨の語"
           "（「推奨環境に合わせる」等）を使っているなら、別の言葉に言い換えるか説明へ移す。",
}


# 推奨の印を付けない問いの形（既定）。字の形の推し量りなので、止めずに知らせるだけ。
REC_NOTICE_KINDS = {
    "済んだかの確認": [r"(?:終わり|済み|でき|入れ|完了し|設定し|保存し|押し|送り|届き|直り|動き|反映され|され)ましたか",
                   r"(?:済んで|終わって|完了して|入って|届いて|直って|動いて|反映されて|できて)(?:い)?ますか",
                   r"(?:終わった|済んだ|できた|入った|届いた|直った|動いた)(?:か|？|\?|$)", r"完了(?:しましたか|ですか|か)"],
    "意図・考えを聞く問い": [r"なぜ|どうして|何のため", r"どういう(?:意図|つもり|狙い|考え)", r"意図は|意図を(?:教え|聞かせ)|つもりですか|お考え",
                    r"どう思い|どう考え|どう感じ", r"お好み|好みは|好きな"],
}


def _search(pat, text, bad):
    """値の表の正規表現が壊れていても知らせ全体を落とさない（壊れた形は bad に集めて知らせる）。"""
    try:
        return re.search(pat, text)
    except re.error:
        if pat not in bad:
            bad.append(pat)
        return None


def rec_kind_notes(qs, vals, bad=None):
    """印（推奨の語）が付いた問いのうち、済んだか・意図の形に見える物 [(問いの頭, 名)]。"""
    bad = [] if bad is None else bad
    kinds = vals.get("ask_rec_notice_kinds")
    if not isinstance(kinds, dict) or not kinds:
        kinds = REC_NOTICE_KINDS
    exempt = [p for p in (vals.get("ask_rec_notice_exempt") or []) if isinstance(p, str) and p]
    out = []
    for q in qs:
        if not isinstance(q, dict):
            continue
        text = _text(q.get("question"))
        if not text or any(_search(p, text, bad) for p in exempt):
            continue
        labels = [_text(o.get("label")) for o in (q.get("options") or []) if isinstance(o, dict)]
        if not any(rec_marked(lb) for lb in labels):
            continue
        for name, pats in kinds.items():
            if any(isinstance(p, str) and p and _search(p, text, bad) for p in (pats if isinstance(pats, list) else [])):
                out.append((text[:40] + ("…" if len(text) > 40 else ""), str(name)))
                break
    return out


def notice(data, vals):
    """PostToolUse: 推奨の印が済んだか・意図の問いに付いていたら知らせる（止めない）。"""
    if str(data.get("tool_name") or "") != ASK_TOOL:
        return ""
    ti = data.get("tool_input")
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list) or not qs:
        tr = data.get("tool_response")
        qs = tr.get("questions") if isinstance(tr, dict) else None
    if not isinstance(qs, list) or not qs:
        return ""
    bad = []
    notes = rec_kind_notes(qs, vals, bad)
    if not notes and not bad:
        return ""
    lines = []
    if bad:
        lines.append("[guard] 値の表の guard.ask_rec_notice_kinds か ask_rec_notice_exempt の正規表現が壊れていて、その形は"
                     "照らせていない（直す）: %s" % "・".join(bad[:5]))
    if not notes:
        return "\n".join(lines)
    lines += ["[guard] 推奨の印が付いた問いが、印を付けない形に見える（知らせるだけ・止めていない。印は作り方の分かれ道の問い"
             "だけ＝細目 §4「推奨の印」）:"]
    lines += ["- 「%s」— %s に見える" % (t, n) for t, n in notes]
    lines.append("当たっていれば: 答えが印に引かれて寄っていないかを確かめ（済んだかは AI が確かめられる所を先に確かめる）、"
                 "次から印を外す。字の形だけ当たった誤りなら値の表の guard.ask_rec_notice_exempt（問いの文）に足す。")
    return "\n".join(lines)


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") != ASK_TOOL:
        return ""
    ti = data.get("tool_input")
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list) or not qs:
        return ""
    found = findings(qs, vals)
    if not found:
        return ""
    lines = ["[guard] 選択肢の画面の問いが読みにくい形なので、画面を出す前に止めた（オーナー同意 2026-11-19・人の操作は"
             "止めていない・画面はまだ人に出ていない）。"]
    lines += ["- [%s] %s" % (code, msg) for code, msg in found]
    lines.append("直し方:")
    for code in dict.fromkeys(c for c, _ in found):
        lines.append("- [%s] %s" % (code, HOW[code]))
    lines.append("誤って止めた時（日常の言葉の中で字の形だけ当たった等）: 値の表の guard.ask_term_allow（字）か "
                 "guard.ask_shape_exempt（問いの文）に正規表現を足す（PR とレビューを通す）。細目は skill `guard:guard-rules`。")
    return "\n".join(lines)
