"""窓の題の印と返事の札は、種類×状態の表（session_watch.py の TITLE_TABLE・オーナーの決定 2026-11-22）に在る物だけが通るか。

意図: 窓の題の印と返事の札を、オーナーが決めた 1 つの表（種類×状態）にある物だけにし、見て迷わないようにする。
課題: 2026-11-21 にオーナーの窓の AI が 🟢 を自作し、子と後継が create_session の title で写して 🟡・⚪・🔨 まで広がった。
子の窓への知らせは「同じ題でもよい」と言い、親の崩れた題がそのまま残った。
原因: 前の表は状態が足りず（止まった・ほかの窓の待ち・後継へ渡した の置き場が無い）、題の照らし（split_title・
title_shape）は 1 文字目しか見ずに 2 文字目の知らない印を作業名として素通りさせた。
ここでは、広がった印と畳んだ印（題の ⏳・🙋⏳ 手:・砂時計の札 ⏳待ち）をわざと入れて、題を付ける口・
窓を立てる口・返事の締めのどれもが拒むことを見る。
返事の 1 行目の待ちの札は題の状態と同じ絵の 💤待ち（オーナーの決定 2026-11-22 23:00 日本時間・前の ⏳待ち は畳んだ）。入力は全部作り物。
"""
import pytest

from test_guard import deny_reason, env  # noqa: F401  （env は fixture）
from test_session_watch import rows, set_last_text, set_title, sw

SET_TITLE = "mcp__claude-code-remote__set_session_title"
CREATE = "mcp__claude-code-remote__create_session"

# 2026-11-21 に広がった印と、表から畳んだ印（わざと入れる）。
BAD_TITLES = [
    "🙋🟢 作り物の相談",
    "🤖🟡 作り物の作業",
    "🤖⚪ 作り物の作業",
    "🔨 作り物の作業",
    "🟢 作り物の作業",
    "🤖⏳ 作り物の作業",
    "🙋⏳ 手: 作り物の設定",
    "🤖 手: 作り物の設定",
    "✋❓ 作り物の設定",
    "✋💤 作り物の設定",
    "✋🛑 作り物の設定",
    "🤖❓✅ 作り物の作業",
    "🤖作り物の作業",
]


def tool(name, **ti):
    return {"tool_name": name, "session_id": "s1", "cwd": "", "tool_input": ti}


def all_titles():
    """表の全部の組み合わせ（在る物）と、表に無い組み合わせ。"""
    ok, ng = [], []
    for k in sw.KINDS:
        for s in (sw.MOVING,) + sw.STATES:
            (ok if s in sw.TITLE_TABLE[k] else ng).append("%s%s 作り物" % (k, s))
    return ok, ng


def test_表の組み合わせはオーナーの決定どおり():
    assert sw.KINDS == ("🙋", "✋", "🤖")
    assert set(sw.TITLE_TABLE[sw.HUMAN]) == set(sw.TITLE_TABLE[sw.AI]) == {"", "❓", "💤", "🛑", "✅"}
    assert set(sw.TITLE_TABLE[sw.HAND]) == {"", "✅"}
    assert sw.CARDS == ("✅", "❓", "💤", "🛑")
    assert [c + sw.CARD_WORDS[c] for c in sw.CARDS] == ["✅終わった", "❓答えて", "💤待ち", "🛑止まった"]


def test_表に在る組み合わせは全部通り_無い組み合わせは全部拒む():
    ok, ng = all_titles()
    assert len(ok) == 12 and len(ng) == 3
    for t in ok:
        assert sw.title_shape(t) == [], t
    for t in ng:
        assert sw.title_shape(t), t


@pytest.mark.parametrize("title", BAD_TITLES)
def test_表に無い印の題は形の正本が拒む(title):
    assert sw.title_shape(title), title


