"""選択肢の画面の問いの決まりの文（核 §4・細目 §4・guard-rules の skill）とコード（guard の ask_shape・session-watch の点検）が、
1 つの正本を読み、互いに食い違わないかを見る。

なぜ在るか（原因の台帳の同じ原因の 1 行・2026-11-19）: ①細目 §4 は画面の問いに前提 1〜2 文を許すが、核 §4 は「1 文に」・
値の表の既定（ask_question_max_sentences）は 1 で、文どおりの問いがコードで止まった ②推奨の印は「形はこの 1 つ」と書くが
コードは 3 形を受けた ③「分からない」の選択肢の見分けが session_watch.py と ask_shape.py で別に在り、「わからない」で
食い違った。
注入の試験: 細目に前提の文の数を戻す・既定を変える・「分からない」の見分けを写しに戻すと赤（guard-rules の一覧と道具の値の縛りは tests/test_doc_tool_values.py）。
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
CORE = PLUGINS / "core" / "核.md"
DETAIL = PLUGINS / "core" / "細目.md"
SCHEMA = ROOT / "skill-values" / "schema.json"
ASK = PLUGINS / "guard" / "scripts" / "ask_shape.py"
SW = PLUGINS / "session-watch" / "scripts" / "session_watch.py"
GUARD_RULES = PLUGINS / "guard" / "skills" / "guard-rules" / "SKILL.md"

sys.dont_write_bytecode = True


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _default(key):
    """schema.json の guard の鍵の既定（形を問わず鍵の名の下の default を探す）。"""
    found = []

    def walk(v):
        if isinstance(v, dict):
            if key in v and isinstance(v[key], dict) and "default" in v[key]:
                found.append(v[key]["default"])
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    walk(json.loads(SCHEMA.read_text(encoding="utf-8")))
    return found


def test_画面の問いの文の数は核と細目と既定が同じ():
    assert "画面の問いは 1 文に" in CORE.read_text(encoding="utf-8")
    sys.path.insert(0, str(PLUGINS / "guard" / "scripts"))
    G = load("guard_common_ask_one_source", PLUGINS / "guard" / "scripts" / "guard_common.py")
    assert G.DEFAULTS.get("ask_question_max_sentences") == 1
    detail = DETAIL.read_text(encoding="utf-8")
    line = [ln for ln in detail.splitlines() if ln.startswith("- **見せてから聞く**")][0]
    assert "画面の問いは何を決めるかの 1 文（前提は ① のチャットへ）" in line
    assert not re.search(r"\d\s*[〜~-]\s*\d\s*文", line), "画面の問いに前提の文の数を足す形（核 §4 と既定に背く）"


def test_推奨の印の形は_ask_shape_が正本で細目は数を言わない():
    detail = DETAIL.read_text(encoding="utf-8")
    assert "形はこの 1 つ" not in detail
    assert "（形は guard の `ask_shape` が正本・推奨しない訳などは説明へ）" in detail
    assert "（印に引かれて答えが寄るため）" in detail


def test_分からないの見分けは_ask_shape_1_つ():
    ask = load("ask_shape_idk_one_source", ASK)
    sw = load("sw_idk_one_source", SW)
    for label in ("分からない", "わからない", "よく分からない", "不明", "Unknown", "I don't know"):
        q = {"question": "作り物？", "options": [{"label": "作り物の案"}, {"label": label}]}
        assert ask.is_dunno(label) and sw.has_idk(q), label
    q = {"question": "作り物？", "options": [{"label": "不明点を先に洗う"}, {"label": "作り物の案"}]}
    assert not ask.is_dunno("不明点を先に洗う") and not sw.has_idk(q)
    assert "IDK in" not in SW.read_text(encoding="utf-8"), "session_watch に「分からない」の見分けの写しが在る"
