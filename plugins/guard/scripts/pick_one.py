"""PreToolUse — 選択肢の画面（AskUserQuestion）で、作業・論点・原因を並べて 1 つだけ選ばせる問いを止め、出し直させる。

意図: 相談で出た事は全部やる（オーナー決定 2026-11-19）。原因を見立てる役は AI が持ち、オーナーへ渡さない。
課題: 「どれを進めますか」と 1 つだけ選ばせると、選ばなかった物を捨てる形になる。原因を並べて 1 つ選ばせるのも、
原因を見立てる AI の役をオーナーへ渡す形になる。
原因: 文の決まりは読み飛ばされる（なので問いが出る前に形で止める）。止まるのは AI の問いだけ（画面はまだ人に出ていない）。

止める問い（どれも 1 つだけ選ぶ問い＝multiSelect が偽の時だけ）:
  work   … どれを進めますか・何から始めますか・どの論点を先に詰めますか（これからやる物・手を付ける順を選ばせる意志の形）
  first  … どれを優先しますか（意志の形）
  cause  … 原因はどれだと思いますか・どれが原因に近いですか（原因の見立てをオーナーに選ばせる）
通す問い:
  - 全部を選べる問い（multiSelect が真）
  - 選択肢に「全部」「すべて」「両方」「同時」「並行」など、全部やる道が在る問い（やり方を問う問いになる）
  - 意図・事実・言葉の意味を問う問い: 止める形を意志の形（〜しますか・〜したいか・〜すべきか）と原因の見立ての言い回しに
    絞るので、過去（どの環境から始めましたか）・受け身（どの設定が優先されますか）・意味（どちらの意味ですか）・事実
    （原因はどの資料に書いてありますか）の問いには当たらない。ただし言い回しの推し量りなので、試験に置いた形の外では誤りうる
  - 値の表 guard.ask_pick_one_exempt（問いの文に当てる正規表現の並び）に当たる問い（誤って止まる形を PR とレビューで外す）
見分けは問いの文の語の形による推し量り（意味は読まない）。言い換えれば抜けられる＝残る穴は PR と SKILL に書く。
"""
from __future__ import annotations

import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import skill_values as SV  # noqa: E402  値の表の当て方の 1 本の口（土台の skill-values/ への symlink）

ASK_TOOL = "AskUserQuestion"

# 止めるのは「これから AI がやる物・順を 1 つ選ばせる」意志の問いと、「原因はどれだと思うか」と見立てを選ばせる問いだけ。
# 過去（〜しましたか）・受け身（〜されますか）・「が」を挟む形（どの設定が優先されるか）・意味や事実の問いは当てない。
_WHICH = r"(?:どれ|どちら|どっち|どの[^\s、。？?をがはにでともへのか]{1,12})"   # 「どの…」は助詞を越えて飲み込まない
_ORDER = r"(?:先に|最初に|まず|次に)"
# 動詞は「ます」にも「べき」にも続く形で持つ（サ変は し／す、五段は り／る）。
_DO = (r"(?:進め|進み|やり|やる|着手(?:し|す)|手を付け|手をつけ|取り掛か(?:り|る)|取りかか(?:り|る)"
       r"|片付け|片づけ|始め|詰め|対応(?:し|す))")