@pytest.mark.parametrize("title", BAD_TITLES)
def test_表に無い印の題は付ける口でも立てる口でも止まる(env, title):
    for payload in (tool(SET_TITLE, session_id="s", title=title),
                    tool(CREATE, title=title, prompt="目的 手順 済んだ目印 済んだ後")):
        why = deny_reason(env, payload)
        assert "決まりの形でない" in why, (title, payload["tool_name"])
        assert "| `💤` | ほかの何か（ほかの窓の返事・本流への取り込み・CI）待ち |" in why        # 直し方に表の正本を出す


@pytest.mark.parametrize("title", BAD_TITLES)
def test_表に無い印の題のまま締めると見張りが拾う(title):
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", title)
    assert any(c == "title" for c, _ in sw.check(sw.Log(rs))), title


def test_畳んだ砂時計の待ちの札は拾い_今の札を名指す():
    rs = set_last_text(rows("owner_ok.jsonl"), "⏳待ち（作り物の窓・今日中）\n作り物を待つ。\n"
                       "AI がこの後やること: なし\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。")
    found = [m for c, m in sw.check(sw.Log(rs)) if c == "card"]
    assert found and "待ちの札は 💤待ち" in found[0]
    ok = set_last_text(rs, rs[-1]["message"]["content"][0]["text"].replace("⏳待ち", "💤待ち"))
    assert not [c for c, _ in sw.check(sw.Log(ok)) if c == "card"]


# 札の絵だけ合って語が表に無い 1 行目（わざと入れる）。絵の 1 文字目だけを見ていた時は全部通った。
BAD_CARDS = ["❓🟢 進行中", "🛑止めた", "✅一部終わった", "💤", "⏳待ち", "💤待機", "✅完了", "❓質問"]


@pytest.mark.parametrize("card", BAD_CARDS)
def test_札の語が表に無い返事は拾う(card):
    rs = set_last_text(rows("owner_ok.jsonl"), card + "\n作り物の本文。\n"
                       "AI がこの後やること: なし\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。")
    assert [c for c, _ in sw.check(sw.Log(rs)) if c == "card"], card


@pytest.mark.parametrize("card", ["✅終わった", "✅ 終わった", "✅終わった（一部）", "❓答えて", "💤待ち（作り物の窓）", "💤 待ち", "🛑止まった。"])
def test_表の札は通る(card):
    assert sw.CARD_LINE.match(card), card


def test_親が立てた窓への知らせも表に照らさせ_親の題を写させない():
    for text in (sw.REMIND_PARENT, sw.REMIND_CHILD):
        assert "親の題を写さない" in text and "💤" in text
        assert "付け直す" not in text


def test_skill_の表は正本の表の写しと同じ():
    from pathlib import Path
    skill = Path(sw.__file__).resolve().parent.parent / "skills" / "title-mark" / "SKILL.md"
    assert sw.table_doc() in skill.read_text(encoding="utf-8")


# ── 決まりの文（核・細目）は表と同じ印を書く（文を消す・古い印へ戻すと赤）──
def _core(name):
    from pathlib import Path
    core = Path(sw.__file__).resolve().parents[2] / "core"
    if name == "細目":                                     # 細目は節ごとの file
        return "\n".join(p.read_text(encoding="utf-8") for p in sorted((core / "細目").glob("*.md")))
    return (core / name).read_text(encoding="utf-8")


def test_核の札は見張りの_4_札と同じ():
    line = "- 1 行目は 4 札のどれか: %s。" % "／".join("`%s%s`" % (c, sw.CARD_WORDS[c]) for c in sw.CARDS)
    assert line in _core("核.md")


@pytest.mark.parametrize("sentence", [
    "- **窓の題** — 形は `<種類><状態> <作業名>`。",
    "種類（`🙋`・`✋`・`🤖`）と状態の表・決め方は skill `session-watch:title-mark` が正本で、表に無い印と組み合わせは題を付ける口で止まる。",
    "役は作業名に書く。",
    "後継へ移る時は前の窓の最後の返事に後継の URL を書き、題を `✅` にする。",
    "- **4 札の中身** — `💤待ち` は何を・いつまでを書く。",
    "`🛑止まった` には、何に当たったかと、誰が何をすれば続くかを書く。",
])
def test_細目の窓の題と札の文は表と同じ印(sentence):
    assert sentence in _core("細目")


