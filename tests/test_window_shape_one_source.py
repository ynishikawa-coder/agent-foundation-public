"""窓の id の形・返し先・窓の種類・⏳ の意味・窓を閉じる決まりが、1 つの正本（window-shape/window_shape.py）から読まれるかを見る。

なぜ在るか（原因の台帳の同じ原因の 4 行・2026-11-19）: これらが session-watch・guard・checker の file と決まりの文ごとに
別々に書かれ、①guard は返し先の正規表現の写しで手の窓を子の窓（止まる側）と見た ②窓の id の形が file ごとに違い、
`session_watch` を窓の id と見る所と見ない所が在った ③⏳ の意味が 4 か所でずれた ④閉じる・閉じないの逆の決まりが同じ窓に当たった。
注入の試験: 写しを戻す（plugin の .py に窓の id や返し先の正規表現を書く・lib を写しに替える）・決まりの文を正本と違えると赤。
入力は全部作り物。
"""
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "window-shape" / "window_shape.py"
PLUGINS = ROOT / "plugins"
DETAIL = PLUGINS / "core" / "細目.md"
TITLE_MARK = PLUGINS / "session-watch" / "skills" / "title-mark" / "SKILL.md"
SW = PLUGINS / "session-watch" / "scripts" / "session_watch.py"

sys.dont_write_bytecode = True


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W = load("window_shape_one_source", SOURCE)
REAL = "session_01AbCdEfGhIjKlMnOpQrStUv"   # 作り物（本物の id と同じ形）


# ── 正本は 1 つ: lib は symlink・plugin の .py は窓の形を自分で書かない ──
@pytest.mark.parametrize("plugin", ["session-watch", "guard", "checker"])
def test_plugin_の窓の形の読み口は正本への_symlink(plugin):
    p = PLUGINS / plugin / "lib" / "window_shape.py"
    assert p.is_symlink(), f"{p.relative_to(ROOT)} が写し（正本 window-shape/window_shape.py への symlink にする）"
    assert p.resolve() == SOURCE.resolve()


COPY = re.compile(r"session_0?\[A-Za-z0-9\]|返し先\\s|親窓\\s")


def test_plugin_の_py_は窓の_id_と返し先の形を写さない():
    bad = []
    for p in PLUGINS.rglob("*.py"):
        if "lib" in p.relative_to(PLUGINS).parts or not p.is_file():
            continue
        for no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if COPY.search(line):
                bad.append(f"{p.relative_to(ROOT)}:{no}")
    assert bad == [], f"窓の id・返し先の形の写し（window_shape の SESSION_ID_PAT・RETURN_TO・CHILD_OF を使う）: {bad}"


def test_写しの見分けは写しを拾う():
    """注入: 上の見分けが、写しの典型（以前の guard_common・verdict_form の行）を拾うか。"""
    assert COPY.search(r'RETURN_TO_WINDOW = re.compile(r"返し先\s*[=＝:：]\s*session_[A-Za-z0-9]+")')
    assert COPY.search(r'LINE1 = re.compile(r"^レビューした窓: (session_[A-Za-z0-9]+) 判定")')
    assert COPY.search(r'SESSION_ID = re.compile(r"session_0[A-Za-z0-9]{15,}")')


# ── 窓の id の形 ──
def test_窓の_id_の形は名と取り違えない():
    assert W.SESSION_ID.fullmatch(REAL)
    for name in ("session_watch", "session_id", "session_title", "session_X"):
        assert not W.SESSION_ID.fullmatch(name), name


def test_中の言葉の見分けは窓の_id_の正本を使う():
    sys.path.insert(0, str(PLUGINS / "guard" / "scripts"))
    ask = load("ask_shape_one_source", PLUGINS / "guard" / "scripts" / "ask_shape.py")
    found = [t for n, t in ask.inner_terms("作り物 %s と session_watch の話" % REAL, {}) if n == "窓の id"]
    assert found == [REAL]


# ── 窓の種類: guard も同じ正本（手の窓は返し先が窓でも 🙋＝人のいる窓）──
def write_log(tmp_path, first, title=None, origin="task-notification"):
    """作り物の会話ログ。頼みの行の記録（origin.kind）は既定で別の窓から来た頼み。None なら記録なし。"""
    rows = [{"type": "user", "message": {"role": "user", "content": first}}]
    if origin:
        rows[0]["origin"] = {"kind": origin}
    if title:
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "mcp__claude-code-remote__set_session_title",
             "input": {"title": title}}]}})
    p = tmp_path / "log.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return str(p)


@pytest.fixture()
def G():
    sys.path.insert(0, str(PLUGINS / "guard" / "scripts"))
    return load("guard_common_one_source", PLUGINS / "guard" / "scripts" / "guard_common.py")


