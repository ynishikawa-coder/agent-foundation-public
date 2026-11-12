#!/usr/bin/env python3
"""会話ログ（transcript の JSONL）だけを読む見張り。

拾う物（どれも会話ログの中だけで決まる＝環境の値・外の台帳・get_session の返りを見ない）:
  title    … 窓の題の目印（`<種類><状態> <作業名>`）が決まりどおりか
  close    … 返事の最後の締めの 1 行が型どおりか（オーナーへ返す窓がアーカイブを申し出ていないか）
  card     … 返事の 1 行目が 4 札（✅❓⏳🛑）のどれかで始まるか
  plain    … 答えを求める問いを、選択肢モーダル（AskUserQuestion）でなく平文で書いたか
  unanswered … モーダルで出した問いに、答えが返らないまま残っている物があるか
  chore    … AI が自分で打てる手（窓を立てる・合流・push 等）をオーナーに頼んで締めたか（返し先が別の窓の窓は見ない）
  wait     … このターンに題を ⏳（オーナーの作業待ち）にしたのに、頼み方の型（済んだ目印）が返事に無いか

窓の種類＝「オーナーが相手の窓か」（この窓が誰に返すか）。誰が立てたか（親の窓の有無・
parent_session_id・origin）では決めない。会話ログの最初の頼みの文に書かれた返し先だけで決める:
  `返し先=オーナー` → 🙋 ／ `返し先=session_…` → 🤖 ／ `（親窓 session_… の子）` → 🤖 ／ 書いていない → 決めない。
引き継ぎで立った窓（AI が立てた窓）でも、返し先がオーナーなら 🙋（締めも 🙋 の形）。

使い方:
  python3 session_watch.py <transcript.jsonl>   … 拾った物を 1 行ずつ出す（拾えば exit 1）
  python3 session_watch.py --hook               … Stop hook。標準入力の JSON の transcript_path を読み、
                                                  拾えば 1 回だけ止めて直させる（stop_hook_active なら止めない）
読めない・壊れた記録は黙って通す（見張りの故障で窓を止めない）。
"""
import json
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
DONE = "✅"      # 終わった・アーカイブしてよい（🤖 の窓だけ）
STATES = (ASKING, WAITING, DONE)
CARDS = ("✅", "❓", "⏳", "🛑")

# 最初の頼みの文に書く返し先（型はここ 1 か所）。
RETURN_TO = re.compile(r"返し先\s*[=＝:：]\s*(オーナー|session_[A-Za-z0-9]+)")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")

# 締めの 1 行の型（ここ 1 か所）。前後の ` と ** は許す。
CLOSE_LINE = re.compile(
    r"^[`*]*この窓: ?残り(?:なし(?: ?→ ?アーカイブしてよい)?"
    r"|あり(?:（[^）]+）)? ?→ ?(?:待つ（[^）]+）|答える(?:（[^）]+）)?))[`*。]*$")

# 平文の問いの型: 末尾が ？／❓ 札で始まる／最後 2 行に問いの言い回し（条件つきの頼みは除く）。
QEND = re.compile(r"[？?]\s*[)）」』*_`]*\s*$")
STRONG = re.compile(
    r"(よいですか|よろしいですか|いいですか|いいでしょうか|どうしますか|どうしましょう|しますか[？?]|ますか[？?]"
    r"|決めてください|選んでください|返してください|返事をください|OK／NG|OK/NG|ご判断|どちらに|どちらが"
    r"|どちらで|教えてください(?!.*(なら|たら)))")
COND = re.compile(r"(なら|たら|れば|場合)[^。]*(教えて|声をかけて|言って)")
CARD_LINE = re.compile(r"^[#>*\s]*(✅|❓|⏳|🛑)")

# オーナーに手を頼む（型の正本は細目 §4「オーナーに手を頼む」）。AI が自分で打てる手を頼む言い回し。
CHORE = re.compile(
    r"(窓を(立て|開い|作っ|閉じ)|アーカイブし|合流し|マージし|merge し|PR を(出し|作っ)|push し|プッシュし"
    r"|send_message し|レビュー窓を立て)"
    r"[^。\n]{0,6}?(てください|て下さい|ておいて|といて|てもらえ|てほしい|て欲しい|お願いします|お願い)")