_WILL = r"(?:ますか|ましょうか|ましょう|たいですか|たい|るべき|べき)"     # 意志の形（ましたか・されますか は当たらない）
_CAUSE = r"(?:原因|要因|真因|根っこ|根本原因)"      # 「根」1 字は「根拠」に当たるので使わない
_OPINION = r"(?:だと思|と思|と見|に近い|が近い|当たって|有力|怪しい)"   # 原因の見立てをオーナーに選ばせる言い回し
PATTERNS = (
    ("work", re.compile(_WHICH + r"\s*(?:を|から|に)\s*" + _ORDER + r"?\s*" + _DO + r"\s*" + _WILL
                        + r"|" + _ORDER + r"\s*" + _WHICH + r"\s*(?:を|から|に)\s*" + _DO + r"\s*" + _WILL
                        + r"|(?:何|なに)\s*(?:から\s*" + _ORDER + r"?|を\s*" + _ORDER + r")\s*" + _DO + r"\s*" + _WILL)),
    # 「優先度は高いか」「どの設定が優先されますか」は事実の問い。どれ・どちらを優先する（意志の形）だけ。
    ("first", re.compile(_WHICH + r"\s*(?:を|から)?\s*優先(?:し|す)\s*" + _WILL)),
    ("cause", re.compile(r"(?:" + _CAUSE + r"\s*(?:は|として)\s*(?:" + _WHICH + r"|何)"
                         + r"|(?:" + _WHICH + r"|何)\s*が\s*(?:一番|最も|主な|本当の)?\s*の?\s*" + _CAUSE
                         + r"|どの\s*" + _CAUSE + r"\s*が)[^。？?]{0,12}?" + _OPINION)),
)
WHY = {
    "work": "やる物・手を付ける順を 1 つ選ばせている",
    "first": "優先する物を 1 つ選ばせている",
    "cause": "原因を 1 つ選ばせている",
}
# 全部やる道が選択肢に在れば、捨てる問いでなく、やり方を問う問い。
ALL_WAY = re.compile(r"全部|すべて|全て|両方|いずれも|どれも|同時|並行|並べて")

HOW = (
    "直し方（どれか 1 つで出し直す）:\n"
    "1. 相談で出た事は全部やる。順と窓の分け方は AI が決めて進め、問わない（核 §4）。\n"
    "2. 全部を選べる形にする（multiSelect: true、または「全部」の選択肢を置く）。\n"
    "3. 原因なら、AI が原因を見立てて示し（合意した全体の絵があれば絵の上で）、その見立てが合っているかを問う（原因を並べて選ばせない）。\n"
    "4. 調べれば決まる順なら、問わずに AI が決めて全部進める。\n"
    "推奨の印（推奨）は作り方の分かれ道の問いだけに付ける（細目 §4「推奨の印」）。全部やるかを問う選択肢には付けない。\n"
    "誤って止めた時（意図・事実・言葉の意味を問う問いだった）: 問いの文を「どちらが正しいか／どの意味か／どちらにするか」の形に"
    "直して出し直す。同じ形で何度も誤って止まるなら、repo の値の表 guard.ask_pick_one_exempt（問いの文に当てる正規表現）に足す"
    "（PR とレビューを通す）。止め方の細目は skill `guard:guard-rules`。")



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}

def classify(question, vals=None):
    """1 問を見て、止めるなら理由の札（work／first／cause）、通すなら ""。"""
    if not isinstance(question, dict) or question.get("multiSelect"):
        return ""
    text = re.sub(r"\s+", " ", str(question.get("question") or "")).strip()
    if not text:
        return ""
    if SV.hit(SV.patterns_of("guard", None, "ask_pick_one_exempt", vals), text) is not None:
        return ""
    for o in question.get("options") or []:
        if isinstance(o, dict) and ALL_WAY.search(str(o.get("label") or "")):
            return ""
    for code, pat in PATTERNS:
        if pat.search(text):
            return code
    return ""


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") != ASK_TOOL:
        return ""
    ti = data.get("tool_input")
    qs = ti.get("questions") if isinstance(ti, dict) else None
    if not isinstance(qs, list):
        return ""
    hit = []
    for q in qs:
        code = classify(q, vals)
        if code:
            hit.append("- 「%s」— %s" % (str(q.get("question") or "")[:80], WHY[code]))
    if not hit:
        return ""
    return ("[guard] 選択肢の画面で、作業・論点・原因を並べて 1 つだけ選ばせる問いは出さない（相談で出た事は全部やる・"
            "オーナー決定 2026-11-19）。画面はまだ人に出ていない。\n" + "\n".join(hit) + "\n" + HOW)
