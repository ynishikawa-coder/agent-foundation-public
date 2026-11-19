"""窓の形の正本 1 本: 窓の id の形・返し先・窓の種類・題の状態の印・窓を閉じる決まり。

なぜ在るか: 窓の id の形・返し先の見分け・種類の決め方・⏳ の意味・閉じる決まりが、session-watch・guard・checker の
file ごと（と決まりの文ごと）に別々に書かれ、同じ窓を片方は子の窓・片方はオーナーの窓と見たり、同じ id を片方は id と
見て片方は見なかったりした。ここを 1 つの正本にし、各 plugin は lib/window_shape.py（この file への symlink）を直に
読む（写さない。値の表の読み口と同じ symlink の置き方）。決まりの文（skill title-mark・細目）は下の *_RULE を
そのまま載せ、試験が一致を照らす。
"""
from __future__ import annotations

import re

# ── 窓の id ──
# 窓の id の形（`session_01…`）。`session_watch`・`session_id` のような名は窓の id でない（`0` の後に 15 字以上）。
SESSION_ID_PAT = r"session_0[A-Za-z0-9]{15,}"
SESSION_ID = re.compile(SESSION_ID_PAT)
# commit の書き手の記録（窓が commit の度に付ける `Claude-Session: <URL か id>` の行）。書いた窓の組はこれで読む
# （guard の pr_text・土台の scripts/pr_writer.py）。
COMMIT_SESSION = re.compile(r"^Claude-Session:\s*\S*?(%s)\s*$" % SESSION_ID_PAT, re.M)

# ── 種類と状態の印 ──
AI = "🤖"       # 別の窓か仕組みへ返す窓
HUMAN = "🙋"    # オーナーが相手の窓
KINDS = (AI, HUMAN)
ASKING = "❓"    # オーナーの答え待ち
WAITING = "⏳"   # 人の手か別の窓の返しを待って止まっている（STATE_RULE）
DONE = "✅"      # 終わった（🤖 の窓だけ）
STATES = (ASKING, WAITING, DONE)

# ── 返し先（最初の頼みの文に書く。型はここ 1 か所）──
RETURN_TO = re.compile(r"返し先\s*[=＝:：]\s*(オーナー|%s)" % SESSION_ID_PAT)
CHILD_OF = re.compile(r"（親窓\s*%s\s*の子）" % SESSION_ID_PAT)

# 人が打った頼みの記録（会話ログの行の origin.kind。Claude Code が頼みを受けた口で付ける＝文の中身では変わらない）。
HUMAN_ORIGINS = ("human", "person")

# 手の窓（題 `🙋⏳ 手: <何を>`）の作業名の頭と、頼みの文に書く 4 つ。
HAND_TITLE = re.compile(r"^手[:：]")
HAND_PARTS = ("目的", "手順", "済んだ目印", "済んだ後")

# 題を付ける道具（名の末尾で見る）。
SET_TITLE_SUFFIX = "set_session_title"

# 窓の種類の決まりの文（skill title-mark はこの文をそのまま載せる＝試験が照らす）。決め方は window_kind。
KIND_RULE = ("種類の決め方は 2 段: まず手の窓（作業名が `手:` で始まる窓）は返し先によらず `🙋`（相手はオーナー）。"
             "それ以外は窓の最初の頼みの文に書いた返し先だけで決める: `返し先=オーナー` → `🙋`／"
             "`返し先=session_…` か `（親窓 session_… の子）` → `🤖`（別の窓を指す返し先は手で書いた写しなので、頼みの行の記録が人の打った物でない時＝別の窓や仕組みから来た頼みの時だけ数える。オーナーが引き継ぎの文を貼った窓は `🤖` にしない）／どれも無い → 窓が自分で決める（点検は種類の食い違いを拾わない）。")

# 状態 ⏳ の決まりの文（正本はここ。skill title-mark はこの文をそのまま載せる＝試験が照らす。細目 §4 の窓の題の節は skill を指すだけで文を載せない）。見張りは ⏳ の窓を「待ちの窓」と読む
# （締めの残りを動かす手が無くても拾わない）。
STATE_RULE = ("`⏳` は、この窓が人の手か別の窓の返しを待って止まっている印（手の窓は必ず `⏳`・動いている間は付けない）。")

# 窓を閉じる決まりの文（細目 §5 はこの文をそのまま載せる。ほかの文は閉じる・閉じないを言い直さず、ここを指す）。
CLOSE_RULE = ("🤖 の窓は終わったら AI が閉じ、立てた子も閉じる。手の窓は頼んだ窓へ返したら閉じる。"
              "土台が新しくなった窓は 🙋 でも後継へ引き継いで閉じる。ほかの 🙋 の窓とオーナーが立てた窓は AI が閉じない。")


def split_title(title):
    """題を (種類, 状態, 作業名) に分ける。印が無ければ None。"""
    t = str(title or "").strip()
    kind = mark = None
    for k in KINDS:
        if t.startswith(k):
            kind, t = k, t[len(k):]
            break
    for s in STATES:
        if t.startswith(s):
            mark, t = s, t[len(s):]
            break
    return kind, mark, t.strip()


def seeded_by_record(row):
    """頼みの行が、人が打った物でなく別の窓・仕組みから来た事を、行の記録が示すか。
    記録: origin.kind が人の物でない（別の窓の create_session・send_message・知らせ等）か promptSource が system。
    記録が無い・読めない時は False（文だけで別の窓へ返す窓と決めない）。"""
    if not isinstance(row, dict):
        return False
    origin = row.get("origin")
    if isinstance(origin, dict) and isinstance(origin.get("kind"), str) and origin["kind"]:
        return origin["kind"] not in HUMAN_ORIGINS
    return row.get("promptSource") == "system"


def kind_of(first_prompt, seeded=False):
    """最初の頼みの文に書かれた返し先で種類を決める。書いていなければ None（決めない）。手の窓は見ない＝window_kind を使う。
    別の窓を指す返し先（写し）は、頼みの行の記録が人の打った物でない時（seeded＝seeded_by_record）だけ数える。"""
    m = RETURN_TO.search(first_prompt or "")
    if m and m.group(1) == "オーナー":
        return HUMAN
    if not seeded:
        return None
    if m or CHILD_OF.search(first_prompt or ""):
        return AI
    return None


def is_hand_title(title):
    """手の窓の題か（作業名が `手:` で始まる）。"""
    return bool(HAND_TITLE.match(split_title(title)[2]))


def window_kind(first_prompt, title=None, seeded=False):
    """窓の種類の正本（KIND_RULE）。手の窓（作業名が `手:`）は返し先によらず 🙋、ほかは最初の頼みの返し先
    （別の窓を指す返し先は seeded の時だけ数える）。"""
    if is_hand_title(title):
        return HUMAN
    return kind_of(first_prompt, seeded)


def title_in_tool(name, inp):
    """道具の呼び出しが題を付ける物なら、その題。違えば None。"""
    if str(name or "").endswith(SET_TITLE_SUFFIX) and isinstance(inp, dict):
        return str(inp.get("title") or "")
    return None
