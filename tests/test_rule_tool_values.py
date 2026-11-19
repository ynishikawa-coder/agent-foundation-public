"""決まりの文の値と、その決まりを照らす道具の値を突き合わせる（文を消す・値を書き換えると赤）。

なぜ在るか: 核と細目の文の多くは、消しても試験が赤にならなかった（tests/test_rule_holes.py の表）。そのうち道具が照らす決まり
（4 札・窓の題・締めの 2 行・手の窓・完了の 4 状態・問いの形・量の上限・時計）は、文から値を読み、道具の値と同じかを見る。
文の値を変えて道具を変えない（またはその逆）と赤＝決まりと道具がずれたまま合流しない。
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "plugins" / "core"


def _load(rel):
    spec = importlib.util.spec_from_file_location("_rule_tool_" + Path(rel).stem, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SW = _load("plugins/session-watch/scripts/session_watch.py")


def _核():
    return (CORE / "核.md").read_text(encoding="utf-8")


def _細目():
    return (CORE / "細目.md").read_text(encoding="utf-8")


def _当てる(pat, text, what):
    m = re.search(pat, text, re.M)
    assert m, f"決まりの文が無いか形が変わった（{what}）: {pat}"
    return m


def test_返事の_1_行目の_4_札は_session_watch_の札と同じ():
    m = _当てる(r"^- 1 行目は 4 札のどれか: (.+?)。", _核(), "核 §5 の 4 札")
    assert tuple(re.findall(r"`(.)[^`]*`", m.group(1))) == SW.CARDS


def test_窓の題の種類と状態の印は_session_watch_の印と同じ():
    text = _細目()
    m = _当てる(r"種類は返し先（`(.)`＝オーナー／`(.)`＝別の窓か仕組み）。", text, "細目 §5 窓の題の種類")
    assert (m.group(1), m.group(2)) == (SW.HUMAN, SW.AI) and set(SW.KINDS) == {SW.HUMAN, SW.AI}
    m = _当てる(r"状態: (.+?)／無し＝動いている。", text, "細目 §5 窓の題の状態")
    assert tuple(re.findall(r"`(.)`", m.group(1))) == SW.STATES


def test_手の窓の題と_4_つの欄は_session_watch_の型と同じ():
    text = _細目()
    m = _当てる(r"だけ、題 `(.)(.) (手: <何を>)` の窓を立てて頼む。", text, "細目 §4 手の窓の題")
    assert (m.group(1), m.group(2)) == (SW.HUMAN, SW.WAITING) and SW.HAND_TITLE.match(m.group(3))
    m = _当てる(r"そこに ①(\S+?)（1 行）②(\S+) ③(\S+) ④(\S+) を書き、前置きと背景の説明を足さない。", text, "細目 §4 手の窓の 4 欄")
    assert m.groups() == SW.HAND_PARTS


def test_締めの_2_行の形は_session_watch_の型と同じ():
    m = _当てる(r"^- 最後の 2 行は `(.+?)` と `(.+?)`。", _核(), "核 §5 の締めの 2 行")
    assert SW.CLOSE_AI.match(m.group(1) + " x") and SW.CLOSE_OWNER.match(m.group(2) + " x")
    text = _細目()
    m = _当てる(r"^  - `(AI がこの後やること: なし)` ／ `(AI がこの後やること: <何を>（<いつまでに>・<どの窓で>）)`$", text, "細目 §5 締めの AI の行")
    assert SW.CLOSE_AI.match(m.group(1)) and SW.CLOSE_AI.match(m.group(2))
    nones = re.findall(r"^  - `(あなたがやること: なし。(.+?))`$", text, re.M)
    assert len(nones) == 2 and all(SW.OWNER_NONE.match(n) for n, _ in nones), "あなたがやること: なし の 2 つの行"
    assert [[w for w in SW.CLOSE_OK if w in tail] for _, tail in nones] == [[w] for w in SW.CLOSE_OK], \
        "閉じてよいか（閉じて大丈夫／まだ閉じないで）の言い回しが道具の CLOSE_OK とずれた"
    m = _当てる(r"^  - `(あなたがやること: <何を>（問いに答える・手を打つ窓の URL）。(これが済むまで <何> に進めません。))`$", text,
              "細目 §5 締めのあなたがやることの行")
    assert SW.CLOSE_OWNER.match(m.group(1)) and not SW.OWNER_NONE.match(m.group(1)) and SW.BLOCKS in m.group(2)


def test_完了の_4_状態の表は核の_4_状態と同じ():
    m = _当てる(r"終わった／一部／止めた／続けられない のどれかで報告する", _核(), "核 §7 の 4 状態")
    states = m.group(0).split(" ")[0].split("／")
    t = _当てる(r"^\| 状態 \| 意味 \|\n\|---\|---\|\n((?:\| [^|\n]+ \| [^|\n]+ \|\n)+)", _細目(), "細目 §7 の 4 状態の表")
    assert [ln.split("|")[1].strip() for ln in t.group(1).splitlines()] == states


ASK_KINDS = {"題の長さ": "long", "中の言葉": "inner", "話題の混ざり": "topic", "推奨の印の付け方": "rec"}


def test_問いの形の照らしの種類は_ask_shape_の種類と同じ():
    m = _当てる(r"(?:^|。)([^。]+?)は guard の `(\w+)` が出す前に照らす。", _細目(), "細目 §4 問いの形の照らし")
    guard = _load("plugins/guard/scripts/guard.py")
    assert m.group(2) in [n for n, _ in guard.watchers("pre")], "出す前（PreToolUse）に照らしていない"
    mod = _load(f"plugins/guard/scripts/{m.group(2)}.py")
    assert {ASK_KINDS.get(n, n) for n in m.group(1).split("・")} == set(mod.HOW)


LIMIT_NAMES = {"核": "核", "振る舞いの既定": "振る舞い", "各 repo に固有の決まり": "各社固有"}


def test_量の上限の置き場と数の名は_kaku_py_の_LIMITS_と同じ():
    m = _当てる(r"^(.+?)（根の `CLAUDE.md`）に別々の上限があり、`python3 (\S+) check` が照らします（数は `kaku\.py` の `LIMITS` の 1 か所。",
              _細目(), "細目 量の上限")
    kaku = _load(m.group(2))
    assert {LIMIT_NAMES.get(n, n) for n in m.group(1).split("・")} == set(kaku.LIMITS)
    assert 'add_parser("check"' in (ROOT / m.group(2)).read_text(encoding="utf-8")


def test_容器の時計と_cron_の時刻帯は_repo_の設定と同じ():
    text = _細目()
    m = _当てる(r"^- 容器の時計は、各 repo が自分の `(\.claude/settings\.json)` の env に `TZ=(\S+?)` を置いてそろえる。", text, "細目 §6 容器の時計")
    assert json.loads((ROOT / m.group(1)).read_text(encoding="utf-8"))["env"]["TZ"] == m.group(2)
    c = _当てる(r"予約や外の API には `\+09:00`、cron なら頭に `CRON_TZ=(\S+?)` を付け、素の時刻を渡さない。", text, "細目 §6 cron")
    assert c.group(1) == m.group(2) == "Asia/Tokyo"


GUARD_WATCH = [   # (細目の文, その決まりを照らす guard の見張り, 出来事)
    ("- **試験** — 試験から有料の上流（AI の API など）を叩かない。", "paid_upstream", "pre"),
    ("- **文脈が重い時** — 重くなったら区切りの良い所で後継の窓へ移る。", "context_size", "post"),
]


@pytest.mark.parametrize("sentence, watcher, event", GUARD_WATCH)
def test_見張りが照らす決まりの文は在り_見張りがその出来事で回る(sentence, watcher, event):
    assert sentence in _細目(), f"決まりの文が無いか書き換わった: {sentence}"
    guard = _load("plugins/guard/scripts/guard.py")          # 入口が実際にその出来事で回す見張りか（入口の読み方で見る）
    assert watcher in [m for m, _ in guard.watchers(event)]


SKILL_REFS = [   # 手順を skill へ渡す細目の文（文を消すと、どこに手順が在るかが分からなくなる）
    "- **規律と仕組みを足す・直す・畳む** 手順は skill `register-rule`。",
    "- **設計の相談** は skill `design-mode`。",
    "- **確認 HTML** — 選択肢の画面を使えない相手（お客さんなど）に使う（skill `docs-kit:qa-html`）。",
    "仕組み（検査の本体・呼び口・見回り）は土台の `docs/公開の検査.md`、作る手順は skill `dev-flow:public-repo`。",
    "- **前提から聞く** — 問いが頼っている前提が未決なら、そちらを先に聞く（相談の間の論点の表は skill `design-mode`）。",
]


@pytest.mark.parametrize("sentence", SKILL_REFS)
def test_手順を渡す先の_skill_は在る(sentence):
    assert sentence in _細目(), f"決まりの文が無いか書き換わった: {sentence}"
    for ref in re.findall(r"skill `([\w:-]+)`", sentence):
        name = ref.split(":")[-1]
        assert list(ROOT.glob(f"plugins/*/skills/{name}/SKILL.md")), f"渡す先の skill が無い: {ref}"
    for doc in re.findall(r"`(docs/[^`]+)`", sentence):
        assert (ROOT / doc).is_file(), f"渡す先の文書が無い: {doc}"


# 道具が出す照らしの単位 → その照らしが守る決まりの文（文の全体を書く＝文を消す・書き換える・弱めると赤）。
# 単位は道具のコードから読む（session_watch と ask_shape は照らしを出す append の 1 か所ずつ・guard は guard.EVENTS の見張りごと）。
# 道具に照らしを足して文を指さないと赤＝道具が照らす文は試験で守られ、守らない文の表（判断の訳）に載らない
# （tests/test_rule_holes_table_reasons.py）。
照らしの単位 = {
    'session_watch.neighbor:値の表 session-wa': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.neighbor:「分からない」の見分けの正本': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.neighbor:秘密の形の正本（公開の検査 ': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.neighbor:中の言葉の正本（plugin': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.neighbor:値の表の %s に正規表現と': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.neighbor:%s の照らしが壊れて照らせ': ['照らす材料が欠けた日は照らしを飛ばして「確認済」にせず止める。'],
    'session_watch.hand:HAND_ASK': ['頼んだ窓は締めの「あなたがやること」に手の窓の URL と、済むまで何に進めないかを書く。'],
    'session_watch.hand:手の窓の返事に %s が無い': ['そこに ①目的（1 行）②手順 ③済んだ目印 ④済んだ後 を書き、前置きと背景の説明を足さない。'],
    'session_watch.plain:問いを平文で書いた（選ぶ問い': ['選ぶ問いを平文で出さない。', '- **選ぶ問いと開いた問い** — 選ぶ問い（外すとやり直しになる分かれ道・やってよいか・済んだか）は選択肢の画面（AskUserQuestion）で聞く。'],
    'session_watch.secret:返事に秘密の形がある（%s）': ['2. 秘密を出さない — 鍵・トークン・パスワード・接続文字列・認証情報を出力・コード・試験・文書・PR 本文・ログのどこにも書かない。'],
    'session_watch.inner:人への返事に AI の中の言': ['開発・業界の用語は例え話にせず要る所で具体の意味を添え、決まりの中だけの言葉・AI 同士の呼び名・番号は出さない。', '- 番号には中身を 1 行そえる。'],
    'session_watch.time:時刻が日本時間の形でない: ': ['- 「13:43 UTC」と書かない。'],
    'session_watch.title:NO_TITLE': ['- **窓の題** — 形は `<種類><状態> <作業名>`。'],
    'session_watch.title:題の種類が %s だが、この': ['種類は返し先（`🙋`＝オーナー／`🤖`＝別の窓か仕組み）。'],
    'session_watch.title:答えが返ったのに題に %s ': ['状態: `❓`＝オーナーの答え待ち（問いの前に付け、答えが来たら外す）／`⏳`＝オーナーの手待ち／`✅`＝終わった（🤖 だけ）／無し＝動いている。'],
    'session_watch.title:ASK_BEFORE': ['- **問いの持ち方** — 問いは持った窓（子窓も）が題に ❓ を付けて直に出す。'],
    'session_watch.title:%s の窓が %s終わった ': ['状態: `❓`＝オーナーの答え待ち（問いの前に付け、答えが来たら外す）／`⏳`＝オーナーの手待ち／`✅`＝終わった（🤖 だけ）／無し＝動いている。'],
    'session_watch.title:%s の窓が 終わった でな': ['状態: `❓`＝オーナーの答え待ち（問いの前に付け、答えが来たら外す）／`⏳`＝オーナーの手待ち／`✅`＝終わった（🤖 だけ）／無し＝動いている。'],
    'session_watch.card:返事の 1 行目が 4 札（': ['- 1 行目は 4 札のどれか: `✅終わった`／`❓答えて`／`⏳待ち`／`🛑止まった`。'],
    'session_watch.close:返事の最後が締めの 2 行（': ['- 最後の 2 行は `AI がこの後やること:` と `あなたがやること:`。'],
    'session_watch.close:あなたがやることが「なし」な': ['- **締めの 2 行** — オーナーが最後だけ読んで、自分の番か・窓を閉じてよいかが分かる形にする。'],
    'session_watch.close:あなたがやることがあるのに、': ['- **締めの 2 行** — オーナーが最後だけ読んで、自分の番か・窓を閉じてよいかが分かる形にする。'],
    'session_watch.rest:AI がこの後やることを書い': ['- AI がこの後やることは締める前に自分で動かす。', '- AI がこの後やること＝自分が次に打つ手だけ（締める前に子窓・助手・見張り・後で起こす、で動かしておく）。'],
    'session_watch.unanswered:答えの無い問いが残っている（': ['親は子の ❓ を見て、1 時間答えの無い問いを自分の窓に `まだ答えの無い問い: <窓 URL>・<問い 1 行>` で知らせる。'],
    'session_watch.done:✅ の返事に、終わったと言い': ['- 「終わった」と言い切る前に、確かめられる事は全部申告でなく記録（試験・証明）で確かめ、終わった／一部／止めた／続けられない のどれかで報告する。', '- **ぼかさない** — 「たぶん」「概ね」「〜と思われます」と書かず、分からない所は分からないと書く。'],
    'session_watch.idk:選択肢の画面の問いに「分から': ['選択肢は 2〜4 つ、各選択肢の説明に「選ぶとどうなるか」（ほかの選択肢との違い）をはしょらずに書き、どの問いにも「分からない」の選択肢（選ぶと AI が聞き方を変えて聞き直す）を置く。'],
    'ask_shape.long:「%s」— 問いの文が長い:': ['- **見せてから聞く** — ①案・前提・材料をチャットで先に見せる（選択肢の画面が開くと前の文が見えないことがあるので、問いの直前に、それだけで答えが決まる量を出す）→ ②画面の問いは何を決めるかの 1 文（要る前提は 1〜2 文まで）→ ③選択肢ごとの違いは選択肢の説明へ。', '背景を問いの文に詰めない。'],
    'ask_shape.rec:「%s」— 推奨の印の付け方': ['- **推奨の印** — `(推奨)` は作り方の分かれ道の問いだけに付け、1 つ目の選択肢の見出しの末に置き（形はこの 1 つ・推奨しない訳などは説明へ）、理由を説明に書く。'],
    'ask_shape.inner:「%s」— AI の中の言葉': ['決まりの言葉（段取りの名・節の番号・決まりの中で意味が固まった言葉）は問いに出さない。'],
    'ask_shape.topic:1 画面の問いが、語を共にし': ['1 画面は 1 つの話題（別の話題は画面を分けて続けて出す）。'],
    'guard.ask_shape': ['題の長さ・中の言葉・話題の混ざり・推奨の印の付け方は guard の `ask_shape` が出す前に照らす。'],
    'guard.irreversible': ['1. 戻せない操作の前に人に聞く — 強制 push・DB の削除・人の手が入った物や git に無い一点物の削除。'],
    'guard.outbound': ['2. 秘密を出さない — 鍵・トークン・パスワード・接続文字列・認証情報を出力・コード・試験・文書・PR 本文・ログのどこにも書かない。', '- **窓の題** — 形は `<種類><状態> <作業名>`。', 'そこに ①目的（1 行）②手順 ③済んだ目印 ④済んだ後 を書き、前置きと背景の説明を足さない。', '窓が何をする窓か（役）は作業名に書く（決まった一覧は無い・手の窓だけ作業名を `手: <何を>` にする）。', '🙋 の窓とオーナーが立てた窓は自動で閉じない。', '開発・業界の用語は例え話にせず要る所で具体の意味を添え、決まりの中だけの言葉・AI 同士の呼び名・番号は出さない。'],
    'guard.paid_upstream': ['- **試験** — 試験から有料の上流（AI の API など）を叩かない。'],
    'guard.pick_one': ['作業・論点・原因を並べて 1 つ選ばせる問いを出さない。', '- **選ばせない** — 「どれから進めますか」「A と B のどちらを先に」のように、挙がった作業・論点・原因から 1 つを選ばせる問いを出さない。'],
    'guard.pr_text': ['- **公開の repo** — 中身・歴史・commit の名義と説明・PR の題と本文が全部世界に見える。', '秘密・個人の情報・顧客の語をどれにも書かない。'],
    'guard.prior_ask': ['- **聞く前に引く** — 問いを出す前に、各社の決定の記録と問いの表を問いと同じ言葉で引く。', '引いた結果（照らした前の答えの ID か URL・無ければ引いた言葉）は問いごとに持ち、問いを見る別の目にも渡す。'],
    'guard.qa_page': ['- **確認 HTML** — 選択肢の画面を使えない相手（お客さんなど）に使う（skill `docs-kit:qa-html`）。'],
    'guard.spec_gate': ['出す道具は証明の無い物・証明と中身が合わない物を通さない。'],
    'guard.values_keys': ['知らない値・欠けた材料・仕組みで表せない決まりは、既定で止まる（黙って既定の値・近い形・前回の値で進めない）。'],
    'guard.context_size': ['- **文脈が重い時** — 重くなったら区切りの良い所で後継の窓へ移る。', '後継へ移る時は前の窓の最後の返事に後継の URL を書く。', '後継の第一声は ①目的 ②済んだ事 ③残り（並べ方は振る舞いの既定）④読む物 を書く。'],
    'guard.unanswered': ['親は子の ❓ を見て、1 時間答えの無い問いを自分の窓に `まだ答えの無い問い: <窓 URL>・<問い 1 行>` で知らせる。', '問いが 5 つ以上なら 4 問ずつの画面を続けて出す。'],
}


_出す先 = {"plugins/session-watch/scripts/session_watch.py": ("session_watch", "found"),
          "plugins/guard/scripts/ask_shape.py": ("ask_shape", "out")}


def _出す照らし(rel, tool, var):
    """var.append(("<種類>", <文>)) の 1 か所ずつを "<道具>.<種類>:<文の頭>" で返す（文の頭は字の頭 14 字か定数の名）。"""
    import ast
    out = []
    for n in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8"))):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append"
                and isinstance(n.func.value, ast.Name) and n.func.value.id == var and n.args
                and isinstance(n.args[0], ast.Tuple) and isinstance(n.args[0].elts[0], ast.Constant)
                and isinstance(n.args[0].elts[0].value, str)):
            continue
        m = n.args[0].elts[1]
        while isinstance(m, ast.BinOp):
            m = m.left
        if isinstance(m, ast.Call) and isinstance(m.func, ast.Attribute):
            m = m.func.value
        head = m.id if isinstance(m, ast.Name) else m.value[:14] if isinstance(m, ast.Constant) else ast.dump(m)[:20]
        out.append("%s.%s:%s" % (tool, n.args[0].elts[0].value, head))
    return out


def 道具の照らし():
    """道具が出す照らしの単位の一覧（道具のコードから読む・手で書いた一覧を読まない）。"""
    units = [u for rel, (tool, var) in _出す先.items() for u in _出す照らし(rel, tool, var)]
    guard = _load("plugins/guard/scripts/guard.py")
    units += ["guard." + n for ev in guard.EVENTS for n, _ in guard.watchers(ev)]
    return set(units)


def 決まりの文():
    """[(path, 文)]（文の切り方は tests/test_rule_holes.py の 文の並び と同じ）。"""
    out = []
    for rel in ("plugins/core/核.md", "plugins/core/振る舞い.md", "plugins/core/細目.md"):
        for ln in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            out += [(rel, s.strip()) for s in re.findall(r"[^。]*。|[^。]+$", ln) if s.strip()]
    return out


def 照らされる文():
    """{(path, 文): [照らしの単位]}。書いた文が決まりの文にちょうど 1 つ在らなければ赤。"""
    sents, out = 決まりの文(), {}
    for unit, wants in 照らしの単位.items():
        for want in wants:
            hit = [x for x in sents if x[1] == want]
            assert len(hit) == 1, f"{unit} の守る文が {len(hit)} 文に当たる（消した・書き換えた・弱めた）: {want}"
            out.setdefault(hit[0], []).append(unit)
    return out


def test_道具が出す照らしは全部_決まりの文を指す():
    tools = 道具の照らし()
    assert tools - set(照らしの単位) == set(), "決まりの文を指していない照らし（守る決まりの文を 照らしの単位 に足す）"
    assert set(照らしの単位) - tools == set(), "道具に無い照らし（畳んだ照らしは 照らしの単位 から消す）"
    assert 照らされる文()


def test_時刻の文の例は_session_watch_が日本時間でないと拾う():
    m = _当てる(r"^- 「(\d{1,2}:\d{2} (\w+))」と書かない。", _細目(), "細目 §6 書かない時刻")
    assert [z for _, z in SW.time_hits(m.group(1))] == ["日本時間でない"] and SW.ZONE.match(" " + m.group(2))


def test_窓の題の形と手の窓の作業名は_session_watch_の題の形と同じ():
    text = _細目()
    m = _当てる(r"^- \*\*窓の題\*\* — 形は `<種類><状態> <作業名>`。", text, "細目 §4 窓の題の形")
    assert SW.title_shape(SW.AI + SW.WAITING + " 作業") == [] and SW.title_shape(SW.WAITING + SW.AI + " 作業"), \
        "種類→状態→作業名の並びを道具が照らしていない"
    m = _当てる(r"窓が何をする窓か（役）は作業名に書く（決まった一覧は無い・手の窓だけ作業名を `(手: <何を>)` にする）。", text, "細目 §4 役")
    assert SW.HAND_TITLE.match(m.group(1)) and SW.title_shape(SW.HUMAN + SW.WAITING + " " + m.group(1)) == []


@pytest.mark.parametrize("test, rel, old, new", [
    ("test_返事の_1_行目の_4_札は_session_watch_の札と同じ", "_核", "／`🛑止まった`", ""),
    ("test_窓の題の種類と状態の印は_session_watch_の印と同じ", "_細目", "／`✅`＝終わった（🤖 だけ）", ""),
    ("test_手の窓の題と_4_つの欄は_session_watch_の型と同じ", "_細目", "③済んだ目印", "③済んだ印"),
    ("test_時刻の文の例は_session_watch_が日本時間でないと拾う", "_細目", "「13:43 UTC」", "「13:43 日本時間」"),
    ("test_道具が出す照らしは全部_決まりの文を指す", "_細目", "選ぶ問いを平文で出さない。", ""),
    ("test_道具が出す照らしは全部_決まりの文を指す", "_細目", "「確認済」にせず止める。", "「確認済」にしてよい。"),
])
def test_文の値を書き換えると本物の試験が赤(monkeypatch, test, rel, old, new):
    """注入の試験: 決まりの文を書き換えた中身で本物の試験を回すと赤（比べ方を写さず、試験そのものを回す）。"""
    mod = sys.modules[__name__]
    body = getattr(mod, rel)()
    assert old in body, f"書き換える字が無い: {old}"
    bad = body.replace(old, new, 1)
    monkeypatch.setattr(mod, rel, lambda: bad)
    if rel == "_細目":   # 決まりの文() は file を直に読む＝その読みも書き換えた中身にする
        real = Path.read_text
        target = (CORE / "細目.md").resolve()
        monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: bad if self.resolve() == target else real(self, *a, **k))
    with pytest.raises(AssertionError):     # 書き換える前の緑は、同じ試験が別に回って示す
        getattr(mod, test)()