def test_guard_は手の窓を子の窓と見ない(G, tmp_path):
    first = "作り物の設定を頼む（返し先=%s）。目的・手順・済んだ目印・済んだ後" % REAL
    assert G.is_child_window(write_log(tmp_path, first, "🙋⏳ 手: 作り物の設定")) is False
    assert G.is_child_window(write_log(tmp_path, first)) is True       # 手の窓でなければ今までどおり子の窓
    assert G.is_child_window(write_log(tmp_path, "作り物（親窓 %s の子）" % REAL)) is True
    assert G.is_child_window(write_log(tmp_path, "作り物（返し先=オーナー）")) is False
    # 返し先の文は写し: 頼みの行の記録が人・記録なしなら子の窓にしない（オーナーが引き継ぎの文を貼った窓）
    for origin in ("human", None):
        assert G.is_child_window(write_log(tmp_path, "作り物（親窓 %s の子）" % REAL, origin=origin)) is False


def test_session_watch_と_guard_は同じ種類を返す(G, tmp_path):
    sw = load("sw_one_source", SW)
    for first, title in [("（親窓 %s の子）" % REAL, "🙋⏳ 手: 作り物"), ("（親窓 %s の子）" % REAL, None),
                         ("返し先=オーナー", None), ("頼み", None)]:
        for origin, seeded in (("task-notification", True), ("human", False)):
            got = G.window_kind_of_log(write_log(tmp_path, first, title, origin))
            assert got == sw.window_kind(first, title, seeded), (first, title, origin)
    assert sw.window_kind.__module__ == "window_shape"   # 写しでなく正本を読む
    assert sw.seeded_by_record is G.W.seeded_by_record or sw.seeded_by_record.__module__ == "window_shape"
    assert not hasattr(G, "seeded_by_record") and not hasattr(G, "HUMAN_ORIGINS")   # 記録の見分けも写さない


# ── ⏳ の意味と閉じる決まり: 決まりの文は正本の文をそのまま載せ、ほかの所で言い直さない ──
def test_title_mark_は待ちの印の意味を正本の文で書く():
    text = TITLE_MARK.read_text(encoding="utf-8")
    assert "- " + W.STATE_RULE in text
    assert "| `⏳` | 人の手か別の窓の返しを待って止まる時。" in text


def test_細目は状態の印を_skill_に任せ待ちの印を言い直さない():
    text = DETAIL.read_text(encoding="utf-8")
    assert "状態の印（`❓`・`⏳`・`✅`）の付け方も同じ skill。" in text
    assert "オーナーの手待ち" not in text and "`⏳`＝" not in text


def test_細目の閉じる窓は正本の文():
    assert "- **閉じる窓** — " + W.CLOSE_RULE in DETAIL.read_text(encoding="utf-8")


def test_閉じる決まりを逆に言い直す文が無い():
    """注入: 「🙋 の窓は自動で閉じない」「手の窓は自分を閉じる」「閉じるかはオーナーが決める」を正本の外へ戻すと赤。"""
    detail = DETAIL.read_text(encoding="utf-8").replace(W.CLOSE_RULE, "")
    for old in ("自動で閉じない", "自分を閉じる"):
        assert old not in detail, old
    assert "閉じるかはオーナーが決める" not in SW.read_text(encoding="utf-8")
    assert "済んだ目印を確かめて頼んだ窓へ返す。" in detail


def test_人の窓に終わりの印の差し戻しは閉じる決まりを指す():
    sw = load("sw_one_source_done", SW)
    msg = " ".join(sw.title_shape("🙋✅ 作り物"))
    assert "細目 §5「閉じる窓」" in msg


# ── 頼みの行の記録の見分けと commit の書き手の行の形も正本 1 か所（#93 が各所に 1 つずつ写して足した物を畳んだ）──
COPY_SHAPES = (r"HUMAN_ORIGINS\s*=\s*\(", r"def seeded_by_record\(", r"Claude-Session:\\s")


def copies_outside_source(files):
    import re
    found = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for pat in COPY_SHAPES:
            if re.search(pat, text):
                found.append("%s: %s" % (f.name, pat))
    return found


def source_files():
    root = PLUGINS.parent
    files = [p for p in PLUGINS.glob("*/scripts/*.py")] + [p for p in (root / "scripts").glob("*.py")]
    return [p for p in files if not p.is_symlink()]


def test_記録の見分けと書き手の行の形は正本の外に無い():
    assert copies_outside_source(source_files()) == []


def test_注入_記録の見分けを写すと赤(tmp_path):
    for leak in ('HUMAN_ORIGINS = ("human",)\n', "def seeded_by_record(row):\n    return False\n",
                 'X = re.compile(r"^Claude-Session:\\s*(\\S+)")\n'):
        f = tmp_path / "leak.py"
        f.write_text(leak, encoding="utf-8")
        assert copies_outside_source([f]), leak