QUOTED = re.compile(r"「[^」\n]*」|『[^』\n]*』|`[^`\n]*`")
SHAPED = "済んだ目印"   # 型まで書いた頼み＝人にしか打てない手として渡している
WAIT_CHECK = (
    "題を %s（オーナーの作業待ち）にしたのに、頼み方の型が返事に無い。締める前に 2 つ見る（細目 §4「オーナーに手を頼む」）: "
    "①頼む手が AI の道具で打てる手（窓を立てる・送る・閉じる・push・PR・合流・共有の物へ書く・調べる・見張りを置いて待つ）"
    "なら頼まずに今打ち、%s を外す ②人にしか打てない手（許しと設定・アカウント・PC やスマホにしか無い物・本番や社外の go の後の操作・"
    "人に会う）だけを、何のため／手順（1 番に 1 操作・開く URL・押す字そのまま・貼る物はコードブロック 1 個）／済んだ目印／"
    "済んだ後に AI がする事 の型で書き切る")


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
    """末尾の締めの 1 行を外す。(上の本文, 締めの 1 行 or None)。"""
    lines = [ln for ln in (text or "").rstrip().splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and CLOSE_LINE.match(lines[-1].strip()):
        return "\n".join(lines[:-1]), lines[-1].strip()
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
        phrase = False   # 待つ・残りなし の締めは、言い回しだけでは問いにしない
    return end or card or phrase


def owner_chore(text):
    """締めの本文（締めの 1 行・コード塊・表の行・引用を除く）で AI に打てる手を頼んでいれば、その字（無ければ None）。"""
    body, _ = split_close(text)
    body = "\n".join(x for x in strip_code(body).splitlines() if not x.lstrip().startswith("|"))
    if SHAPED in body:
        return None
    m = CHORE.search(QUOTED.sub("", body))
    return m.group(0) if m else None


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
            if (kind or tk) == AI and close and "残りなし" in close and tm != DONE:
                found.append(("title", "%s の窓が残りなしで締めるのに、題の状態が %s でない" % (AI, DONE)))
            set_wait = any(k == "title" and split_title(v)[1] == WAITING for k, v in log.turn)
            if tm == WAITING and set_wait and SHAPED not in closing:
                found.append(("wait", WAIT_CHECK % (WAITING, WAITING)))

    # 締めの 1 行と 1 行目の札（このターンに返事がある時だけ）
    if closing.strip():
        lines = [ln.strip() for ln in closing.splitlines() if ln.strip()]
        if not CARD_LINE.match(lines[0]):
            found.append(("card", "返事の 1 行目が 4 札（%s）で始まらない: %s" % ("／".join(CARDS), lines[0][:40])))
        if close is None:
            found.append(("close", "返事の最後の行が締めの 1 行の型でない: %s" % lines[-1][-60:]))
        elif "残りなし" in close and "アーカイブ" in close and kind == HUMAN:
            # アーカイブの申し出を足すかは各側が決める（核 §5）。オーナーへ返す窓は閉じるかをオーナーが決めるので申し出ない。
            found.append(("close", "%s の窓（オーナーへ返す窓）がアーカイブを申し出た＝締めは `この窓: 残りなし`" % HUMAN))

    # 平文の問い（このターンにモーダルが無いのに、問いで締めた）
    if closing.strip() and not log.turn_asked() and is_plain_question(closing):
        body, _ = split_close(closing)
        last = [x.strip() for x in strip_code(body).splitlines() if x.strip()]
        found.append(("plain", "問いを平文で書いた（モーダルで聞くか、推奨で決めて進む）: %s" % (last[-1][-60:] if last else "")))

    # 頼みすぎ（AI に打てる手をオーナーに頼んだ）。返し先が別の窓の窓は、オーナーへ頼んでいないので見ない。
    if closing.strip() and kind != AI:
        chore = owner_chore(closing)
        if chore:
            found.append(("chore", "AI が自分で打てる手をオーナーに頼んだ（頼まずに今打つ・人にしか打てない手だけを"
                                   "細目 §4 の型で渡す）: %s" % chore))

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


def hook_main(stdin):
    try:
        payload = json.loads(stdin or "{}")
    except ValueError:
        return ""
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return ""
    path = payload.get("transcript_path")
    found = watch(path) if path else []
    if not found:
        return ""
    reason = "[session-watch] この窓の返事を直す（題の目印・締め・聞き方・答えの無い問い・頼み方）:\n" + "\n".join(
        "- %s: %s" % f for f in found)
    return json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)


def main(argv):
    if len(argv) > 1 and argv[1] == "--hook":
        out = hook_main(sys.stdin.read())
        if out:
            sys.stdout.write(out)
        return 0
    if len(argv) != 2:
        sys.stderr.write("使い方: session_watch.py <transcript.jsonl> | --hook\n")
        return 2
    found = watch(argv[1])
    for code, msg in found:
        print("%s: %s" % (code, msg))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
