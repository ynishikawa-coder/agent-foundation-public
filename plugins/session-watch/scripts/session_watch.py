#!/usr/bin/env python3
"""会話ログ（transcript の JSONL）だけを読む点検（手で回す点検と、返事の形の崩れを見つけて次の頼みの時に知らせる Stop の hook）。

拾う物（どれも会話ログの中だけで決まる＝外の台帳・get_session の返りを見ない。値の表で外す形だけ読む）:
  title    … 窓の題の目印（`<種類><状態> <作業名>`）が決まりどおりか（題だけで決まる形は title_shape。
             guard の outbound が題を付ける口・窓を立てる口でもこれを直に呼ぶ＝題の形の正本）
  close    … 返事の最後が締めの 2 行（`AI がこの後やること: …`／`あなたがやること: …`）か
  card     … 返事の 1 行目が 4 札（✅終わった・❓答えて・💤待ち・🛑止まった＝CARD_WORDS・絵と語の組）のどれかで始まるか
             （close と card は、一言で済む返事＝札も締めも無く SHORT_LINES 行以下・このターンに問いを出していない返事を見ない・細目 §5）
  plain    … 答えを求める問いを、選択肢モーダル（AskUserQuestion）でなく平文で書き、AI の今の読みも添えていないか
             （開いた問い＝意味・考え・前提はチャットで聞いてよい。その時は「AI の今の読み」を添える・細目 §4）
  idk      … 選択肢モーダルの問いに「分からない」の選択肢が無いか
  unanswered … モーダルで出した問いに、答えが返らないまま残っている物があるか
  rest     … 締めの `AI がこの後やること` が「なし」でないのに、この窓で残りを動かす手（子窓・送る・見張り・後で起こす・背で走る助手）を一度も打っていないか
  hand     … 手の窓（題 `✋ <何を>`）の返事に、目的・手順・済んだ目印・済んだ後が揃っているか。
             手の窓でない窓が、あなたがやることに人の手の手順を直に書き、手の窓の URL を書いていないか
  inner    … 人への返事の本文（コードの囲み・`…`・URL を外した所）に、AI の中の言葉らしい字（番号・窓の id・
             `直し_0020` の形の識別子・commit の印）が在るか。見分けの正本は plugin guard の ask_shape.inner_terms
             （選択肢の画面と同じ物を直に呼ぶ）。返し先が別の窓の窓（🤖）は人への文でないので見ない
  time     … 返事の時刻が日本時間でない（Z・UTC・GMT・+09:00 以外の時差）か、日付つきの時刻に日本時間の印が無いか（核 §6）
  done     … 1 行目が ✅ の返事に、終わったと言い切らない語（ほぼ・大体・たぶん・はず 等）が終わりの語と同じ文に在るか（核 §7）
  secret   … 返事に鍵・トークンの形が在るか。形の正本は公開の検査 public-guard/guard.py の secret_labels（直に呼ぶ）
  neighbor … 上の inner・secret の正本（隣の plugin guard・公開の検査）が見つからず照らせないか
  unread   … 会話ログに読めない行（JSON として読めない・dict でない）が在るか（黙って飛ばして判定しない）
  nolog    … hook の口で会話ログの path か file が無いか（空の会話ログとして黙って照らさない。最初の頼みの hook は
             file がまだ無いことがあるので path だけを見る）
  broken   … 照らしそのものが例外で壊れたか（hook の口。手で回す口は exit 2 で止まる）

会話の番（ターン）は人が打った行（guard_common.starts_turn＝人の頼みで、別の窓・仕組みの知らせでも要約の行でもない行）
だけで切る。知らせの行は番を切らない（返事の本文の区切りにはなる）。番の切り方はこの 1 つの口だけ。

窓の種類＝「オーナーが相手の窓か」。誰が立てたかだけでは決めない（立てた記録は返し先の写しを数えるかの照らしにだけ使う）。
決め方の正本は window_kind 1 つ（決まりの文 KIND_RULE を skill title-mark がそのまま載せ、細目 §4 は skill を指す。試験が照らす）:
  手の窓（種類 ✋ の窓）は返し先によらず ✋ ／ それ以外は最初の頼みの文に書かれた返し先で
  `返し先=オーナー` → 🙋 ／ `返し先=session_…` → 🤖 ／ `（親窓 session_… の子）` → 🤖 ／ 書いていない → 決めない。
  別の窓を指す返し先は手で書いた写しなので、頼みの行の記録（origin.kind が人でない・promptSource が system＝
  別の窓や仕組みから来た頼み）と合う時だけ数える。行がまだ無い最初の知らせでは記録を読めないので決めず、サーバの記録
  （get_session の parent_session_id）を AI に読ませる。窓の環境の CLAUDE_CODE_CHILD_SESSION は Claude Code が hook・Bash の
  子プロセス全部に付ける印（公式の文書 env-vars）＝どの窓でも 1 なので見分けに使わない。
  記録の読み方と人の印の表の正本は隣の plugin guard の guard_common.seeded_by_record（写さない）。オーナーが引き継ぎの文を貼った窓は 🤖 にしない。

使い方:
  python3 session_watch.py <transcript.jsonl>  … 拾った物を 1 行ずつ出す（拾えば exit 1）
  python3 session_watch.py --remind            … UserPromptSubmit の hook。前の返事の形の知らせ（--stop が置いた物）を
                                                 隣に出す。クラウドの窓で、まだ題に種類（🙋／🤖）を付けていなければ、付けるよう
                                                 AI に知らせる。前の返事のあなたがやることに人の手の手順を直に書いていれば、
                                                 手の窓で頼むよう知らせる（どれも止めない）
  python3 session_watch.py --stop              … Stop の hook。届いた返事の STOP_CODES の札（題の印〔今の題で直せる物・会話ログに
                                                 題が無い時も〕・1 行目の札・締めの 2 行・平文の問い・中の言葉・時刻・完了の言い切り・
                                                 秘密）の崩れを、次の頼みの時に知らせる物として置くだけ（差し戻さない・書き直させない・
                                                 exit 0 で何も出さない＝返事はそのまま届く）
読めない行は黙って飛ばさず unread で名指す。照らしが壊れたら手で回す口は exit 2、hook の口は窓を止めずに broken で知らせる。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "lib"))
import af_place  # noqa: E402  土台の在り処探しの 1 本の口（土台の skill-values/ への symlink）


# ── 隣の正本（写さず直に呼ぶ）──────────────────────────────────
#  中の言葉・「分からない」の見分け … plugin guard の scripts/ask_shape.py（inner_terms・is_dunno）・値の表は scripts/guard_common.py
#  秘密の形 … 公開の検査 public-guard/guard.py（secret_labels。plugin の外＝市場の写しから読む）
#  探す順: 環境変数 → 土台の在り処探しの 1 本の口 lib/af_place.py（同じ repo の隣・入れた plugin の同じ版・市場の写しの同じ版）
#  版の合う物が無ければ None（check は neighbor の札を出す＝黙って照らしを抜かない）。手近な別の版（mtime の新しい版・
#  版の違う市場の写し）は拾わない（入った版と違う決まりで返事を照らさない）。
NEIGHBORS = {
    "ask_shape": ("AF_ASK_SHAPE", "plugins/guard/scripts/ask_shape.py", "guard", "scripts/ask_shape.py"),
    "guard_common": ("AF_GUARD_COMMON", "plugins/guard/scripts/guard_common.py", "guard", "scripts/guard_common.py"),
    "public_guard": ("AF_PUBLIC_GUARD", "public-guard/guard.py", None, None),
}
_loaded = {}


def neighbor_path(name, env=None):
    """隣の正本の path か None。環境変数の後は土台の在り処探しの 1 本の口（lib/af_place.py）だけで探す
    （入った版と同じ版だけ・市場の写しが先へ進んでいれば入った版の中身を歴史から取り出す）。"""
    env = os.environ if env is None else env
    env_name, repo_rel, plugin, rel = NEIGHBORS[name]
    got = env.get(env_name) or ""
    if got and os.path.isfile(got):
        return got
    if plugin:
        got = af_place.sibling_plugin_file(plugin, rel, PLUGIN_ROOT)
    else:
        got = af_place.foundation_file(repo_rel, PLUGIN_ROOT)
    return got or None


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
from root_cause import root_cause  # noqa: E402  根治の 1 文の 1 本の口＝skill-values/root_cause.py の root_cause（lib/ の symlink）
ROOT_CAUSE = root_cause("オーナーが返事を読んで迷わない", cause="拾われた形が出た", shortcut="拾われた所を出し直す")

# ── 題の印の表（正本はここ 1 か所・オーナーの決定 2026-11-22）──────────────────
#  題は `<種類><状態> <作業名>`。種類は 1 文字目、状態は 2 文字目（無し＝AI が動いている）。表に無い印・表に無い組み合わせは
#  title_shape が拒む（guard の outbound が題を付ける口・窓を立てる口で、Stop の見張りが返事の締めで、同じ物を直に呼ぶ）。
#  skill title-mark の表は TITLE_TABLE_DOC をそのまま載せ、細目 §4 は skill を指す（試験が一致を照らす）。
HUMAN = "🙋"    # オーナーと話す窓
HAND = "✋"     # 手の窓（オーナーの操作を頼む窓）
AI = "🤖"       # AI が立てて AI に返す窓
KINDS = (HUMAN, HAND, AI)
MOVING = ""     # 状態の印なし: AI が動いている（✋ はオーナーの操作待ち）
ASKING = "❓"    # オーナーの答え待ち
WAITING = "💤"   # ほかの何か（ほかの窓の返事・本流への取り込み・CI）待ち
STOPPED = "🛑"   # 止まった（外し方は本文）
DONE = "✅"      # 終わった・後継へ渡した（🙋✅ は AI の手は終わり・閉じるかはオーナー）
STATES = (ASKING, WAITING, STOPPED, DONE)
# 種類ごとに付けてよい状態（表に無い組み合わせは拒む）。
TITLE_TABLE = {
    HUMAN: (MOVING, ASKING, WAITING, STOPPED, DONE),
    AI: (MOVING, ASKING, WAITING, STOPPED, DONE),
    HAND: (MOVING, DONE),
}
KIND_NAMES = {HUMAN: "オーナーと話す窓", HAND: "手の窓（オーナーの操作を頼む窓）", AI: "AI が立てて AI に返す窓"}
STATE_NAMES = {MOVING: "（無し）", ASKING: "オーナーの答え待ち", WAITING: "ほかの何か（ほかの窓の返事・本流への取り込み・CI）待ち",
               STOPPED: "止まった（外し方は本文）", DONE: "終わった（核 §7）・後継へ渡した"}
# 返事の 1 行目の札（核 §5 の 4 つ）。札と題の状態は同じ絵（オーナーの決定 2026-11-22 23:00 日本時間・前の砂時計の札は畳んだ＝古い形 card-wait-hourglass）。
CARD_WAIT = WAITING
OLD_CARD_WAIT = "⏳"
# 待ちの意味の文（核 §5 と skill title-mark に同じ文で載せる。写しの一致は試験が照らす）。
WAIT_MEANING = ('`💤` はオーナーの答えでなく、ほかの窓・CI などを待ち、来たら AI が自分で続ける。')
CARD_WORDS = {DONE: "終わった", ASKING: "答えて", CARD_WAIT: "待ち", STOPPED: "止まった"}
CARDS = tuple(CARD_WORDS)
VS16 = "\ufe0f"  # 絵の字の後に付きうる見た目の切り替えの字（印の一部として読む）


def table_doc():
    """skill title-mark に載せる表の文（正本は TITLE_TABLE。写しの一致は試験が照らす）。"""
    rows = ["| 状態 | 意味 | 付けてよい種類 |", "|---|---|---|"]
    for s in (MOVING,) + STATES:
        kinds = "・".join("`%s`" % k for k in KINDS if s in TITLE_TABLE[k])
        mark = "無し" if s == MOVING else "`%s`" % s
        mean = "AI が動いている（`%s` はオーナーの操作待ち）" % HAND if s == MOVING else STATE_NAMES[s]
        rows.append("| %s | %s | %s |" % (mark, mean, kinds))
    return "\n".join(rows)


# 最初の頼みの文に書く返し先（型はここ 1 か所）。
RETURN_TO = re.compile(r"返し先\s*[=＝:：]\s*(オーナー|session_[A-Za-z0-9]+)")
CHILD_OF = re.compile(r"（親窓\s*session_[A-Za-z0-9]+\s*の子）")

# 締めの 2 行の型（ここ 1 か所）。前後の ` と ** は許す。
CLOSE_AI = re.compile(r"^[`*]*AI がこの後やること: ?\S")
CLOSE_OWNER = re.compile(r"^[`*]*あなたがやること: ?\S")
# あなたがやることが「なし」（人の手の手順・平文の問いの見分けで使う）。
OWNER_NONE = re.compile(r"^[`*]*あなたがやること: ?なし")

# 平文の問いの型: 末尾が ？／❓ 札で始まる／最後 2 行に問いの言い回し（条件つきの頼みは除く）。
QEND = re.compile(r"[？?]\s*[)）」』*_`]*\s*$")
STRONG = re.compile(
    r"(よいですか|よろしいですか|いいですか|いいでしょうか|どうしますか|どうしましょう|しますか[？?]|ますか[？?]"
    r"|決めてください|選んでください|返してください|返事をください|OK／NG|OK/NG|ご判断|どちらに|どちらが"
    r"|どちらで|教えてください(?!.*(なら|たら)))")
COND = re.compile(r"(なら|たら|れば|場合)[^。]*(教えて|声をかけて|言って)")
# 開いた問いをチャットで聞く時に添える AI の読み（細目 §4）。これが在る平文の問いは拾わない。
READING = re.compile(r"AI の(今の)?読み")
# 札は絵と語の組（CARD_WORDS）だけ。絵の 1 文字目だけを見ると `❓🟢 進行中`・`🛑止めた`・`✅一部終わった` が通る。
# 札の後は行の終わり・空白・句読点・括弧の注（`✅終わった（一部）` など）だけを受ける。
CARD_LINE = re.compile(r"^[#>*\s]*(%s)(?=$|[\s。、:：（(])" % "|".join(re.escape(c) + r" ?" + re.escape(w) for c, w in CARD_WORDS.items()))
DONE_LINE = re.compile(r"^[#>*\s]*✅(?!\s*終わった\s*[（(]\s*一部)")   # 終わった（「✅終わった（一部）」は除く・核 §7）
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

# 手の窓（題 `✋ <何を>`）が書く 4 つ。作業名の頭の `手:` は、種類 ✋ の前の古い形（title_shape が拒む）。
HAND_TITLE = re.compile(r"^手[:：]")
HAND_PARTS = ("目的", "手順", "済んだ目印", "済んだ後")
# 頼んだ窓のあなたがやること: 手の窓の URL だけを書く（細目 §4）。手順を直に書いたかを型で見る。
HAND_URL = re.compile(r"claude\.ai/code/session_[A-Za-z0-9]+")
STEP_NUM = re.compile(r"(?:^|\s)(?:[1-9][.)．）](?!\d)\s*\S|[①-⑨])", re.M)
STEP_VERB = re.compile(r"(開[くいけ]|貼[るっり]|足[すし]|押[すし]|入れ|入力|追加|クリック|コピー|選[ぶん]|設定[しす]|保存|ログイン)")
STEP_ARROW = re.compile(r"[→＞>]")
ANSWER = re.compile(r"(答え|問い|選択肢)")


# ── 記録を読む ──────────────────────────────────────────────
UNREADABLE = "_af_unreadable"   # 読めない行の印（行の位置に置く＝黙って捨てない。Log が数えて unread で名指す）


def read_rows(path):
    """会話ログの行の並び。読めない行（JSON として読めない・dict でない）は {UNREADABLE: 行の番号} の印として同じ位置に残す。"""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                row = None
            rows.append(row if isinstance(row, dict) else {UNREADABLE: n})
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


def seeded_by_record(row):
    """子の窓の見分けの記録（頼みの行の origin）。正本は隣の plugin guard の
    guard_common.seeded_by_record（人の印の表もそこ 1 か所＝写さない）。隣が無い時は False（文だけで子の窓と決めない。
    返事の見張りが neighbor の札で名指す）。"""
    G = neighbor("guard_common")
    return bool(G.seeded_by_record(row)) if G is not None and hasattr(G, "seeded_by_record") else False


def is_owner_text(row):
    """頼みの文の行か（道具の返り・見張りの差し戻し〔isMeta〕を除く）。人が打った行も、別の窓・仕組みの知らせの行も含む。"""
    if row.get("type") != "user" or row.get("isMeta") or "toolUseResult" in row:
        return False
    return bool(text_of(row).strip())


GUARD_NEEDS = ("starts_turn", "seeded_by_record", "values", "table")   # この見張りが隣の guard_common から直に呼ぶ物


def guard_gap():
    """隣の guard_common の欠け（無い・版がずれて要る物が無い）を名指す文か None。札はこの 1 か所で立てる
    （締めの文が空の番でも・どの照らしの中でも同じく名指す＝欠けたまま古い切り方で黙って照らさない）。"""
    G = neighbor("guard_common")
    if G is None:
        return ("値の表と番の切り方の正本（plugin guard の guard_common）が見つからず、値の表を読めないまま・"
                "頼みの文の行を全部番の切れ目とみなして照らした（別の窓・仕組みの知らせが番を切り、答えの無い問いを見落とす）")
    lack = [n for n in GUARD_NEEDS if not hasattr(G, n)]
    if lack:
        return ("plugin guard の guard_common の版がずれて %s が無く、その所を古い形で照らした"
                "（starts_turn が無ければ頼みの文の行を全部番の切れ目とみなす）。plugin guard を session-watch と同じ版に入れ直す"
                % "・".join(lack))
    return None


def starts_turn(row):
    """番（ターン）を切る行か。正本は隣の plugin guard の guard_common.starts_turn（写さない）。隣が無い・版がずれて無い時は
    頼みの文の行を全部番の切れ目とみなす（guard_gap が check の中で neighbor の札で必ず名指す）。"""
    G = neighbor("guard_common")
    if G is not None and hasattr(G, "starts_turn"):
        return bool(G.starts_turn(row))
    return is_owner_text(row) and not row.get("isCompactSummary")


def blocks(row):
    """assistant 行の中身を出た順に [("text", str) | ("tool", (name, input, tool_use の id))] で返す。"""
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
            out.append(("tool", (b.get("name") or "", inp if isinstance(inp, dict) else {}, str(b.get("id") or ""))))
    return out


def _msg_id(row):
    """assistant 行の message の id（1 つの返事の塊が何行にも分かれて載る時の目印）。無ければ None。"""
    msg = row.get("message")
    got = msg.get("id") if isinstance(msg, dict) else None
    return got if isinstance(got, str) and got else None


def _rejected_ids(row):
    """道具の返りの行で、誤り（is_error＝人が画面を閉じた・断った）として返った tool_use の id の並び。"""
    if row.get("type") != "user":
        return []
    c = _content(row)
    return [str(b.get("tool_use_id")) for b in c if isinstance(c, list) and isinstance(b, dict)
            and b.get("type") == "tool_result" and b.get("is_error") and b.get("tool_use_id")] if isinstance(c, list) else []


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
        self.events = []        # 出た順: ("title", str) / ("ask", [問い]) / ("answer", {問い: 答え}) / ("owner", str) /
        #                         ("notice", str)＝番を切らない知らせ / ("rejected", [問い])＝閉じられた選択肢の画面
        self.first_prompt = ""
        self.first_seeded = False   # 最初の頼みの行の記録が、人でなく別の窓・仕組みから来た頼みを示すか
        self.cloud = False
        self.unreadable = []        # 読めない行の番号（read_rows の印）
        asks = {}                   # 選択肢の画面の tool_use の id → 問い（閉じられた画面を見分ける）
        msg_ask = {}                # assistant の message の id → その message の最初の問いの位置（同じ message の題を前へ）
        turn_start = 0
        began = False               # 窓の最初の頼みを読んだか（最初の頼みは誰が打っても番の始まり）
        for row in rows:
            if UNREADABLE in row:
                self.unreadable.append(row[UNREADABLE])
                continue
            if row.get("type") == "user" and row.get("isMeta") and "toolUseResult" not in row:
                self.events.append(("meta", ""))     # 見張りの差し戻し: ターンは続くが、締めの本文はここから数え直す
                continue
            if is_owner_text(row):
                if not self.first_prompt and not row.get("isCompactSummary"):
                    self.first_prompt = text_of(row)
                    self.first_seeded = seeded_by_record(row)
                if starts_turn(row) or not began:
                    began = True
                    self.events.append(("owner", text_of(row)))   # 番の始まり（人が打った行・窓の最初の頼み）
                    turn_start = len(self.events)
                else:
                    self.events.append(("notice", text_of(row)))  # 知らせ: 番を切らず、返事の本文だけ数え直す
                continue
            tur = row.get("toolUseResult")
            if isinstance(tur, dict) and "questions" in tur:
                ans = tur.get("answers") if isinstance(tur.get("answers"), dict) else {}
                if ans:   # 空の答え（人が見たかも分からない）は答えに数えない＝問いは残る
                    self.events.append(("answer", {_norm(k): v for k, v in ans.items()}))
                continue
            closed = [asks[i] for i in _rejected_ids(row) if i in asks]
            if closed:
                self.events.append(("rejected", [q for qs in closed for q in qs]))
                continue
            if row.get("type") != "assistant":
                continue
            mid = _msg_id(row)
            for kind, val in blocks(row):
                if kind == "text":
                    self.events.append(("text", val))
                    continue
                name, inp, tid = val
                if name.startswith(REMOTE_PREFIX):
                    self.cloud = True
                if name.endswith(SET_TITLE_SUFFIX):
                    ev = ("title", str(inp.get("title") or ""))
                    at = msg_ask.get(mid) if mid else None
                    if at is not None:
                        # 同じ message の中で問いと並べて付けた題は、問いと同時に出る＝問いの前に置く
                        self.events.insert(at, ev)
                        for k2 in msg_ask:
                            if msg_ask[k2] is not None and msg_ask[k2] >= at:
                                msg_ask[k2] += 1
                        turn_start += 1 if turn_start > at else 0
                    else:
                        self.events.append(ev)
                elif name == ASK:
                    qlist = inp.get("questions")
                    items = [q for q in (qlist if isinstance(qlist, list) else []) if isinstance(q, dict)]
                    qs = [q for q in (_norm(q.get("question")) for q in items) if q]
                    if mid and msg_ask.get(mid) is None:
                        msg_ask[mid] = len(self.events)
                    if tid:
                        asks[tid] = qs
                    self.events.append(("ask", qs))
                    idk = [(q, has_idk(q)) for q in items]
                    lack = [_norm(q.get("question")) for q, ok in idk if ok is False]
                    if lack:
                        self.events.append(("noidk", lack))
                    if any(ok is None for _, ok in idk):
                        self.events.append(("noidk_blind", True))
                else:
                    self.events.append(("tool", name))
                    if moves(name, inp):
                        self.events.append(("move", name))
        self.turn = self.events[turn_start:]

    def closing_text(self):
        """このターンの最後の道具より後ろの返事（オーナーが最後に読む締めの本文）。"""
        out = []
        for kind, val in self.turn:
            if kind in ("tool", "title", "ask", "meta", "notice"):
                out = []
            elif kind == "text":
                out.append(val)
        return "\n".join(out)

    def turn_asked(self):
        return any(k == "ask" for k, _ in self.turn)


def has_idk(question):
    """選択肢の中に「分からない」（細目 §4）が在るか。見分けは plugin guard の ask_shape.is_dunno を直に呼ぶ（写さない）。
    正本が見つからない時は None（見分けられない＝在るとも無いとも言わず、neighbor の札で知らせる）。"""
    A = neighbor("ask_shape")
    if A is None or not hasattr(A, "is_dunno"):
        return None
    return any(isinstance(o, dict) and A.is_dunno(o.get("label")) for o in question.get("options") or [])


def _norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


# ── 窓の種類と題 ──────────────────────────────────────────────
# 窓の種類の決まりの文（skill title-mark はこの文をそのまま載せ、細目 §4 は skill を指す＝試験が照らす）。決め方は window_kind。
KIND_RULE = ("種類の決め方は 2 段: まず手の窓（オーナーの操作を頼む窓）は返し先によらず `✋`。"
             "それ以外は窓の最初の頼みの文に書いた返し先だけで決める: `返し先=オーナー` → `🙋`／"
             "`返し先=session_…` か `（親窓 session_… の子）` → `🤖`（別の窓を指す返し先は手で書いた写しなので、頼みの行の記録が人の打った物でない時（行がまだ無い最初の知らせでは get_session の `parent_session_id`＝別の窓が立てた記録が在る時）＝別の窓や仕組みから来た頼みの時だけ数える。オーナーが引き継ぎの文を貼った窓は `🤖` にしない）／どれも無い → 窓が自分で決める（点検は種類の食い違いを拾わない）。")


def kind_of(first_prompt, seeded=False):
    """最初の頼みの文に書かれた返し先で種類を決める。書いていなければ None（決めない）。手の窓は見ない＝window_kind を使う。
    別の窓を指す返し先（写し）は、頼みの行の記録が人の打った物でない時（seeded）だけ数える。"""
    m = RETURN_TO.search(first_prompt or "")
    if m and m.group(1) == "オーナー":
        return HUMAN
    if not seeded:
        return None
    if m or CHILD_OF.search(first_prompt or ""):
        return AI
    return None


def window_kind(first_prompt, title=None, seeded=False):
    """窓の種類の正本（KIND_RULE）。手の窓（題の種類 ✋）は返し先によらず ✋、ほかは最初の頼みの返し先。"""
    if split_title(title)[0] == HAND:
        return HAND
    return kind_of(first_prompt, seeded)


def _parts(title):
    """題を (種類, 状態, 残り〔印の直後から・削らない〕) に分ける。印が無ければ None。"""
    t = str(title or "").strip()
    kind = mark = None
    for k in KINDS:
        if t.startswith(k):
            kind, t = k, t[len(k):].lstrip(VS16)
            break
    if kind is not None:
        for st in STATES:
            if t.startswith(st):
                mark, t = st, t[len(st):].lstrip(VS16)
                break
    return kind, mark, t


def split_title(title):
    """題を (種類, 状態, 作業名) に分ける。印が無ければ None（状態の無しも None）。"""
    kind, mark, rest = _parts(title)
    return kind, mark, rest.strip()


def _is_mark(ch):
    """印の字（絵・記号）か。作業名の字（文字・数字・かっこ等）と分ける。"""
    import unicodedata
    return unicodedata.category(ch) in ("So", "Sk", "Cn") or ch in (VS16, "\u200d")


def title_shape(title):
    """題そのものの形の崩れ [説明]（会話ログを見ずに題だけで決まる物）。題を付ける口・立てる口（guard の outbound）も
    これを直に呼ぶ＝題の形の決まりの正本はここ 1 つ（表は TITLE_TABLE）。表に無い 2 文字目・許されない組み合わせを拒む。"""
    kind, mark, rest = _parts(title)
    name = rest.strip()
    out = []
    states = "・".join(("無し" if x == MOVING else x) for x in (MOVING,) + STATES)
    if kind is None:
        head = str(title or "").strip()[:1]
        out.append("題の頭に種類（%s）が無い%s（題: %s）" % ("／".join(KINDS),
                   "。頭の「%s」は種類の表に無い" % head if head and _is_mark(head) else "", title))
        return out + ([] if name else ["題に作業名が無い（題: %s）" % title])
    if rest and not rest[0].isspace():
        if _is_mark(rest[0]):
            odd = "".join(c for c in rest.split()[0] if _is_mark(c)) or rest[0]
            if mark:
                out.append("状態の印は 1 つだけ（%s の後の「%s」）（題: %s）" % (kind + mark, odd, title))
            else:
                out.append("%s の後の「%s」は状態の表に無い（状態は %s。⏳ は畳んだ＝待ちは 💤、手の窓は種類 %s）（題: %s）"
                           % (kind, odd, states, HAND, title))
        else:
            out.append("印と作業名の間に空白が無い（`<種類><状態> <作業名>`）（題: %s）" % title)
    elif name and _is_mark(name[0]):
        # 空白の後の作業名の頭に印の字＝空白で区切った状態の印（`<種類> <表に無い印> <作業名>` の形）。作業名の字として通さない。
        odd = "".join(c for c in name.split()[0] if _is_mark(c)) or name[0]
        if not mark and odd.rstrip(VS16) in STATES:
            out.append("%s と状態「%s」の間に空白を入れない（`<種類><状態> <作業名>`）（題: %s）" % (kind, odd, title))
        else:
            out.append("作業名の頭の「%s」は状態の表に無い（状態は %s。⏳ は畳んだ＝待ちは 💤、手の窓は種類 %s。印は種類の直後に続けて 1 つだけ）（題: %s）"
                       % (odd, states, HAND, title))
    if not name:
        out.append("題に作業名が無い（題: %s）" % title)
    if (mark or MOVING) not in TITLE_TABLE[kind]:
        ok = "・".join(("無し" if x == MOVING else x) for x in TITLE_TABLE[kind])
        out.append("%s の窓に %s は付けない（%s の状態は %s）（題: %s）" % (kind, mark, kind, ok, title))
    if HAND_TITLE.match(name):
        out.append("作業名の頭の `手:` は古い形。手の窓は種類 %s で `%s <何を>` と書く（題: %s）" % (HAND, HAND, title))
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
CLOCK = re.compile(r"(?<![\d:])(\d{1,2})(?:[:：](\d{2})(?:[:：]\d{2})?(?:\.\d+)?(?![\d])|\s*時\s*(\d{1,2})\s*分)")
#   「17:53」と「17時53分」の 2 つの書き方（字の形が違うだけで同じ時刻）。
ZONE = re.compile(r"^\s*(Z(?![A-Za-z])|UTC|GMT|[+-]\d{2}:?\d{2}(?!\d))")
JST_MARK = re.compile(r"日本時間|JST|\+09:?00")
CLAUSE = re.compile(r"[^、。,，;；！？!?\n]+")   # 句。時刻を持つ句の印はその句の時刻だけに掛かる（別の句の時刻を日本時間と読まない）
DATE_BEFORE = re.compile(r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|(?<![\d/])\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)"
                         r"\s*(?:[（(][月火水木金土日][)）])?\s*T?\s*$")

# 完了の言い切り（核 §7）: ✅ の返事で、終わりの語と同じ文に言い切らない語。
HEDGE = re.compile(r"ほぼ|大体|だいたい|たぶん|多分|おそらく|恐らく|はず(?![しすさせれ])|と思(?:う|い|われ)|かもしれ")
FINISH = re.compile(r"終わ|済ん|済み|完了|直っ|直り|直せ|直した|でき|出来|通っ|通る|通り|緑|動い|動く|効い|効く|揃っ|片付")
AHEAD = re.compile(r"次の|次回|来週|来月|明日|今後|あとで|後で|予定|見込み")   # 先の事の見込みは完了の言い切りでない
PAST = re.compile(r"た\s*$|た[）)」]|ました|でした|済み|完了")   # 過去の言い切り（見込みの語が在っても数える）
SENTENCE = re.compile(r"[^。！？!?\n]+")
#   照らす単位は 2 段: 見込みかどうか（AHEAD・PAST）は句（、で切る）ごとに見て見込みの句だけを外し、
#   言い切らない語と終わりの語の重なりは残りの文で見る。「書き直した、次の版はたぶん来週できる。」の「た、」は
#   見込みの句に掛からず、「直った、と思います。」のように 2 つの語が「、」をまたぐ言い切りは拾う。


def reply_exempt(data=None):
    """値の表の session-watch.watch-log.reply_exempt（行に当てる正規表現の並び）。当たる行は inner・time・done で見ない。
    (通る形の並び, 通らない形の並び)。通らない形（正規表現として読めない）は捨てる＝1 つの誤りで照らしを全部止めない。"""
    G = neighbor("guard_common")
    got = G.table("session-watch", data) if G else {}
    got = got.get("watch-log") if isinstance(got, dict) else None
    pats = got.get("reply_exempt") if isinstance(got, dict) else None
    ok, bad = [], []
    for p in pats or []:
        p = G.SV._row_pattern(p) if G and hasattr(G, "SV") else (p if isinstance(p, str) else None)   # 行は字か {"pattern": 字}（型 patterns）
        if not p:
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
    """日本時間でない時刻・日付つきで印の無い時刻の並び [(字, 訳)]。日本時間の印は時刻と同じ句の中だけを見る。"""
    hits = []
    for ln in body.splitlines():
        clauses = list(CLAUSE.finditer(ln))
        # 時刻を持たない句の印（「〜まで、日本時間で。」）は行の時刻全部に掛かる。時刻を持つ句の印はその句の時刻だけ。
        loose = any(JST_MARK.search(c.group(0)) and not CLOCK.search(c.group(0)) for c in clauses)
        for c in clauses:
            cl = c.group(0)
            for m in CLOCK.finditer(cl):
                hh, mm = m.group(1), m.group(2) or m.group(3)
                if int(hh) > 23 or int(mm) > 59:
                    continue
                after, before = ln[c.start() + m.end():c.start() + m.end() + 24], cl[max(0, m.start() - 24):m.start()]
                z = ZONE.match(after)
                if z and not re.match(r"^\s*\+09:?00", after):
                    hits.append((m.group(0) + z.group(1), "日本時間でない"))
                elif not z and DATE_BEFORE.search(before) and not (loose or JST_MARK.search(cl)):
                    hits.append(((DATE_BEFORE.search(before).group(1) + " " + m.group(0)).strip(), "日本時間の印が無い"))
    return hits


def hedge_hits(body):
    """見込みの句を外した文に、終わりの語と並んで在る言い切らない語の並び（「」の中の言葉＝引いた言葉は数えない）。"""
    out = []
    for sent in SENTENCE.findall(QUOTED.sub(" ", body)):
        kept = "、".join(c for c in CLAUSE.findall(sent) if not (AHEAD.search(c) and not PAST.search(c)))
        if HEDGE.search(kept) and FINISH.search(kept):
            out.append(sent.strip()[:40])
    return out


def ai_window(log):
    """返し先が別の窓の窓（🤖）か。種類の正本 window_kind（手の窓は 🙋）か、決まらなければ最後の題の種類で決める。"""
    last = None
    for k, v in log.events:
        if k == "title":
            last = v
    return (window_kind(log.first_prompt, last, log.first_seeded) or split_title(last)[0]) == AI


def words(log, closing, data=None):
    """返事の本文の言葉の札 [(code, 説明)]: inner・time・done・secret・neighbor。"""
    found = []
    if not closing.strip():
        return found
    # 照らしは札ごとに分けて走らせる: 1 つ（値の表の誤った形・隣の正本の故障）が壊れても、他の札は黙って抜けない。
    #   壊れた札は neighbor で名指す（AI には直せない＝窓ごとに 1 回だけ知らせる）。
    def part(name, fn):
        try:
            fn()
        except Exception as e:      # noqa: BLE001
            found.append(("neighbor", "%s の照らしが壊れて照らせない（%s: %s）" % (name, type(e).__name__, str(e)[:60])))

    # 隣の guard_common の欠けは check の guard_gap が 1 か所で名指す（ここで締めの文の有無に縛らない）
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
        if A is None or not hasattr(A, "inner_terms"):
            found.append(("neighbor", "中の言葉の正本（plugin guard の ask_shape）が見つからず、返事の言葉を照らせない"))
            return
        if G is None:
            return            # 値の表が読めない事は上で名指した（外す形の無いまま照らすと正しい返事を差し戻す）
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


def ask_state(log):
    """(答えの無い問いの並び, 答えが返った問いが在るか)。問いが閉じるのは次の 3 つ:
    選択肢の画面の答えが返った（その画面とそれより前の問いを全部閉じる＝言い直して出し直した問いに答えが返った時も
    元の問いは閉じる）／画面が答えの無いまま閉じられ、その後に人が打った行がある（チャットで答えた）。
    知らせの行（別の窓・仕組み）は答えに数えない。"""
    pending, rejected, closed = [], set(), False
    for k, v in log.events:
        if k == "ask":
            pending.extend(q for q in v if q not in pending)
        elif k == "answer":
            pending, rejected, closed = [], set(), True
        elif k == "rejected":
            rejected |= set(v)
        elif k == "owner" and rejected:
            left = [q for q in pending if q not in rejected]
            closed = closed or len(left) < len(pending)
            pending, rejected = left, set()
    return pending, closed


def check(log, closing=None, data=None):
    """拾った物を [(code, 説明)] で返す。closing を渡せば、それを締めの返事として見る（Stop の hook）。
    data は hook の入力（値の表の在り処＝cwd を読む）。"""
    found = []
    closing = log.closing_text() if closing is None else closing
    _, close = split_close(closing)

    # 題（クラウドの窓＝題の道具を使える窓だけ）
    if log.cloud:
        title = None
        for i, (k, v) in enumerate(log.events):
            if k == "title":
                title = v
            elif k == "ask":
                in_turn = i >= len(log.events) - len(log.turn)
                # 手の窓（✋）は状態に ❓ を持たない（無し＝オーナーの操作待ち。済んだ目印を先に確かめ、確かめられない所だけ選択肢の画面で聞く・細目 §4）
                if in_turn and split_title(title)[1] != ASKING and split_title(title)[0] != HAND:
                    found.append(("title", ASK_BEFORE + " %s にしていない（題: %s）" % (ASKING, title or "（無し）")))
        pending, closed_any = ask_state(log)
        if title is None and closing.strip():
            found.append(("title", NO_TITLE + "（親が窓を立てた時に付けた題は会話ログの外で照らせない）。`get_session` を "
                                   "session_id を省いて読み、今の題を skill `session-watch:title-mark` の表に照らして "
                                   "`set_session_title` で `<種類><状態> <作業名>` に付け直す（表に無い印・表に無い組み合わせは"
                                   "直して付ける。崩れた題は付ける口で止まる）"))
        if title is not None:
            tk, tm, _ = split_title(title)
            kind = window_kind(log.first_prompt, title, log.first_seeded)
            found += [("title", m) for m in title_shape(title)]
            if tk is not None and kind and tk != kind:
                found.append(("title", "題の種類が %s だが、この窓の種類は %s（題: %s・決め方は skill title-mark の種類の決め方）"
                              % (tk, kind, title)))
            if tm == ASKING and not pending and closed_any:
                found.append(("title", "答えが返ったのに題に %s が残っている" % ASKING))
            # ✅ は「終わった」（核 §7）の印。AI の手が尽きた（AI がこの後やること: なし）とは結ばない。
            first = next((ln.strip() for ln in closing.splitlines() if ln.strip()), "")
            kk = kind or tk
            if CARD_LINE.match(first):
                done = bool(DONE_LINE.match(first))
                if done and tm != DONE and kk in (AI, HAND):
                    found.append(("title", "%s の窓が %s終わった で報告するのに、題の状態が %s でない" % (kk, DONE, DONE)))
                elif not done and tm == DONE:
                    found.append(("title", "終わった でない札（止まった・一部・待ち・問い）で締めるのに、題が %s" % DONE))
            # 手の窓（細目 §4）: 済んだ目印を確かめたら頼んだ窓へ返して閉じる。✅ で締めるのに、この窓で頼んだ窓へ
            #   返した跡（send_message）が無ければ、済んだ手の窓が頼んだ窓に済んだと分からないまま残る。
            #   手の窓は 1 つの頼みに 1 つの窓＝返すのは 1 回なので、跡は窓の全部で探す（返した後の頼み・知らせで消さない）。
            hand_done = bool(DONE_LINE.match(first)) and tk == HAND
            if hand_done and not any(k == "move" and str(v).endswith("send_message") for k, v in log.events):
                found.append(("title", "手の窓が %s終わった で締めるのに、頼んだ窓へ済んだ目印を返した跡（send_message）が"
                                       "この窓に無い（返してから締め、自分を閉じる）" % DONE))
            if tk == HAND and tm != DONE and closing.strip() and not hand_done:
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
            # 畳んだ砂時計の待ちの札は今の札（CARD_WAIT）を名指す。
            old = "（待ちの札は %s%s。%s は畳んだ）" % (CARD_WAIT, CARD_WORDS[CARD_WAIT], OLD_CARD_WAIT) \
                if re.match(r"^[#>*\s]*" + OLD_CARD_WAIT, lines[0]) else ""
            found.append(("card", "返事の 1 行目が 4 札（%s）で始まらない%s: %s"
                          % ("／".join(c + CARD_WORDS[c] for c in CARDS), old, lines[0][:40])))
        if close is None:
            found.append(("close", "返事の最後が締めの 2 行（`AI がこの後やること: …`／`あなたがやること: …`）でない: %s"
                          % lines[-1][-60:]))

    # 動かしていない AI がこの後やること（核 §5: 締める前に AI が自分で動かす）
    #   待ちの題（❓ オーナーの答え待ち／💤 ほかの何かの待ち／✋ 手の窓）と、この窓で既に動かした手（子窓・見張り）は拾わない。
    if close and not close.startswith("AI がこの後やること: なし"):
        last_title = None
        for k, v in log.events:
            if k == "title":
                last_title = v
        lk, lm, _ = split_title(last_title)
        waiting = lm in (ASKING, WAITING) or lk == HAND
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
    if any(k == "noidk_blind" for k, _ in log.events):
        found.append(("neighbor", "「分からない」の見分けの正本（plugin guard の ask_shape.is_dunno）が見つからず、選択肢の画面の問いを照らせない"))

    # 答えの無い問い（画面の答えも、閉じた画面の後のチャットの答えも、出し直した問いの答えも返っていない問い）
    for q in ask_state(log)[0]:
        found.append(("unanswered", "答えの無い問いが残っている（出し直す・残りなしで締めない）: %s" % q[:60]))

    # 隣の正本の欠け（番の切り方・値の表）: 締めの文が空の番でも名指す
    gap = guard_gap()
    if gap:
        found.append(("neighbor", gap))

    # 読めない行（黙って飛ばして判定しない）
    if log.unreadable:
        nums = log.unreadable
        found.append(("unread", "会話ログに読めない行が %d 行ある（%s 行目%s）。その行を読まずに照らした＝落ちたのが題・問い・"
                                "答えの行なら判定が違う" % (len(nums), "・".join(map(str, nums[:5])), " ほか" if len(nums) > 5 else "")))
    return found


def watch(path):
    """拾った物の並び。ログが読めなければ OSError、照らしが壊れればその例外をそのまま上げる
    （読めない・壊れた＝拾う物なし＝緑、に化かさない。main が exit 2 で止まる）。"""
    return check(Log(read_rows(path)))


# ── 知らせる（UserPromptSubmit の hook・止めない）──────────────────
def title_forms(table=None):
    """付けてよい題の印の短い文（正本は TITLE_TABLE。REMIND の 3 つはここから作る＝種類×状態を手で写さない）。
    同じ状態の並びを持つ種類は 1 つにまとめる（例: 🙋・🤖 は 無し・❓・💤・🛑・✅／✋ は 無し・✅）。"""
    table = TITLE_TABLE if table is None else table
    groups = {}
    for k in sorted(table, key=lambda k: KINDS.index(k) if k in KINDS else len(KINDS)):
        groups.setdefault(tuple(table[k]), []).append(k)
    return "／".join("%s は %s" % ("・".join(ks), "・".join("無し" if s == MOVING else s for s in sts))
                    for sts, ks in groups.items())


def remind_texts(table=None):
    """題の知らせ 3 つ（人の窓・返し先が別の窓・子の窓）。表の印は title_forms から差す。"""
    forms = title_forms(table)
    table = TITLE_TABLE if table is None else table
    kinds = "／".join(sorted(table, key=lambda k: KINDS.index(k) if k in KINDS else len(KINDS)))
    human = ("[session-watch] この窓の題にまだ種類の印（" + kinds + "）が無い。最初の返事を書く前に、"
             "%s の `set_session_title` で題を `<種類><状態> <作業名>` に付ける（自分の session id は `get_session` を "
             "session_id を省いて読む）。種類: %s。付けてよい印（種類 は 状態）: " + forms
             + "。形の細目は skill `session-watch:title-mark`。")
    parent = ("[session-watch] 最初の頼みの文の返し先が別の窓を指すが、頼みの行の記録をまだ読めない（文は人が貼った写しかもしれない）。"
              "最初の返事の前に `get_session` を session_id を省いて読み、`parent_session_id` が在れば（別の窓が立てた記録）" + AI
              + " の窓として、今の題を表（" + forms + "）に照らして `set_session_title` で付ける（親が付けた題は会話ログに載らず、"
              "返事の見張りが照らせない。親の題を写さない・表に無い印と組み合わせは直して付ける）。`parent_session_id` が無ければ"
              "人が立てた窓なので " + HUMAN + " で題を付ける。形の細目は skill `session-watch:title-mark`。")
    child = ("[session-watch] 親が付けた題は会話ログに載らず、返事の見張り（Stop）が照らせない。最初の返事の前に "
             "`get_session` を session_id を省いて読み、今の題を表（" + forms + "）に照らして `set_session_title` で付ける。"
             "表に無い印・表に無い組み合わせは直して付ける（親の題を写さない。崩れた題は付ける口で止まる）。"
             "形の細目は skill `session-watch:title-mark`。")
    return human, parent, child


REMIND, REMIND_PARENT, REMIND_CHILD = remind_texts()


HAND_ASK = ("あなたがやることに人の手の手順を直に書いた。人の手は手の窓（題 ✋ <何を>・1 つの頼みに 1 つの窓）"
            "で頼み、あなたがやることには手の窓の URL だけを書く（細目 §4）")
HAND_REMIND = "[session-watch] 前の返事の" + HAND_ASK + "。"


def in_hand_window(log):
    """この窓が手の窓（題 `✋ <何を>`）か。手の窓は手順を自分の返事に書く。"""
    last = None
    for k, v in log.events:
        if k == "title":
            last = v
    return split_title(last)[0] == HAND


def last_reply(log):
    """最後に締めた返事（最後の道具より後ろの本文）。新しい頼みが記録に載った後でも、その前の返事を返す。"""
    out, prev = [], []
    for kind, val in log.events:
        if kind in ("owner", "notice"):
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
    """出す文（str）か None。前の返事の形の知らせ（Stop の hook が置いた物・1 回だけ出す）と、クラウドの窓（題の道具を
    持つ窓）でまだ種類の印を付けていない時の知らせ。"""
    env = os.environ if env is None else env
    out = [take_note(env, data.get("session_id"))]
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() == "true":
        log, missing = log_of(data, first_prompt=True)
        out += [missing and nolog_note(env, data.get("session_id"), missing),
                remind_title(log, data), remind_hand(log)]
    out = [t for t in out if t]
    return "\n".join(out) if out else None


def remind_title(log, data):
    if titled(log):
        return None
    if log.first_prompt:
        kind = window_kind(log.first_prompt, None, log.first_seeded)
    else:
        # 頼みの行がまだ無い（最初の頼みを受けた hook）: 記録を読めないので文だけで子の窓と決めない（人の窓の側へ倒す）。
        # 文が別の窓を指す時だけ、サーバの記録（parent_session_id）で決めさせる。窓の環境の印は読まない（どの窓でも 1）。
        prompt = str(data.get("prompt") or "")
        kind = window_kind(prompt, None, False)
        if kind is None and kind_of(prompt, True) == AI:
            return REMIND_PARENT
    if kind == AI:
        return REMIND_CHILD   # 親が create_session で付けた題は会話ログに無い＝返事の見張りで照らせないので、付け直させる
    which = ("%s（最初の頼みの返し先から）" % kind) if kind else (
        "オーナーと話す窓なら %s・オーナーの操作を頼む窓なら %s・別の窓へ返す窓なら %s" % (HUMAN, HAND, AI))
    return REMIND % (REMOTE_PREFIX.rstrip("_"), which)


def remind_hand(log):
    """前の返事のあなたがやることに人の手の手順を直に書いていれば知らせる（手の窓自身は除く）。"""
    if in_hand_window(log) or not owner_steps(last_reply(log)):
        return None
    return HAND_REMIND


BROKEN = ("[session-watch] 見張りの %s が壊れて、この返事の形を照らせなかった（%s）。窓は止めていない。"
          "直し: plugin session-watch の session_watch.py を直す PR を出すか、あなたがやることに書く。この知らせは窓ごとに 1 回だけ。")


def broken_note(env, sid, where, e):
    """照らしの故障の知らせ（窓ごとに 1 回だけ）。故障を黙って「崩れなし」にしない。"""
    if _seen(env, sid, "broken"):
        return None
    return BROKEN % (where, "%s: %s" % (type(e).__name__, str(e)[:80]))


NOLOG = ("会話ログを読めなかった（%s）。題・問い・答え・手の窓の照らしは材料が無いので照らしていない（返事の文の形だけ照らした）。"
         "この知らせは窓ごとに 1 回だけ。")


def log_of(data, first_prompt=False):
    """hook の入力から会話ログを読む。(Log, 読めなかった理由 か None)。材料が無いのを黙って空の会話ログにしない。
    first_prompt: 最初の頼みの hook では会話ログの file がまだ作られていないことがある＝file が無いのは理由にしない
    （path が無いのは理由にする）。Stop の hook では file が無いのも理由にする。"""
    path = data.get("transcript_path")
    if not isinstance(path, str) or not path:
        return Log([]), "hook の入力に transcript_path が無い"
    if not os.path.isfile(path):
        return Log([]), (None if first_prompt else "file が無い: %s" % path[-80:])
    return Log(read_rows(path)), None


def nolog_note(env, sid, why):
    """会話ログを読めなかった知らせ（--remind の口・窓ごとに 1 回だけ・Stop の口と印を分け合う）。"""
    return None if _seen(env, sid, "nolog") else "[session-watch] " + NOLOG % why


def hook_remind(stdin):
    data = {}
    try:
        data = json.loads(stdin.read() or "{}")
        data = data if isinstance(data, dict) else {}
        text = remind(data)
    except Exception as e:     # noqa: BLE001  見張りの故障で窓を止めない（止めずに知らせる）
        try:
            text = broken_note(os.environ, data.get("session_id"), "--remind", e)
        except Exception:      # noqa: BLE001
            return 0
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": text}}, ensure_ascii=False))
    return 0


# ── 知らせる（Stop の hook が置き、次の頼みの時に UserPromptSubmit の hook が出す・差し戻さない）────────────────
STOP_CODES = ("title", "card", "close", "plain", "inner", "time", "done", "secret", "neighbor", "unread", "nolog")
ONCE_CODES = ("neighbor", "unread", "nolog")   # AI には直せない＝窓ごとに 1 回だけ知らせる
#   知らせる札（核 §1・§2・§4・§5・§6・§7 の、AI が読み飛ばすとそのまま人に届く所）。ほか（idk・unanswered・rest・hand）は
#   手で回す点検だけ。neighbor（隣の正本が見つからない）・unread（会話ログに読めない行）は窓ごとに 1 回だけ知らせる（AI には直せない）。
#   返事は差し戻さない（書き直しは同じ返事を 2 度書く無駄になる＝届いた返事はそのまま・次の返事から合わせる）。
NOTE_HEAD = ("[session-watch] 前の返事の形が崩れていた（返事は届いている・書き直さない・差し戻していない）。次の返事から下を合わせる。"
             "形の正本は核 §4・§5（細目 §5）・skill `session-watch:title-mark`。")
STOP_HOW = {
    "plain": "選ぶ問いは選択肢の画面で聞く（「分からない」も置く・推奨の印は作り方の分かれ道だけ）。意味・考え・前提を問う開いた問いは"
             "「AI の今の読み」を添えて書く。調べれば決まる事は AI が決めて進める（細目 §4）。",
    "inner": "番号・窓の id・`直し_0020` の形の名・commit の印は、それが何かを日常の言葉で言い換える（例: 「#616」→「昨日出した"
             "置き場の直し」と URL）。コード・path・file 名は数えていない（どうしても要る字は `…` で囲む）。",
    "time": "時刻は「YYYY-MM-DD HH:MM 日本時間」で書く（UTC の時刻は 9 時間足す）。記録をそのまま見せる時はコードの囲みに入れる（核 §6）。",
    "done": "確かめた事だけを言い切る。確かめ切れていない所があれば 1 行目を `%s%s（一部）` か `%s%s` にし（札は表の 4 つだけ）、"
            "何が残るかを書く（核 §7）。" % (DONE, CARD_WORDS[DONE], STOPPED, CARD_WORDS[STOPPED]) +
            "人の言葉を引くだけなら「」で囲む。",
    "secret": "鍵・トークンの値を以後の返事に出さず、在り処（環境の値の名・設定の場所）だけを書く。出てしまった鍵は人に作り直しを頼む（核 §1）。",
    "nolog": "hook が渡す会話ログの path（transcript_path）か、その file が無い。AI には直せない。続くなら plugin "
             "session-watch の hooks.json と Claude Code の版を確かめる PR を出すか、あなたがやることに書く。",
    "unread": "会話ログの読めない行は AI には直せない。照らしはその行を除いて出したので、題・問い・答えの判定は手で確かめる"
              "（この知らせは窓ごとに 1 回だけ）。続くなら plugin session-watch の読み口を直す PR を出す。",
    "neighbor": "上の行が名指す原因を直す: 値の表の読めない形なら、その形を直す PR を出すか、あなたがやることに書く。隣の正本が"
                "見つからないなら、土台の plugin guard と市場の写し（公開の検査）を入れ直す（docs/核の届け方.md）。読めない形は捨てて"
                "照らし続けているので、他の札は効いている。この知らせは窓ごとに 1 回だけ。",
}
# 誤って当たった時の外し方は、値の表の reply_exempt が外せる札（返事の本文で照らす inner・time・done）にだけ付ける。
STOP_FOOT_CODES = ("inner", "time", "done")
STOP_FOOT = ("誤って当たった時（引いた言葉・記録の写しに当たった等）: 当たる行の形を値の表 config/skill-values.json の "
             "session-watch.watch-log.reply_exempt（行に当てる正規表現の並び）に、中の言葉の字は guard.ask_term_allow に足す（PR とレビューを"
             "通す）。")


def stop_tmp(env):
    import tempfile
    return env.get("AF_SESSION_WATCH_TMP") or os.path.join(tempfile.gettempdir(), "af-session-watch")


def _note_path(env, sid):
    name = "".join(c for c in str(sid or "nosid") if c.isalnum() or c in "-_")[:120] or "nosid"
    return os.path.join(stop_tmp(env), name + ".note")


def put_note(env, sid, text):
    """次の頼みの時に出す知らせを置く（前の知らせは新しい物に替える＝溜めない）。置けなければ黙る。"""
    try:
        os.makedirs(stop_tmp(env), exist_ok=True)
        with open(_note_path(env, sid), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def take_note(env, sid):
    """置いた知らせを 1 回だけ取り出す（取り出したら消す）。無ければ None。"""
    path = _note_path(env, sid)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        os.remove(path)
    except OSError:
        return None
    return text or None


def stop(data, env=None):
    """知らせる文（str）か None。今の返事（last_assistant_message・無ければ会話ログの締め）の形を見る。"""
    env = os.environ if env is None else env
    log, missing = log_of(data)
    if str(env.get("CLAUDE_CODE_REMOTE", "")).lower() == "true":
        log.cloud = True          # クラウドの窓は題の道具を持つ（会話ログで道具を打つ前でも題を照らす）
    last = data.get("last_assistant_message")
    closing = last if isinstance(last, str) and last.strip() else None
    found = [(c, m) for c, m in check(log, closing, data) if c in STOP_CODES and not m.startswith(ASK_BEFORE)]
    if missing:
        found.insert(0, ("nolog", NOLOG % missing))
    for once in ONCE_CODES:
        if any(c == once for c, _ in found) and _seen(env, data.get("session_id"), once):
            found = [(c, m) for c, m in found if c != once]
    if not found:
        return None
    out = [NOTE_HEAD] + ["- %s: %s" % (c, m) for c, m in found]
    hows = [c for c in dict.fromkeys(c for c, _ in found) if c in STOP_HOW]
    if hows:
        out.append("直し方:")
        out += ["- [%s] %s" % (c, STOP_HOW[c]) for c in hows]
    if any(c in STOP_FOOT_CODES for c, _ in found):
        out.append(STOP_FOOT)
    out.append(ROOT_CAUSE)
    return "\n".join(out)


def _seen(env, sid, what):
    """この窓で what を既に知らせたか（初めてなら印を置いて False）。"""
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
    """崩れを次の頼みの時の知らせとして置くだけ。何も出さない（decision=block で差し戻さない＝返事を書き直させない）。"""
    data = {}
    try:
        data = json.loads(stdin.read() or "{}")
        data = data if isinstance(data, dict) else {}
        note = stop(data)
    except Exception as e:     # noqa: BLE001  見張りの故障で窓を止めない（次の頼みの時に知らせる）
        try:
            note = broken_note(os.environ, data.get("session_id"), "--stop", e)
        except Exception:      # noqa: BLE001
            return 0
    if note:
        put_note(os.environ, data.get("session_id"), note)
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
    except Exception as e:     # noqa: BLE001  照らしの故障を「拾う物なし」にしない
        sys.stderr.write("照らしが壊れた: %s（%s: %s）\n" % (argv[1], type(e).__name__, str(e)[:120]))
        return 2
    for code, msg in found:
        print("%s: %s" % (code, msg))
    if found:
        print(ROOT_CAUSE)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
