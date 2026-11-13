#!/usr/bin/env python3
"""会話ログ（transcript の JSONL）だけを読む点検（手で回す・返事は止めない）。

拾う物（どれも会話ログの中だけで決まる＝環境の値・外の台帳・get_session の返りを見ない）:
  title    … 窓の題の目印（`<種類><状態> <作業名>`）が決まりどおりか
  close    … 返事の最後が締めの 2 行（`AI がこの後やること: …`／`あなたがやること: …`）か。あなたがやることが「なし」なら窓を閉じてよいかを、
             「なし」でなければ「これが済むまで <何> に進めません」を書いているか
  card     … 返事の 1 行目が 4 札（✅❓⏳🛑）のどれかで始まるか
  plain    … 答えを求める問いを、選択肢モーダル（AskUserQuestion）でなく平文で書いたか
  unanswered … モーダルで出した問いに、答えが返らないまま残っている物があるか
  rest     … 締めの `AI がこの後やること` が「なし」でないのに、この窓で残りを動かす手（子窓・送る・見張り・後で起こす・背で走る助手）を一度も打っていないか
  hand     … 手の窓（題 `🙋⏳ 手: <何を>`）の返事に、目的・手順・済んだ目印・済んだ後が揃っているか

窓の種類＝「オーナーが相手の窓か」（この窓が誰に返すか）。誰が立てたか（親の窓の有無・
parent_session_id・origin）では決めない。会話ログの最初の頼みの文に書かれた返し先だけで決める:
  `返し先=オーナー` → 🙋 ／ `返し先=session_…` → 🤖 ／ `（親窓 session_… の子）` → 🤖 ／ 書いていない → 決めない。

使い方:
  python3 session_watch.py <transcript.jsonl>  … 拾った物を 1 行ずつ出す（拾えば exit 1）
  python3 session_watch.py --remind            … UserPromptSubmit の hook。クラウドの窓で、まだ題に種類（🙋／🤖）を
                                                 付けていなければ、付けるよう AI に知らせる文を隣に出す（止めない）
読めない・壊れた記録は黙って通す。
"""
import json
import os
import re
import sys

ASK = "AskUserQuestion"
SET_TITLE_SUFFIX = "set_session_title"
REMOTE_PREFIX = "mcp__claude-code-remote__"

AI = "🤖"       # 返し先が別の窓か仕組み
HUMAN = "🙋"    # 返し先がオーナー（オーナーが話しかける窓）
KINDS = (AI, HUMAN)
ASKING = "❓"    # オーナーの答え待ち
WAITING = "⏳"   # オーナーの作業待ち
DONE = "✅"      # 終わった（🤖 の窓だけ）
STATES = (ASKING, WAITING, DONE)
CARDS = ("✅", "❓", "⏳", "🛑")

# 最初の頼みの文に書く返し先（型はここ 1 か所）。
RETURN_TO = re.compile(r"返し先\s*[=＝:：]\s*(オーナー|session_[A-Za-z0-9]+)")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")

# 締めの 2 行の型（ここ 1 か所）。前後の ` と ** は許す。
CLOSE_AI = re.compile(r"^[`*]*AI がこの後やること: ?\S")
CLOSE_OWNER = re.compile(r"^[`*]*あなたがやること: ?\S")
# あなたがやることの中身: なし→窓を閉じてよいか／ある→済むまで何に進めないか。
OWNER_NONE = re.compile(r"^[`*]*あなたがやること: ?なし")
CLOSE_OK = ("閉じて大丈夫", "閉じないで")
BLOCKS = "済むまで"

# 平文の問いの型: 末尾が ？／❓ 札で始まる／最後 2 行に問いの言い回し（条件つきの頼みは除く）。
QEND = re.compile(r"[？?]\s*[)）」』*_`]*\s*$")
STRONG = re.compile(
    r"(よいですか|よろしいですか|いいですか|いいでしょうか|どうしますか|どうしましょう|しますか[？?]|ますか[？?]"
    r"|決めてください|選んでください|返してください|返事をください|OK／NG|OK/NG|ご判断|どちらに|どちらが"
    r"|どちらで|教えてください(?!.*(なら|たら)))")
