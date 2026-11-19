#!/usr/bin/env python3
"""会話ログ（transcript の JSONL）だけを読む点検（手で回す点検と、返事の形の崩れだけを AI へ差し戻す Stop の hook）。

拾う物（どれも会話ログの中だけで決まる＝外の台帳・get_session の返りを見ない。値の表で外す形だけ読む）:
  title    … 窓の題の目印（`<種類><状態> <作業名>`）が決まりどおりか（題だけで決まる形は title_shape。
             guard の outbound が題を付ける口・窓を立てる口でもこれを直に呼ぶ＝題の形の正本）
  close    … 返事の最後が締めの 2 行（`AI がこの後やること: …`／`あなたがやること: …`）か。あなたがやることが「なし」なら窓を閉じてよいかを、
             「なし」でなければ「これが済むまで <何> に進めません」を書いているか
  card     … 返事の 1 行目が 4 札（✅❓⏳🛑）のどれかで始まるか
             （close と card は、一言で済む返事＝札も締めも無く SHORT_LINES 行以下・このターンに問いを出していない返事を見ない・細目 §5）
  plain    … 答えを求める問いを、選択肢モーダル（AskUserQuestion）でなく平文で書き、AI の今の読みも添えていないか
             （開いた問い＝意味・考え・前提はチャットで聞いてよい。その時は「AI の今の読み」を添える・細目 §4）
  idk      … 選択肢モーダルの問いに「分からない」の選択肢が無いか
  unanswered … モーダルで出した問いに、答えが返らないまま残っている物があるか
  rest     … 締めの `AI がこの後やること` が「なし」でないのに、この窓で残りを動かす手（子窓・送る・見張り・後で起こす・背で走る助手）を一度も打っていないか
  hand     … 手の窓（題 `🙋⏳ 手: <何を>`）の返事に、目的・手順・済んだ目印・済んだ後が揃っているか。
             手の窓でない窓が、あなたがやることに人の手の手順を直に書き、手の窓の URL を書いていないか
  inner    … 人への返事の本文（コードの囲み・`…`・URL を外した所）に、AI の中の言葉らしい字（番号・窓の id・
             `直し_0020` の形の識別子・commit の印）が在るか。見分けの正本は plugin guard の ask_shape.inner_terms
             （選択肢の画面と同じ物を直に呼ぶ）。返し先が別の窓の窓（🤖）は人への文でないので見ない
  time     … 返事の時刻が日本時間でない（Z・UTC・GMT・+09:00 以外の時差）か、日付つきの時刻に日本時間の印が無いか（核 §6）
  done     … 1 行目が ✅ の返事に、終わったと言い切らない語（ほぼ・大体・たぶん・はず 等）が終わりの語と同じ文に在るか（核 §7）
  secret   … 返事に鍵・トークンの形が在るか。形の正本は公開の検査 public-guard/guard.py の secret_labels（直に呼ぶ）
  neighbor … 上の inner・secret の正本（隣の plugin guard・公開の検査）が見つからず照らせないか

窓の種類＝「オーナーが相手の窓か」（この窓が誰に返すか）。誰が立てたか（親の窓の有無・
parent_session_id・origin）では決めない。会話ログの最初の頼みの文に書かれた返し先だけで決める:
  `返し先=オーナー` → 🙋 ／ `返し先=session_…` → 🤖 ／ `（親窓 session_… の子）` → 🤖 ／ 書いていない → 決めない。

使い方:
  python3 session_watch.py <transcript.jsonl>  … 拾った物を 1 行ずつ出す（拾えば exit 1）
  python3 session_watch.py --remind            … UserPromptSubmit の hook。クラウドの窓で、まだ題に種類（🙋／🤖）を
                                                 付けていなければ、付けるよう AI に知らせる文を隣に出す。前の返事の
                                                 あなたがやることに人の手の手順を直に書いていれば、手の窓で頼むよう
                                                 知らせる（どちらも止めない）
  python3 session_watch.py --stop              … Stop の hook。AI が返事を締めようとした時、STOP_CODES の札（題の印〔今の題で
                                                 直せる物・会話ログに題が無い時も〕・1 行目の札・締めの 2 行・平文の問い・中の言葉・
                                                 時刻・完了の言い切り・秘密）が崩れていれば、AI だけを差し戻して書き直させる
                                                 （decision=block。人の操作は止めない。同じターンで STOP_MAX 回まで）
読めない・壊れた記録は黙って通す。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)


# ── 隣の正本（写さず直に呼ぶ）──────────────────────────────────
#  中の言葉 … plugin guard の scripts/ask_shape.py（inner_terms）・値の表は scripts/guard_common.py
#  秘密の形 … 公開の検査 public-guard/guard.py（secret_labels。plugin の外＝市場の写しから読む）
#  探す順: 環境変数 → 同じ repo（plugins/session-watch の隣）→ 入れた plugin の同じ版 → 市場の写し → 入れた plugin の新しい版
#  どこにも無ければ None（check は neighbor の札を出す＝黙って照らしを抜かない）。
NEIGHBORS = {
    "ask_shape": ("AF_ASK_SHAPE", "plugins/guard/scripts/ask_shape.py", "guard", "scripts/ask_shape.py"),
    "guard_common": ("AF_GUARD_COMMON", "plugins/guard/scripts/guard_common.py", "guard", "scripts/guard_common.py"),
    "public_guard": ("AF_PUBLIC_GUARD", "public-guard/guard.py", None, None),
    "saimoku": ("AF_SAIMOKU", "plugins/core/細目.md", "core", "細目.md"),
}
_loaded = {}


def neighbor_path(name, env=None):
    env = os.environ if env is None else env
    env_name, repo_rel, plugin, rel = NEIGHBORS[name]
    cands = [env.get(env_name) or ""]
    up2 = os.path.dirname(os.path.dirname(PLUGIN_ROOT))       # repo: <repo> ／ 入れた形: cache/<市場>
    cands.append(os.path.join(up2, repo_rel))
    ver, market = os.path.basename(PLUGIN_ROOT), os.path.basename(up2)
    if plugin:
        cands.append(os.path.join(up2, plugin, ver, rel))
    cands.append(os.path.join(os.path.dirname(os.path.dirname(up2)), "marketplaces", market, repo_rel))
    if plugin:
        import glob
        cands += sorted(glob.glob(os.path.join(up2, plugin, "*", rel)), key=os.path.getmtime, reverse=True)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def neighbor(name):
    """隣の正本の module か None。読み込みは 1 回だけ（__pycache__ を作らない）。"""
    if name not in _loaded:
        mod = None
        path = neighbor_path(name)
        if path:
            try:
                import importlib.util
                sys.dont_write_bytecode = True
                spec = importlib.util.spec_from_file_location("af_sw_" + name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:      # noqa: BLE001  壊れた隣は無い物として扱う（neighbor の札で知らせる）
                mod = None
        _loaded[name] = mod
    return _loaded[name]


ASK = "AskUserQuestion"
SET_TITLE_SUFFIX = "set_session_title"
REMOTE_PREFIX = "mcp__claude-code-remote__"
ROOT_CAUSE = "直し: 拾われた所を出し直すだけで済ませず、細目 §3「まず構造を疑う」で原因から直す"

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
# 開いた問いをチャットで聞く時に添える AI の読み（細目 §4）。これが在る平文の問いは拾わない。
READING = re.compile(r"AI の(今の)?読み")
# 選択肢モーダルのどの問いにも置く選択肢（細目 §4）。
IDK = "分からない"
CARD_LINE = re.compile(r"^[#>*\s]*(✅|❓|⏳|🛑)")
# 完了の 4 状態と 1 行目の札の対応の正本は細目 §7 の表の「返事の 1 行目」の欄（ここに形を写さない）。
STATE_ROW = re.compile(r"^\|\s*(終わった|一部|止めた|続けられない)\s*\|[^|]*\|\s*`([^`]+)`\s*\|\s*$")


def state_lines(path=None):
    """細目 §7 の表から {状態: 1 行目}。読めない・4 つ揃わない時は None（呼ぶ側が neighbor で名指す）。"""
    path = path or neighbor_path("saimoku")
    try:
        from pathlib import Path
        rows = dict(m.groups() for m in map(STATE_ROW.match, Path(path).read_text(encoding="utf-8").splitlines()) if m)
    except Exception:  # noqa: BLE001  読めない正本は無い物として扱う（neighbor の札で知らせる）
        return None
    return rows if len(rows) == 4 else None


def done_line(rows):
    """「終わった」の 1 行目だけに当たる形（ほかの状態の 1 行目が同じ頭で始まっても当てない）。"""
    done = rows["終わった"]
    others = [v[len(done):] for k, v in rows.items() if k != "終わった" and v.startswith(done)]
    tail = "(?!%s)" % "|".join(r"\s*" + re.escape(o.strip()) for o in others) if others else ""
    loose = r"\s*".join(re.escape(c) for c in (done[0], done[1:]))   # 札と言葉の間の空白は許す（「✅ 終わった」）
    return re.compile(r"^[#>*\s]*" + loose + tail)
# 一言で済む返事（細目 §5）の行数の上限。札で始めた返事・問いを出したターンは長さに関わらず札と締めを見る。
SHORT_LINES = 3

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
# 頼んだ窓のあなたがやること: 手の窓の URL だけを書く（細目 §4）。手順を直に書いたかを型で見る。
HAND_URL = re.compile(r"claude\.ai/code/session_[A-Za-z0-9]+")
STEP_NUM = re.compile(r"(?:^|\s)(?:[1-9][.)．）](?!\d)\s*\S|[①-⑨])", re.M)
STEP_VERB = re.compile(r"(開[くいけ]|貼[るっり]|足[すし]|押[すし]|入れ|入力|追加|クリック|コピー|選[ぶん]|設定[しす]|保存|ログイン)")
STEP_ARROW = re.compile(r"[→＞>]")
ANSWER = re.compile(r"(答え|問い|選択肢)")


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
            if row.get("type") == "user" and row.get("isMeta") and "toolUseResult" not in row:
                self.events.append(("meta", ""))     # 見張りの差し戻し: ターンは続くが、締めの本文はここから数え直す
                continue
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
                    items = [q for q in inp.get("questions") or [] if isinstance(q, dict)]
                    qs = [_norm(q.get("question")) for q in items]
                    self.events.append(("ask", [q for q in qs if q]))
                    lack = [_norm(q.get("question")) for q in items if not has_idk(q)]
                    if lack:
                        self.events.append(("noidk", lack))
                else:
                    self.events.append(("tool", name))
                    if moves(name, inp):
                        self.events.append(("move", name))
        self.turn = self.events[turn_start:]

    def closing_text(self):
        """このターンの最後の道具より後ろの返事（オーナーが最後に読む締めの本文）。"""
        out = []
        for kind, val in self.turn:
            if kind in ("tool", "title", "ask", "meta"):
                out = []
            elif kind == "text":
                out.append(val)
        return "\n".join(out)

    def turn_asked(self):
        return any(k == "ask" for k, _ in self.turn)


def has_idk(question):
    """選択肢の中に「分からない」が在るか。"""
    for o in question.get("options") or []:
        if isinstance(o, dict) and IDK in str(o.get("label") or ""):
            return True
    return False


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


def title_shape(title):
    """題そのものの形の崩れ [説明]（会話ログを見ずに題だけで決まる物）。題を付ける口・立てる口（guard の outbound）も
    これを直に呼ぶ＝題の形の決まりの正本はここ 1 つ。"""
    kind, mark, name = split_title(title)
    out = []
    if kind is None:
        out.append("題の頭に種類（%s／%s）が無い（題: %s）" % (AI, HUMAN, title))
    if not name:
        out.append("題に作業名が無い（題: %s）" % title)
    if kind == HUMAN and mark == DONE:
        out.append("%s の窓に %s は付けない（閉じるかはオーナーが決める）" % (HUMAN, DONE))
    if HAND_TITLE.match(name):
        if kind != HUMAN or mark != WAITING:
            out.append("手の窓の題は `%s%s 手: <何を>`（題: %s）" % (HUMAN, WAITING, title))
        if not HAND_TITLE.sub("", name).strip():
            out.append("手の窓の題の `手:` の後に何を頼むかが無い（題: %s）" % title)
    return out


def split_close(text):
    """末尾の締めの 2 行を外す。(上の本文, 締めの 2 行 or None)。"""
    lines = [ln for ln in (text or "").rstrip().splitlines() if ln.strip()]
    if len(lines) >= 2 and CLOSE_AI.match(lines[-2].strip()) and CLOSE_OWNER.match(lines[-1].strip()):
        return "\n".join(lines[:-2]), "\n".join(x.strip() for x in lines[-2:])
    return "\n".join(lines), None


def owner_section(text):
    """返事の最後の `あなたがやること:` の行から末尾まで（コードブロックも含む）の中身。無ければ None。"""
    lines = (text or "").rstrip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if CLOSE_OWNER.match(lines[i].strip()):
            head = re.sub(r"^[`*]*あなたがやること: ?", "", lines[i].strip())
            return "\n".join([head] + lines[i + 1:])
    return None


def owner_steps(text):
    """あなたがやることに人の手の手順を直に書き、手の窓の URL が無いか。
    手順らしい物＝番号付きの手順・コードブロック・→ の並び・手の動詞が 2 つ以上。
    「なし」・URL がある・答える事（問い）だけは拾わない。"""
    sec = owner_section(text)
    if sec is None or OWNER_NONE.match("あなたがやること: " + sec.strip()) or HAND_URL.search(sec):
        return False
    if "```" in sec:
        return True                      # 貼る文がある＝手順
    if ANSWER.search(sec):
        return False                     # 問いに答える事（番号の付いた選択肢を含む）は手の窓に回さない
    return bool(STEP_NUM.search(sec)) or len(STEP_ARROW.findall(sec)) >= 2 or len(STEP_VERB.findall(sec)) >= 2


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
    if close and OWNER_NONE.match(close.splitlines()[-1]):
        phrase = False   # あなたがやることが「なし」の締めは、言い回しだけでは問いにしない
    return end or card or phrase


# ── 返事の本文の言葉（人への文）────────────────────────────────
INLINE_CODE = re.compile(r"`[^`\n]+`")
URL = re.compile(r"https?://\S+")
QUOTED = re.compile(r"「[^」\n]*」|『[^』\n]*』|\"[^\"\n]*\"")

# 時刻（核 §6）: 人に見せる時刻は日本時間。印は「日本時間」「JST」「+09:00」。
CLOCK = re.compile(r"(?<![\d:])(\d{1,2})[:：](\d{2})(?:[:：]\d{2})?(?:\.\d+)?(?![\d])")
ZONE = re.compile(r"^\s*(Z(?![A-Za-z])|UTC|GMT|[+-]\d{2}:?\d{2}(?!\d))")
JST_LINE = re.compile(r"日本時間|JST|\+09:?00")      # 同じ行に印があれば、その行の印の無い時刻は日本時間と読む
DATE_BEFORE = re.compile(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|(?<![\d/])\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)"
                         r"\s*(?:[（(][月火水木金土日][)）])?\s*T?\s*$")

# 完了の言い切り（核 §7）: ✅ の返事で、終わりの語と同じ文に言い切らない語。
HEDGE = re.compile(r"ほぼ|大体|だいたい|たぶん|多分|おそらく|恐らく|はず(?![しすさせれ])|と思(?:う|い|われ)|かもしれ")
FINISH = re.compile(r"終わ|済ん|済み|完了|直っ|直り|直せ|直した|でき|出来|通っ|通る|通り|緑|動い|動く|効い|効く|揃っ|片付")
AHEAD = re.compile(r"次の|次回|来週|来月|明日|今後|あとで|後で|予定|見込み")   # 先の事の見込みは完了の言い切りでない
PAST = re.compile(r"た\s*$|た[、,）)」]|ました|でした|済み|完了")   # 過去の言い切り（見込みの語が在っても数える）
SENTENCE = re.compile(r"[^。！？!?\n]+")


def reply_exempt(data=None):
    """値の表の session-watch.watch-log.reply_exempt（行に当てる正規表現の並び）。当たる行は inner・time・done で見ない。
    (通る形の並び, 通らない形の並び)。通らない形（正規表現として読めない）は捨てる＝1 つの誤りで照らしを全部止めない。"""
    G = neighbor("guard_common")
    got = G.table("session-watch", data) if G else {}
    got = got.get("watch-log") if isinstance(got, dict) else None
    pats = got.get("reply_exempt") if isinstance(got, dict) else None
    ok, bad = [], []
    for p in pats or []:
        if not isinstance(p, str) or not p:
            continue
        try:
            re.compile(p)
            ok.append(p)
        except re.error:
            bad.append(p)
    return ok, bad


def prose(text, exempt=()):
    """人へ見せる本文: コードの囲み・`…`・URL を外し、外す形に当たる行を除く。"""
    out = []
    for ln in strip_code(text).splitlines():
        if any(re.search(p, ln) for p in exempt):
            continue
        out.append(URL.sub(" ", INLINE_CODE.sub(" ", ln)))
    return "\n".join(out)


def time_hits(body):
    """日本時間でない時刻・日付つきで印の無い時刻の並び [(字, 訳)]。"""
    hits = []
    for ln in body.splitlines():
        for m in CLOCK.finditer(ln):
            if int(m.group(1)) > 23 or int(m.group(2)) > 59:
                continue
            after, before = ln[m.end():m.end() + 24], ln[max(0, m.start() - 24):m.start()]
            z = ZONE.match(after)
            if z and not re.match(r"^\s*\+09:?00", after):
                hits.append((m.group(0) + z.group(1), "日本時間でない"))
            elif not z and DATE_BEFORE.search(before) and not JST_LINE.search(ln):
                hits.append(((DATE_BEFORE.search(before).group(1) + " " + m.group(0)).strip(), "日本時間の印が無い"))
    return hits


def hedge_hits(body):
    """終わりの語と同じ文にある言い切らない語の並び（「」の中の言葉＝引いた言葉は数えない）。"""
    out = []
    for sent in SENTENCE.findall(QUOTED.sub(" ", body)):
        h = HEDGE.search(sent)
        if h and FINISH.search(sent) and not (AHEAD.search(sent) and not PAST.search(sent)):
            out.append(sent.strip()[:40])
    return out


def ai_window(log):
    """返し先が別の窓の窓（🤖）か。最初の頼みの返し先か、最後の題の種類で決める。"""
    if kind_of(log.first_prompt) == AI:
        return True
    last = None
    for k, v in log.events:
        if k == "title":
            last = v
    return split_title(last)[0] == AI


def words(log, closing, data=None):
    """返事の本文の言葉の札 [(code, 説明)]: inner・time・done・secret・neighbor。"""
    found = []
    if not closing.strip():
        return found
    # 照らしは札ごとに分けて走らせる: 1 つ（値の表の誤った形・隣の正本の故障）が壊れても、他の札は黙って抜けない。
    #   壊れた札は neighbor で名指す（AI には直せない＝窓ごとに 1 回だけ差し戻す）。
    def part(name, fn):
        try:
            fn()
        except Exception as e:      # noqa: BLE001
            found.append(("neighbor", "%s の照らしが壊れて照らせない（%s: %s）" % (name, type(e).__name__, str(e)[:60])))

    exempt, bad = reply_exempt(data)
    if bad:
        found.append(("neighbor", "値の表 session-watch.watch-log.reply_exempt に正規表現として読めない形がある（捨てて照らした）: %s"
                      % "／".join(b[:30] for b in bad[:3])))
    body = prose(closing, exempt)

    def secret():
        PG = neighbor("public_guard")
        if PG is None or not hasattr(PG, "secret_labels"):
            found.append(("neighbor", "秘密の形の正本（公開の検査 public-guard/guard.py）が見つからず、返事の鍵を照らせない"))
            return
        labels = PG.secret_labels(closing)
        if labels:
            found.append(("secret", "返事に秘密の形がある（%s）。値を消し、在り処の名だけを書く（核 §1）" % "・".join(labels)))

    def inner():
        if ai_window(log):
            return
        A, G = neighbor("ask_shape"), neighbor("guard_common")
        if A is None or not hasattr(A, "inner_terms") or G is None:
            found.append(("neighbor", "中の言葉の正本（plugin guard の ask_shape・guard_common）が見つからず、返事の言葉を照らせない"))
            return
        vals = G.values(data)
        bad = A.bad_patterns(vals) if hasattr(A, "bad_patterns") else []
        if bad:
            found.append(("neighbor", "値の表の %s に正規表現として読めない形がある（捨てて照らした・値の表を直す）"
                          % "／".join("guard.%s「%s」" % (k, p[:30]) for k, p in bad[:3])))
        hits = A.inner_terms(body, vals, A.REPLY_KINDS)
        if hits:
            shown = "／".join("%s「%s」" % (n, t[:30]) for n, t in hits[:6])
            found.append(("inner", "人への返事に AI の中の言葉らしい字: %s%s" % (
                shown, "（ほか %d 件）" % (len(hits) - 6) if len(hits) > 6 else "")))

    def time():
        th = time_hits(body)
        if th:
            found.append(("time", "時刻が日本時間の形でない: %s" % "／".join("「%s」%s" % (t, why) for t, why in th[:4])))

    def done():
        lines = [ln.strip() for ln in closing.splitlines() if ln.strip()]
        if lines and re.match(r"^[#>*\s]*✅", lines[0]):
            hh = hedge_hits(body)
            if hh:
                found.append(("done", "✅ の返事に、終わったと言い切らない語がある: %s" % "／".join("「%s」" % x for x in hh[:3])))

    for name, fn in (("secret", secret), ("inner", inner), ("time", time), ("done", done)):
        part(name, fn)
    return found


# ── 見張り ──────────────────────────────────────────────────
NO_TITLE = "題の印が会話ログに無い"
ASK_BEFORE = "問いを出す前に題の状態を"   # 過ぎた事（今の題を直しても消えない）＝差し戻しには使わない


def check(log, closing=None, data=None):
    """拾った物を [(code, 説明)] で返す。closing を渡せば、それを締めの返事として見る（Stop の hook）。
    data は hook の入力（値の表の在り処＝cwd を読む）。"""
    found = []
    kind = kind_of(log.first_prompt)
    closing = log.closing_text() if closing is None else closing
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
                    found.append(("title", ASK_BEFORE + " %s にしていない（題: %s）" % (ASKING, title or "（無し）")))
                open_ask = True
            elif k == "answer":
                answered |= set(v)
                open_ask = not v
        if title is None and closing.strip():
            found.append(("title", NO_TITLE + "（親が窓を立てた時に付けた題は会話ログの外で照らせない）。`get_session` を "
                                   "session_id を省いて読み、今の題を `set_session_title` で `<種類><状態> <作業名>` に付け直す"
                                   "（同じ題でもよい。会話ログに載れば照らせる）"))
        if title is not None:
            tk, tm, _ = split_title(title)
            found += [("title", m) for m in title_shape(title)]
            if tk is not None and kind and tk != kind:
                found.append(("title", "題の種類が %s だが、この窓の返し先から種類は %s（題: %s）" % (tk, kind, title)))
            if tm == ASKING and not open_ask and answered:
                found.append(("title", "答えが返ったのに題に %s が残っている" % ASKING))
            # ✅ は「終わった」（核 §7）の印。AI の手が尽きた（AI がこの後やること: なし）とは結ばない。
            first = next((ln.strip() for ln in closing.splitlines() if ln.strip()), "")
            rows = state_lines() if (kind or tk) == AI and CARD_LINE.match(first) else None
            if (kind or tk) == AI and CARD_LINE.match(first) and rows is None:
                found.append(("neighbor", "完了の 4 状態と 1 行目の対応（細目 §7 の表）が読めず、題の ✅ を照らせない"))
            elif rows is not None:
                done = bool(done_line(rows).match(first))
                if done and tm != DONE:
                    found.append(("title", "%s の窓が %s終わった で報告するのに、題の状態が %s でない" % (AI, DONE, DONE)))
                elif not done and tm == DONE:
                    found.append(("title", "%s の窓が 終わった でない札（止まった・一部・待ち・問い）で締めるのに、題が %s" % (AI, DONE)))
            if tm == WAITING and HAND_TITLE.match(split_title(title)[2]) and closing.strip():
                lack = [p for p in HAND_PARTS if p not in closing]
                if lack:
                    found.append(("hand", "手の窓の返事に %s が無い（目的・手順〔貼る文は全部〕・済んだ目印・済んだ後を書く）"
                                  % "・".join(lack)))

    # 頼んだ窓のあなたがやること（手の窓の URL だけ・細目 §4）
    if not in_hand_window(log) and owner_steps(closing):
        found.append(("hand", HAND_ASK))

    # 締めの 2 行と 1 行目の札（このターンに返事がある時だけ）
    lines = [ln.strip() for ln in closing.splitlines() if ln.strip()]
    short = bool(lines) and not CARD_LINE.match(lines[0]) and close is None and len(lines) <= SHORT_LINES and not log.turn_asked()
    if lines and not short:
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
    if closing.strip() and not log.turn_asked() and is_plain_question(closing) \
            and not READING.search(split_close(closing)[0]):
        body, _ = split_close(closing)
        last = [x.strip() for x in strip_code(body).splitlines() if x.strip()]
        found.append(("plain", "問いを平文で書いた（選ぶ問いはモーダルで、開いた問いは AI の今の読みを添えて聞くか、AI が決めて進む）: %s" % (last[-1][-60:] if last else "")))

    # 返事の本文の言葉（中の言葉・時刻・完了の言い切り・秘密）
    found += words(log, closing, data)

    # 「分からない」の無いモーダルの問い（細目 §4）
    for k, v in log.events:
        if k == "noidk":
            for q in v:
                found.append(("idk", "選択肢の画面の問いに「分からない」の選択肢が無い（足して出す）: %s" % q[:60]))

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
    """拾った物の並び。ログが読めなければ OSError を上げる（読めない＝拾う物なし＝緑、に化かさない）。"""
    rows = read_rows(path)
    try:
        return check(Log(rows))
    except (ValueError, TypeError, AttributeError):
        return []


# ── 知らせる（UserPromptSubmit の hook・止めない）──────────────────
REMIND = (
    "[session-watch] この窓の題にまだ種類の印（%s／%s）が無い。最初の返事を書く前に、"
    "%s の `set_session_title` で題を `<種類><状態> <作業名>` に付ける（自分の session id は `get_session` を "
    "session_id を省いて読む）。種類: %s。形の細目は skill `session-watch:title-mark`。")


REMIND_CHILD = ("[session-watch] 親が付けた題は会話ログに載らず、返事の差し戻し（Stop）が照らせない。最初の返事の前に "
                "`get_session` を session_id を省いて読み、今の題を `set_session_title` で付け直す（形が合っていれば同じ題でよい）。")


HAND_ASK = ("あなたがやることに人の手の手順を直に書いた。人の手は手の窓（題 🙋⏳ 手: <何を>・1 つの頼みに 1 つの窓）"
            "で頼み、あなたがやることには手の窓の URL だけを書く（細目 §4）")
HAND_REMIND = "[session-watch] 前の返事の" + HAND_ASK + "。"


def in_hand_window(log):
    """この窓が手の窓（題 `🙋⏳ 手: <何を>`）か。手の窓は手順を自分の返事に書く。"""
    last = None
    for k, v in log.events:
        if k == "title":
            last = v
    _, mark, name = split_title(last)
    return mark == WAITING and bool(HAND_TITLE.match(name))


def last_reply(log):
    """最後に締めた返事（最後の道具より後ろの本文）。新しい頼みが記録に載った後でも、その前の返事を返す。"""
    out, prev = [], []
    for kind, val in log.events:
        if kind == "owner":
            if out:
                prev = out
            out = []
        elif kind in ("tool", "title", "ask", "meta"):
            out = []
        elif kind == "text":
            out.append(val)
    return "\n".join(out or prev)


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
    out = [t for t in (remind_title(log, data), remind_hand(log)) if t]
    return "\n".join(out) if out else None


def remind_title(log, data):
    if titled(log):
        return None
    kind = kind_of(log.first_prompt or str(data.get("prompt") or ""))
    if kind == AI:
        return REMIND_CHILD   # 親が create_session で付けた題は会話ログに無い＝返事の差し戻しで照らせないので、付け直させる
    which = ("%s（最初の頼みの返し先から）" % kind) if kind else (
        "オーナーと話す窓なら %s・別の窓へ返す窓なら %s" % (HUMAN, AI))
    return REMIND % (HUMAN, AI, REMOTE_PREFIX.rstrip("_"), which)


def remind_hand(log):
    """前の返事のあなたがやることに人の手の手順を直に書いていれば知らせる（手の窓自身は除く）。"""
    if in_hand_window(log) or not owner_steps(last_reply(log)):
        return None
    return HAND_REMIND


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


# ── 差し戻す（Stop の hook・止まるのは AI だけ）────────────────
STOP_CODES = ("title", "card", "close", "plain", "inner", "time", "done", "secret", "neighbor")
NOTE_CODES = ("idk", "unanswered", "rest", "hand")
#   STOP_CODES は差し戻す札（核 §1・§2・§4・§5・§6・§7 の、AI が読み飛ばすとそのまま人に届く所・止めるのは AI の締めだけ）。
#   NOTE_CODES は手で回す点検と知らせるだけ。check() が出す札はどちらか 1 つに必ず載る（載らない札は試験が赤＝黙って
#   止める物にも知らせる物にもならない）。STOP_CODES を変える PR は変更の記録の断片に「止める物:」の行が要る（scripts/pr_shape.py）。neighbor（隣の正本が見つからない）は窓ごとに 1 回だけ差し戻す（AI には直せない＝回さない）。
STOP_MAX = 2                              # 同じターンで差し戻す回数の上限（越えたら通して届ける＝窓が回り続けない）
STOP_OFF = "AF_SESSION_WATCH_STOP"        # 0／false で差し戻しを切る（見張りが壊れた時の逃げ道・人の手でだけ設定する）
STOP_HEAD = ("[session-watch] 返事の形が崩れているので、まだ届けていない。下を直して、返事を頭から全部書き直す"
             "（道具を打ったら、その後に書いた本文が届く返事になる）。形の正本は核 §4・§5（細目 §5）・skill "
             "`session-watch:title-mark`。")
STOP_HOW = {
    "plain": "選ぶ問いは選択肢の画面で聞く（「分からない」も置く・推奨の印は作り方の分かれ道だけ）。意味・考え・前提を問う開いた問いは"
             "「AI の今の読み」を添えて書く。調べれば決まる事は AI が決めて進める（細目 §4）。",
    "inner": "番号・窓の id・`直し_0020` の形の名・commit の印は、それが何かを日常の言葉で言い換える（例: 「#616」→「昨日出した"
             "置き場の直し」と URL）。コード・path・file 名は数えていない（どうしても要る字は `…` で囲む）。",
    "time": "時刻は「YYYY-MM-DD HH:MM 日本時間」で書く（UTC の時刻は 9 時間足す）。記録をそのまま見せる時はコードの囲みに入れる（核 §6）。",
    "done": "確かめた事だけを言い切る。確かめ切れていない所があれば 1 行目を細目 §7 の表の「返事の 1 行目」（一部・止めた・続けられない）の形にし、何が残るかを書く。"
            "人の言葉を引くだけなら「」で囲む。",
    "secret": "鍵・トークンの値を返事から消し、在り処（環境の値の名・設定の場所）だけを書く。出てしまった鍵は人に作り直しを頼む（核 §1）。",
    "neighbor": "上の行が名指す原因を直す: 値の表の読めない形なら、その形を直す PR を出すか、あなたがやることに書く。隣の正本が"
                "見つからないなら、土台の plugin guard と市場の写し（公開の検査）を入れ直す（docs/核の届け方.md）。読めない形は捨てて"
                "照らし続けているので、他の札は効いている。この知らせは窓ごとに 1 回だけ。",
}
STOP_FOOT = ("誤って差し戻した時（引いた言葉・記録の写しに当たった等）: 当たる行の形を値の表 config/skill-values.json の "
             "session-watch.watch-log.reply_exempt（行に当てる正規表現の並び）に、中の言葉の字は guard.ask_term_allow に足す（PR とレビューを"
             "通す）。見張りが壊れた時だけ環境変数 %s=0 で切る。" % STOP_OFF)


def stop_tmp(env):
    import tempfile
    return env.get("AF_SESSION_WATCH_TMP") or os.path.join(tempfile.gettempdir(), "af-session-watch")


def _count(env, sid, reset):
    """この窓の今のターンで差し戻した回数を 1 つ進めて返す（stop_hook_active が偽＝新しい締めなら 0 から）。"""
    d = stop_tmp(env)
    name = "".join(c for c in str(sid or "nosid") if c.isalnum() or c in "-_")[:120] or "nosid"
    path = os.path.join(d, name + ".stop")
    n = 0
    if not reset:
        try:
            with open(path, encoding="utf-8") as f:
                n = int(f.read().strip() or 0)
        except (OSError, ValueError):
            n = 0
    n += 1
    try:
        os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(n))
    except OSError:
        pass
    return n


def stop(data, env=None):
    """差し戻す理由（str）か None。今の返事（last_assistant_message・無ければ会話ログの締め）の形を見る。"""
    env = os.environ if env is None else env
    if str(env.get(STOP_OFF, "")).strip().lower() in ("0", "false", "off", "no"):
        return None
    path = data.get("transcript_path") or ""
    log = Log(read_rows(path)) if path and os.path.exists(path) else Log([])
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() == "true":
        log.cloud = True          # クラウドの窓は題の道具を持つ（会話ログで道具を打つ前でも題を照らす）
    last = data.get("last_assistant_message")
    closing = last if isinstance(last, str) and last.strip() else None
    found = [(c, m) for c, m in check(log, closing, data) if c in STOP_CODES and not m.startswith(ASK_BEFORE)]
    if any(c == "neighbor" for c, _ in found) and _seen(env, data.get("session_id"), "neighbor"):
        found = [(c, m) for c, m in found if c != "neighbor"]
    if not found:
        return None
    if _count(env, data.get("session_id"), reset=not data.get("stop_hook_active")) > STOP_MAX:
        sys.stderr.write("[session-watch] 差し戻しが %d 回を越えたので通す\n" % STOP_MAX)
        return None
    out = [STOP_HEAD] + ["- %s: %s" % (c, m) for c, m in found]
    hows = [c for c in dict.fromkeys(c for c, _ in found) if c in STOP_HOW]
    if hows:
        out.append("直し方:")
        out += ["- [%s] %s" % (c, STOP_HOW[c]) for c in hows]
    out.append(STOP_FOOT)
    out.append(ROOT_CAUSE)
    return "\n".join(out)


def _seen(env, sid, what):
    """この窓で what を既に差し戻したか（初めてなら印を置いて False）。"""
    d = stop_tmp(env)
    name = "".join(c for c in str(sid or "nosid") if c.isalnum() or c in "-_")[:120] or "nosid"
    path = os.path.join(d, "%s.%s" % (name, what))
    if os.path.exists(path):
        return True
    try:
        os.makedirs(d, exist_ok=True)
        open(path, "w").close()
    except OSError:
        pass
    return False


def hook_stop(stdin):
    try:
        data = json.loads(stdin.read() or "{}")
        reason = stop(data if isinstance(data, dict) else {})
    except Exception:          # noqa: BLE001  見張りの故障で窓を止めない
        return 0
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


def main(argv):
    if argv[1:] == ["--remind"]:
        return hook_remind(sys.stdin)
    if argv[1:] == ["--stop"]:
        return hook_stop(sys.stdin)
    # 知らない印・数の違う引数・読めないログは既定で止める（打ち間違いを「拾う物なし＝緑」にしない）
    if len(argv) != 2 or argv[1].startswith("--"):
        sys.stderr.write("使い方: session_watch.py <transcript.jsonl> ／ session_watch.py --remind ／ session_watch.py --stop\n")
        return 2
    try:
        found = watch(argv[1])
    except OSError as e:
        sys.stderr.write("ログを読めない: %s（%s）\n" % (argv[1], e.strerror or e))
        return 2
    for code, msg in found:
        print("%s: %s" % (code, msg))
    if found:
        print(ROOT_CAUSE)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
