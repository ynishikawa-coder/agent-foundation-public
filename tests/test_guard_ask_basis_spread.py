"""判断を頼む時の 2 行（具体例・頼む理由）を広げた所の注入の試験（細目 §4「見せてから聞く」「手の窓」「問いの言葉」）。
どれも知らせるだけ（止める物を増やしていない）。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "plugins" / "guard" / "scripts"
SW = ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py"
sys.path.insert(0, str(GUARD))
import ask_shape  # noqa: E402
import outbound  # noqa: E402

sys.path.pop(0)


def _core(tmp_path, heading):
    (tmp_path / "細目").mkdir(parents=True)
    (tmp_path / "振る舞い.md").write_text("- **%s** — 作り物の決まり。\n" % heading, encoding="utf-8")
    (tmp_path / "細目" / "01-作り物.md").write_text("- **意図** — 短い見出しは数えない。\n", encoding="utf-8")
    return str(tmp_path)


def test_決まりの言葉は核の太字の見出しから拾い_見出しを消すと拾わない(tmp_path):
    ask_shape._rule_cache.clear()
    core = _core(tmp_path / "a", "作り物の見回りの段取り")
    hits = ask_shape.rule_terms("作り物の見回りの段取りを先にしますか", {}, core)
    assert (ask_shape.RULE_KIND, "作り物の見回りの段取り") in hits
    assert ask_shape.rule_terms("意図を教えてください", {}, core) == []          # 6 字未満の見出しは数えない
    assert ask_shape.rule_terms("細目 §4 のとおりに聞きますか", {}, core) != []   # 節の番号は数える
    ask_shape._rule_cache.clear()
    gone = _core(tmp_path / "b", "別の作り物の決まりの名")
    assert ask_shape.rule_terms("作り物の見回りの段取りを先にしますか", {}, gone) == []


def test_決まりの言葉は画面の後に知らせるだけで_出す前には止めない(tmp_path, monkeypatch):
    ask_shape._rule_cache.clear()
    monkeypatch.setenv("AF_CORE_DIR", _core(tmp_path, "作り物の見回りの段取り"))
    qs = [{"question": "作り物の見回りの段取りを先にしますか", "header": "順番", "multiSelect": False,
           "options": [{"label": "先にする", "description": "見回りが今日動く"},
                       {"label": "後にする", "description": "見回りが来週動く"},
                       {"label": "分からない", "description": "聞き方を変えて聞き直す"}]}]
    note = ask_shape.notice({"tool_name": "AskUserQuestion", "tool_input": {"questions": qs}}, {})
    assert "作り物の見回りの段取り" in note
    assert not any("作り物の見回りの段取り" in f for f in ask_shape.findings(qs, {}))
    ask_shape._rule_cache.clear()


def _hand(title, prompt):
    return {"tool_name": "mcp__claude-code-remote__create_session", "tool_input": {"title": title, "prompt": prompt}}


PROMPT = "目的: 作り物の設定が動く。\n手順:\n1. 開く\n済んだ目印: 出る\n済んだ後: 返す。\n"


def test_手の窓を立てた頼みに_2_行が無ければ知らせ_揃えば黙る(monkeypatch):
    monkeypatch.setenv("AF_SESSION_WATCH", str(SW))
    note = outbound.hand_basis_note(_hand("✋ 作り物の設定", PROMPT))
    assert note.startswith("[guard] 手の窓を立てた頼みの文に") and "人の手の理由" in note and "止めていない" in note
    full = PROMPT + "具体例: 作り物の画面で保存を押すと作り物が動く。\n**人の手の理由**： 作り物の画面はオーナーの PC にしか無い。\n"
    assert outbound.hand_basis_note(_hand("✋ 作り物の設定", full)) == ""
    assert outbound.hand_basis_note(_hand("🤖 作り物の直し", PROMPT)) == ""     # 手の窓でなければ見ない


def test_手の窓の_2_行の知らせは正本の無い古い版では黙る(monkeypatch, tmp_path):
    fake = tmp_path / "session_watch.py"
    fake.write_text("HAND='✋'\nHAND_PARTS=()\nKINDS=('✋',)\nKIND_NAMES={'✋': '作り物'}\n"
                    "def table_doc(): return ''\n"
                    "def title_shape(t): return []\n"
                    "def split_title(t): return ('✋', None, t)\n", encoding="utf-8")
    monkeypatch.setenv("AF_SESSION_WATCH", str(fake))
    assert outbound.hand_basis_note(_hand("✋ 作り物の設定", PROMPT)) == ""


def test_決まりの文が見張りと同じ_2_行の名を持つ():
    """細目 §4「手の窓」と §3 の「直さない」を聞く文が、見張り（session-watch の HAND_BASIS・ask_basis の 2 行）と同じ名の行を
    求める。片方だけ名を変えると、決まりと見張りが別の行を求める。文を消すか古い形に戻すと赤。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sw_for_rule", SW)
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    saimoku = ROOT / "plugins" / "core" / "細目"
    s4 = (saimoku / "04-聞き方.md").read_text(encoding="utf-8")
    hand = next(line for line in s4.splitlines() if line.startswith("- **手の窓**"))
    assert "行の頭の 2 行" in hand and "2 行が無ければ立てた後に guard の outbound が知らせる" in hand
    for label in sw.HAND_BASIS:
        assert "`%s:`" % label in hand, f"細目 §4「手の窓」に行の名が無い: {label}"
    s3 = (saimoku / "03-直すは根治.md").read_text(encoding="utf-8")
    ask = next(line for line in s3.splitlines() if "「直さない」をオーナーに聞くか" in line)
    assert "聞く時は画面の前にチャットで行の頭の `具体例:`・`判断を頼む理由:` の 2 行を置く" in ask