COND = re.compile(r"(なら|たら|れば|場合)[^。]*(教えて|声をかけて|言って)")
CARD_LINE = re.compile(r"^[#>*\s]*(✅|❓|⏳|🛑)")

# AI がこの後やることを動かす手（子窓や背で走る助手に頼む・PR を見張る・自分を後で起こす）。名の末尾で見る。
MOVE_TOOLS = ("create_session", "send_message", "send_later", "create_trigger", "fire_trigger",
              "subscribe_pr_activity", "ScheduleWakeup", "Monitor", "Workflow")


def moves(name, inp):
    """残りを動かす手か。助手（Agent）は背で走らせた時だけ（前で待つ助手はターンの中で終わる）。"""
    if name.endswith(MOVE_TOOLS):
        return True
    return name == "Agent" and inp.get("run_in_background") is not False

# 手の窓（題 `🙋⏳ 手: <何を>`）が書く 4 つ。
HAND_TITLE = re.compile(r"^手[:：]")
HAND_PARTS = ("目的", "手順", "済んだ目印", "済んだ後")


# ── 記録を読む ──────────────────────────────────────────────
def read_rows(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _content(row):
    msg = row.get("message")
    return msg.get("content") if isinstance(msg, dict) else None


def text_of(row):
    c = _content(row)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text") or "" for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_owner_text(row):
    """ターンの境界になる頼みの文か（道具の返り・見張りの差し戻し〔isMeta〕を除く）。"""
    if row.get("type") != "user" or row.get("isMeta") or "toolUseResult" in row:
        return False
    return bool(text_of(row).strip())


def blocks(row):
    """assistant 行の中身を出た順に [("text", str) | ("tool", (name, input))] で返す。"""
    c = _content(row)
    if isinstance(c, str):
        return [("text", c)] if c.strip() else []
    out = []
    for b in c if isinstance(c, list) else ():
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and (b.get("text") or "").strip():
            out.append(("text", b["text"]))
        elif b.get("type") == "tool_use":
            inp = b.get("input")
            out.append(("tool", (b.get("name") or "", inp if isinstance(inp, dict) else {})))
    return out


def strip_code(text):
    out, in_code = [], False
    for raw in (text or "").splitlines():
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            out.append(raw)
    return "\n".join(out)


class Log(object):
    """記録 1 本を、見張りが読む形に 1 回だけ並べ直す。"""

    def __init__(self, rows):
        self.events = []        # 出た順: ("title", str) / ("ask", [問い]) / ("answer", {問い: 答え}) / ("owner", str)
        self.first_prompt = ""
        self.cloud = False
        turn_start = 0
        for row in rows:
            if is_owner_text(row):
                if not self.first_prompt:
                    self.first_prompt = text_of(row)
                self.events.append(("owner", text_of(row)))
                turn_start = len(self.events)
                continue
            tur = row.get("toolUseResult")
            if isinstance(tur, dict) and "questions" in tur:
                ans = tur.get("answers") if isinstance(tur.get("answers"), dict) else {}
                self.events.append(("answer", {_norm(k): v for k, v in ans.items()}))
                continue
            if row.get("type") != "assistant":
                continue
            for kind, val in blocks(row):
                if kind == "text":
                    self.events.append(("text", val))
                    continue
                name, inp = val
                if name.startswith(REMOTE_PREFIX):
                    self.cloud = True
                if name.endswith(SET_TITLE_SUFFIX):
                    self.events.append(("title", str(inp.get("title") or "")))
                elif name == ASK:
                    qs = [_norm(q.get("question")) for q in inp.get("questions") or [] if isinstance(q, dict)]
                    self.events.append(("ask", [q for q in qs if q]))
                else:
                    self.events.append(("tool", name))
                    if moves(name, inp):
                        self.events.append(("move", name))
        self.turn = self.events[turn_start:]

    def closing_text(self):
        """このターンの最後の道具より後ろの返事（オーナーが最後に読む締めの本文）。"""
        out = []
        for kind, val in self.turn:
            if kind in ("tool", "title", "ask"):
                out = []
            elif kind == "text":
                out.append(val)
        return "\n".join(out)

    def turn_asked(self):
        return any(k == "ask" for k, _ in self.turn)


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


# ── 窓の種類と題 ──────────────────────────────────────────────
def kind_of(first_prompt):
    """最初の頼みの文に書かれた返し先で種類を決める。書いていなければ None（決めない）。"""
    m = RETURN_TO.search(first_prompt or "")
    if m:
        return HUMAN if m.group(1) == "オーナー" else AI
    if CHILD_OF.search(first_prompt or ""):
        return AI
    return None


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


def split_close(text):
    """末尾の締めの 2 行を外す。(上の本文, 締めの 2 行 or None)。"""
    lines = [ln for ln in (text or "").rstrip().splitlines() if ln.strip()]
    if len(lines) >= 2 and CLOSE_AI.match(lines[-2].strip()) and CLOSE_OWNER.match(lines[-1].strip()):
        return "\n".join(lines[:-2]), "\n".join(x.strip() for x in lines[-2:])
    return "\n".join(lines), None


def is_plain_question(text):
    """締めの 1 行を外した本文が、答えを求める問いで終わっているか。"""
    body, close = split_close(text)
    s = strip_code(body).strip()
    if not s:
        return False
    lines = [x for x in s.splitlines() if x.strip()]
    end = bool(QEND.search(s))
    card = bool(re.match(r"\s*(\*\*)?❓", s))
    phrase = bool(STRONG.search("\n".join(lines[-2:]))) and not COND.search(lines[-1])
    if close and "答える" not in close:
        phrase = False   # オーナーへの問いが無い締めは、言い回しだけでは問いにしない
    return end or card or phrase


# ── 見張り ──────────────────────────────────────────────────
def check(log):
    """拾った物を [(code, 説明)] で返す。"""
    found = []
    kind = kind_of(log.first_prompt)
    closing = log.closing_text()
    _, close = split_close(closing)

    # 題（クラウドの窓＝題の道具を使える窓だけ）
    if log.cloud:
        title = None
        answered = set()
        open_ask = False
        for i, (k, v) in enumerate(log.events):
            if k == "title":
                title = v
            elif k == "ask":
                in_turn = i >= len(log.events) - len(log.turn)
                if in_turn and split_title(title)[1] != ASKING:
                    found.append(("title", "問いを出す前に題の状態を %s にしていない（題: %s）" % (ASKING, title or "（無し）")))
                open_ask = True
            elif k == "answer":
                answered |= set(v)
                open_ask = not v
        if title is not None:
            tk, tm, _ = split_title(title)
            if tk is None:
                found.append(("title", "題の頭に種類（%s／%s）が無い（題: %s）" % (AI, HUMAN, title)))
            elif kind and tk != kind:
                found.append(("title", "題の種類が %s だが、この窓の返し先から種類は %s（題: %s）" % (tk, kind, title)))
            if tk == HUMAN and tm == DONE:
                found.append(("title", "%s の窓に %s は付けない（閉じるかはオーナーが決める）" % (HUMAN, DONE)))
            if tm == ASKING and not open_ask and answered:
                found.append(("title", "答えが返ったのに題に %s が残っている" % ASKING))
            if (kind or tk) == AI and close and close.startswith("AI がこの後やること: なし") and tm != DONE:
                found.append(("title", "%s の窓が AI がこの後やることなしで締めるのに、題の状態が %s でない" % (AI, DONE)))
            if tm == WAITING and HAND_TITLE.match(split_title(title)[2]) and closing.strip():
                lack = [p for p in HAND_PARTS if p not in closing]
                if lack:
                    found.append(("hand", "手の窓の返事に %s が無い（目的・手順〔貼る文は全部〕・済んだ目印・済んだ後を書く）"
                                  % "・".join(lack)))

    # 締めの 2 行と 1 行目の札（このターンに返事がある時だけ）
    if closing.strip():
        lines = [ln.strip() for ln in closing.splitlines() if ln.strip()]
        if not CARD_LINE.match(lines[0]):
            found.append(("card", "返事の 1 行目が 4 札（%s）で始まらない: %s" % ("／".join(CARDS), lines[0][:40])))
        if close is None:
            found.append(("close", "返事の最後が締めの 2 行（`AI がこの後やること: …`／`あなたがやること: …`）でない: %s"
                          % lines[-1][-60:]))
        else:
            owner = close.splitlines()[-1]
            if OWNER_NONE.match(owner) and not any(w in owner for w in CLOSE_OK):
                found.append(("close", "あなたがやることが「なし」なのに、この窓を閉じてよいか（閉じて大丈夫／まだ閉じないで）を書いていない"))
            if not OWNER_NONE.match(owner) and BLOCKS not in owner:
                found.append(("close", "あなたがやることがあるのに、「これが済むまで <何> に進めません」を書いていない"))

    # 動かしていない AI がこの後やること（核 §5: 締める前に AI が自分で動かす）
    #   待ちの題（❓ オーナーの答え待ち／⏳ 手待ち・子の返し待ち）と、この窓で既に動かした手（子窓・見張り）は拾わない。
    if close and not close.startswith("AI がこの後やること: なし"):
        last_title = None
        for k, v in log.events:
            if k == "title":
                last_title = v
        waiting = split_title(last_title)[1] in (ASKING, WAITING)
        moved = any(k == "move" for k, _ in log.events)
        if not (waiting or moved):
            found.append(("rest", "AI がこの後やることを書いたのに、この窓で動かしていない（子窓や背で走る助手に頼む・PR を見張る・"
                                  "後で起こすのどれかを打ってから締める）: %s" % close.splitlines()[0][:60]))

    # 平文の問い（このターンにモーダルが無いのに、問いで締めた）
    if closing.strip() and not log.turn_asked() and is_plain_question(closing):
        body, _ = split_close(closing)
        last = [x.strip() for x in strip_code(body).splitlines() if x.strip()]
        found.append(("plain", "問いを平文で書いた（モーダルで聞くか、推奨で決めて進む）: %s" % (last[-1][-60:] if last else "")))

    # 答えの無い問い（一度も答えが返っていない問い）
    asked, answered = [], set()
    for k, v in log.events:
        if k == "ask":
            asked.extend(q for q in v if q not in asked)
        elif k == "answer":
            answered |= set(v)
    for q in asked:
        if q not in answered:
            found.append(("unanswered", "答えの無い問いが残っている（出し直す・残りなしで締めない）: %s" % q[:60]))
    return found


def watch(path):
    try:
        return check(Log(read_rows(path)))
    except (OSError, ValueError, TypeError, AttributeError):
        return []


# ── 知らせる（UserPromptSubmit の hook・止めない）──────────────────
REMIND = (
    "[session-watch] この窓の題にまだ種類の印（%s／%s）が無い。最初の返事を書く前に、"
    "%s の `set_session_title` で題を `<種類><状態> <作業名>` に付ける（自分の session id は `get_session` を "
    "session_id を省いて読む）。種類: %s。形の細目は skill `session-watch:title-mark`。")


def titled(log):
    """この窓が題に種類の印を付けたことがあるか。"""
    return any(k == "title" and split_title(v)[0] for k, v in log.events)


def remind(data, env=None):
    """出す文（str）か None。クラウドの窓（題の道具を持つ窓）で、まだ種類の印を付けていない時だけ。"""
    env = os.environ if env is None else env
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() != "true":
        return None
    path = data.get("transcript_path") or ""
    log = Log(read_rows(path)) if path and os.path.exists(path) else Log([])
    if titled(log):
        return None
    kind = kind_of(log.first_prompt or str(data.get("prompt") or ""))
    if kind == AI:
        return None    # 別の窓へ返す子窓は、立てた親が create_session の title で題を付ける
    which = ("%s（最初の頼みの返し先から）" % kind) if kind else (
        "オーナーと話す窓なら %s・別の窓へ返す窓なら %s" % (HUMAN, AI))
    return REMIND % (HUMAN, AI, REMOTE_PREFIX.rstrip("_"), which)


def hook_remind(stdin):
    try:
        data = json.loads(stdin.read() or "{}")
        text = remind(data if isinstance(data, dict) else {})
    except Exception:          # noqa: BLE001  見張りの故障で窓を止めない
        return 0
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": text}}, ensure_ascii=False))
    return 0


def main(argv):
    if argv[1:] == ["--remind"]:
        return hook_remind(sys.stdin)
    if len(argv) != 2:
        sys.stderr.write("使い方: session_watch.py <transcript.jsonl>\n")
        return 2
    found = watch(argv[1])
    for code, msg in found:
        print("%s: %s" % (code, msg))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
