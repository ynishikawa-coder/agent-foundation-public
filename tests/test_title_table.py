"""窓の題の印と返事の札は、種類×状態の表（session_watch.py の TITLE_TABLE・オーナーの決定 2026-11-22）に在る物だけが通るか。

なぜ在るか: 前の表は状態が足りず（止まった・ほかの窓の待ち・後継へ渡した の置き場が無い）、題の照らし（split_title・
title_shape）は 1 文字目しか見ずに 2 文字目の知らない印を作業名として素通りさせた。2026-11-21 にオーナーの窓の AI が
🟢 を自作し、子と後継が create_session の title で写して 🟡・⚪・🔨 まで広がった。子の窓への知らせは「同じ題でもよい」
と言い、親の崩れた題がそのまま残った。ここでは、広がった印と畳んだ印（⏳・🙋⏳ 手:・⏳待ち）をわざと入れて、題を付ける口・
窓を立てる口・返事の締めのどれもが拒むことを見る。入力は全部作り物。
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
        assert "| `💤` | ほかの窓・合流待ち |" in why        # 直し方に表の正本を出す


@pytest.mark.parametrize("title", BAD_TITLES)
def test_表に無い印の題のまま締めると見張りが拾う(title):
    rs = set_title(rows("owner_ok.jsonl"), "🙋 作り物の続き", title)
    assert any(c == "title" for c, _ in sw.check(sw.Log(rs))), title


def test_畳んだ待ちの札で始めた返事は札の表に無いと拾う():
    rs = set_last_text(rows("owner_ok.jsonl"), "⏳待ち（作り物の窓・今日中）\n作り物を待つ。\n"
                       "AI がこの後やること: なし\nあなたがやること: なし。この窓で AI が続けるので、まだ閉じないでください。")
    found = [m for c, m in sw.check(sw.Log(rs)) if c == "card"]
    assert found and "💤待ち" in found[0] and "⏳ の札は畳んだ" in found[0]
    ok = set_last_text(rs, rs[-1]["message"]["content"][0]["text"].replace("⏳待ち", "💤待ち"))
    assert not [c for c, _ in sw.check(sw.Log(ok)) if c == "card"]


def test_skill_の表は正本の表の写しと同じ():
    from pathlib import Path
    skill = Path(sw.__file__).resolve().parent.parent / "skills" / "title-mark" / "SKILL.md"
    assert sw.table_doc() in skill.read_text(encoding="utf-8")


# ── 決まりの文（核・細目）は表と同じ印を書く（文を消す・古い印へ戻すと赤）──
def _core(name):
    from pathlib import Path
    return (Path(sw.__file__).resolve().parents[2] / "core" / name).read_text(encoding="utf-8")


def test_核の札は題の状態と同じ絵の_4_つ():
    line = "- 1 行目は 4 札のどれか: %s（題の状態と同じ絵）。" % "／".join("`%s%s`" % (c, sw.CARD_WORDS[c]) for c in sw.CARDS)
    assert line in _core("核.md")


@pytest.mark.parametrize("sentence", [
    "- **窓の題** — 形は `<種類><状態> <作業名>`。",
    "状態は `❓`＝オーナーの答え待ち／`💤`＝ほかの窓・合流待ち／`🛑`＝止まった／`✅`＝終わった・後継へ渡した／無し＝動いている。",
    "種類ごとに付けてよい状態の表は skill `session-watch:title-mark` で、表に無い印と組み合わせは題を付ける口で止まる。",
    "役は作業名に書く。",
    "後継へ移る時は前の窓の最後の返事に後継の URL を書き、題を `✅` にする。",
    "- **4 札の中身** — `💤待ち` は誰を・いつまで、`🛑止まった` は理由・外せる人を書く。",
])
def test_細目の窓の題と札の文は表と同じ印(sentence):
    assert sentence in _core("細目.md")


def test_決まりの文に畳んだ印が残らない():
    for name in ("核.md", "細目.md"):
        text = _core(name)
        assert "⏳" not in text and "🙋⏳" not in text and "手: <何を>" not in text, name
