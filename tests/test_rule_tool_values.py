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


# 道具が照らす種類 → その種類が守る決まりの文（文の中の一続きの字で指す・指す文はちょうど 1 つ）。
# 種類の一覧は道具から読む（session_watch の拾う物・ask_shape の HOW・guard の見張り）。道具に種類を足して文を指さないと赤、
# 指した文を消すと赤＝道具が照らす文は試験で守られ、守らない文の表（判断の訳）に載らない（tests/test_rule_holes_table_reasons.py）。
照らしの種類 = {
    "session_watch.title": ["形は `<種類><状態> <作業名>`", "（役）は作業名に書く", "🙋 の窓とオーナーが立てた窓は自動で閉じない"],
    "session_watch.close": ["最後の 2 行は", "オーナーが最後だけ読んで"],
    "session_watch.card": ["1 行目は 4 札のどれか"],
    "session_watch.plain": ["選ぶ問いを平文で出さない", "選ぶ問いと開いた問い"],
    "session_watch.idk": ["「分からない」の選択肢"],
    "session_watch.unanswered": ["1 時間答えの無い問い"],
    "session_watch.rest": ["AI がこの後やることは締める前に", "AI がこの後やること＝自分が次に打つ手だけ"],
    "session_watch.hand": ["頼んだ窓は締めの「あなたがやること」に手の窓の URL", "①目的（1 行）②手順"],
    "session_watch.inner": ["決まりの中だけの言葉・AI 同士の呼び名・番号は出さない", "番号には中身を 1 行そえる"],
    "session_watch.time": ["「13:43 UTC」と書かない"],
    "session_watch.done": ["全部申告でなく記録", "「たぶん」「概ね」"],
    "session_watch.secret": ["2. 秘密を出さない"],
    "session_watch.neighbor": ["照らす材料が欠けた日は"],
    "ask_shape.long": ["②画面の問いは何を決めるかの 1 文", "背景を問いの文に詰めない"],
    "ask_shape.inner": ["決まりの言葉（段取りの名"],
    "ask_shape.topic": ["1 画面は 1 つの話題"],
    "ask_shape.rec": ["`(推奨)` は作り方の分かれ道"],
    "guard.ask_shape": ["は guard の `ask_shape` が出す前に照らす"],
    "guard.irreversible": ["1. 戻せない操作の前に人に聞く"],
    "guard.outbound": ["2. 秘密を出さない", "形は `<種類><状態> <作業名>`", "①目的（1 行）②手順"],
    "guard.paid_upstream": ["試験から有料の上流"],
    "guard.pick_one": ["並べて 1 つ選ばせる問いを出さない", "原因から 1 つを選ばせる問いを出さない"],
    "guard.pr_text": ["PR の題と本文が全部世界に見える", "秘密・個人の情報・顧客の語をどれにも書かない"],
    "guard.prior_ask": ["問いを出す前に、各社の決定の記録と問いの表", "引いた結果（照らした前の答え"],
    "guard.qa_page": ["**確認 HTML**"],
    "guard.spec_gate": ["出す道具は証明の無い物"],
    "guard.values_keys": ["知らない値・欠けた材料・仕組みで表せない決まりは"],
    "guard.context_size": ["重くなったら区切りの良い所で後継の窓へ移る", "後継へ移る時は前の窓の最後の返事に後継の URL", "後継の第一声は"],
    "guard.unanswered": ["1 時間答えの無い問い", "問いが 5 つ以上なら 4 問ずつ"],
}


def 道具の種類():
    """道具が照らす種類の一覧（道具から読む）。"""
    doc = SW.__doc__.split("窓の種類＝")[0]
    kinds = {"session_watch." + k for k in re.findall(r"^  (\w+)\s+…", doc, re.M)}
    kinds |= {"ask_shape." + k for k in _load("plugins/guard/scripts/ask_shape.py").HOW}
    guard = _load("plugins/guard/scripts/guard.py")
    kinds |= {"guard." + n for ev in ("pre", "post", "stop", "prompt", "start") for n, _ in guard.watchers(ev)}
    return kinds


def 決まりの文():
    """[(path, 文)]（文の切り方は tests/test_rule_holes.py の 文の並び と同じ）。"""
    out = []
    for rel in ("plugins/core/核.md", "plugins/core/振る舞い.md", "plugins/core/細目.md"):
        for ln in (ROOT / rel).read_text(encoding="utf-8").splitlines():
            out += [(rel, s.strip()) for s in re.findall(r"[^。]*。|[^。]+$", ln) if s.strip()]
    return out


def 照らされる文():
    """{(path, 文): [種類]}。指す字が文にちょうど 1 つ当たらなければ赤。"""
    sents, out = 決まりの文(), {}
    for kind, frags in 照らしの種類.items():
        for frag in frags:
            hit = [x for x in sents if frag in x[1]]
            assert len(hit) == 1, f"{kind} の指す文（{frag}）が {len(hit)} 文に当たる（ちょうど 1 文を指す）"
            out.setdefault(hit[0], []).append(kind)
    return out


def test_道具が照らす種類は全部_決まりの文を指す():
    tools = 道具の種類()
    assert tools - set(照らしの種類) == set(), "決まりの文を指していない照らしの種類（道具が照らす決まりの文を 照らしの種類 に足す）"
    assert set(照らしの種類) - tools == set(), "道具に無い照らしの種類（畳んだ種類は 照らしの種類 から消す）"
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
    ("test_道具が照らす種類は全部_決まりの文を指す", "_細目", "選ぶ問いを平文で出さない。", ""),
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