def test_決まりの文に畳んだ印が残らない():
    for name in ("核.md", "細目"):
        text = _core(name)
        assert "🙋⏳" not in text and "`⏳`＝" not in text and "手: <何を>" not in text and "⏳待ち" not in text, name


# ── 使う側に残る砂時計の形を、古い形の照らしが拾う（字の間の空白・手の窓の種類でもすり抜けない）──
@pytest.mark.parametrize("line", ["✋⏳ 作り物の設定", "🙋⏳ 手: 作り物", "🤖️⏳ 作り物"])
def test_古い形の砂時計は空白や手の窓の種類でも拾う(line):
    import json
    import re
    from pathlib import Path
    olds = json.loads((Path(sw.__file__).resolve().parents[2] / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    row = next(r for r in olds if r["id"] == "title-mark-hourglass")
    assert re.search(row["pattern"], line), line


# ── 種類と状態の印の間に空白を入れても、表に無い印や続けて書くべき印を作業名として通さない ──
@pytest.mark.parametrize("title", ["🤖 🟢 作り物", "🤖 ⏳ 作り物", "🙋 ⏳ 手: 作り物", "🙋 🟡 作り物", "🤖 ✅ 作り物", "✋ ❓ 作り物"])
def test_空白で区切った状態の印を拒む(title):
    assert sw.title_shape(title), title


@pytest.mark.parametrize("title", ["🤖✅ 作り物", "🙋 作り物", "✋ 作り物を開く", "🤖 「作り物」の直し", "🤖 2 本目"])
def test_作業名の頭が文字なら通す(title):
    assert sw.title_shape(title) == [], title


@pytest.mark.parametrize("line", ["🤖 ⏳ 作り物", "🙋 ⏳ 手: 作り物", "✋ ⏳ 作り物"])
def test_古い形の砂時計は種類との間の空白でも拾う(line):
    import json
    import re
    from pathlib import Path
    olds = json.loads((Path(sw.__file__).resolve().parents[2] / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    row = next(r for r in olds if r["id"] == "title-mark-hourglass")
    assert re.search(row["pattern"], line), line


def _old(id_):
    import json
    from pathlib import Path
    olds = json.loads((Path(sw.__file__).resolve().parents[2] / "core" / "古い形.json").read_text(encoding="utf-8"))["olds"]
    return next(r for r in olds if r["id"] == id_)


@pytest.mark.parametrize("line", ["⏳待ち（作り物の窓）", "⏳ 待ち", "1 行目は 4 札のどれか: `⏳待ち`"])
def test_古い形の砂時計の待ちの札は札の行が拾い_題の行は拾わない(line):
    import re
    assert re.search(_old("card-wait-hourglass")["pattern"], line), line
    assert not re.search(_old("title-mark-hourglass")["pattern"], line), line


@pytest.mark.parametrize("line", ["💤待ち（作り物の窓）", "🤖💤 作り物", "待ちの札は 💤待ち"])
def test_古い形の札の行は今の札を拾わない(line):
    import re
    assert not re.search(_old("card-wait-hourglass")["pattern"], line), line


def test_待ちの意味は核と_title_mark_で同じ文():
    from pathlib import Path
    skill = Path(sw.__file__).resolve().parent.parent / "skills" / "title-mark" / "SKILL.md"
    assert sw.WAIT_MEANING in _core("核.md")
    assert sw.WAIT_MEANING in skill.read_text(encoding="utf-8")
    for other in ("オーナーの答えでなく", "AI が自分で続ける"):
        assert other in sw.WAIT_MEANING
    assert "オーナーの答え待ちは `❓`、止まって誰かが手を打たないと動かないのは `🛑`" in skill.read_text(encoding="utf-8")
