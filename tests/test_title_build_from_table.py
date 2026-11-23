"""窓の題を組む道具（title_build.py）は、題の印の表（session_watch.py の TITLE_TABLE）から組み、表に無い形を組まないか。

意図: 窓の題を、止められてから直すのでなく、初めから通る形で付ける。
課題: AI が表を思い出して題を手で組み、表に無い組み合わせ（✋💤）・畳んだ印（⏳）・空白抜けを出して止められ、直す往復が出ていた。
原因: 表を照らす口（title_shape）はあっても、表から正しい題を組んで渡す口が無かった。
ここでは、表に在る組み合わせが全部 title_shape を通る題になること、表に無い印・組み合わせ・作業名の無い形をわざと入れて
組まずに訳を返すこと、表の正本を替えると組める物も替わる（表を写していない）ことを見る。入力は全部作り物。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "session-watch" / "scripts"
TOOL = SCRIPTS / "title_build.py"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("title_build_t", TOOL)
tb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tb)
SW = tb.SW


def test_表に在る組み合わせは全部_照らしを通る題になる():
    for kind, states in SW.TITLE_TABLE.items():
        for s in states:
            title, probs = tb.build(kind, s or "無し", "作り物の作業")
            assert probs == [] and SW.title_shape(title) == [], (kind, s, probs)
            assert title == "%s%s 作り物の作業" % (kind, s)


@pytest.mark.parametrize("kind,state,name", [
    ("✋", "💤", "作り物の設定"),      # 表に無い組み合わせ
    ("✋", "❓", "作り物の設定"),
    ("🤖", "⏳", "作り物の作業"),      # 畳んだ印
    ("🤖", "🟢", "作り物の作業"),      # 広がった自作の印
    ("🔨", "無し", "作り物の作業"),    # 表に無い種類
    ("🤖", "無し", "   "),              # 作業名が無い
    ("🤖", "💤", "手: 作り物の設定"),  # 古い手の窓の形（照らしの正本で拒む）
])
def test_表に無い形は組まず訳を返す(kind, state, name):
    title, probs = tb.build(kind, state, name)
    assert title is None and probs
    p = subprocess.run([sys.executable, str(TOOL), kind, state, name], capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and p.stdout == "" and "題を組めない" in p.stderr


def test_別名と札の言葉からも表の印に引き当てる():
    assert tb.build("ai", "waiting", "作り物")[0] == "%s%s 作り物" % (SW.AI, SW.WAITING)
    assert tb.build("human", "答えて", "作り物")[0] == "%s%s 作り物" % (SW.HUMAN, SW.ASKING)
    assert tb.build("hand", "moving", "作り物")[0] == "%s 作り物" % SW.HAND


def test_表の正本を替えると組める物も替わる_表を写していない(monkeypatch):
    monkeypatch.setitem(SW.TITLE_TABLE, SW.AI, (SW.MOVING, SW.DONE))
    title, probs = tb.build(SW.AI, SW.WAITING, "作り物")
    assert title is None and any("付けてよい状態" in p for p in probs)
    monkeypatch.setitem(SW.TITLE_TABLE, SW.HAND, (SW.MOVING, SW.DONE, SW.WAITING))
    assert tb.build(SW.HAND, SW.WAITING, "作り物")[0] == "%s%s 作り物" % (SW.HAND, SW.WAITING)


def test_表を出す口は正本の表の文と同じ():
    p = subprocess.run([sys.executable, str(TOOL), "--table"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and p.stdout.strip() == SW.table_doc()


def test_細目の窓の題は表から組む道具を名で指し_その道具が在る():
    text = (SCRIPTS.parent.parent / "core" / "細目" / "04-聞き方.md").read_text(encoding="utf-8")
    assert "`scripts/title_build.py <種類> <状態> <作業名>`" in text and TOOL.is_file()
