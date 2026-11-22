"""上限の試験は、上限の数を手で写さず、正本（guard の scripts と scripts/plugin_smoke.py の名の付いた定数）を直に読む約束。

注入（作り物でわざと入れる誤り）は 2 つ:
- 正本の上限の値を別の数に変えた写しで、上限の試験がそのまま緑＝作り物が「境目のすぐ上（と下）」で作られ続ける
  （数を写した試験は、値を変えると境目より下の作り物で回り、切りの誤りを見ないまま緑になっていた）。
- その写しにさらに切りの誤り（上限で切らない・上限で落とす）を入れると、同じ試験が赤になる。
"""
import importlib.util
import re
import shutil
from pathlib import Path

import pytest

import test_guard as tg
from test_guard import env  # noqa: F401  （試験ごとの一時の箱の fixture を同じ物で使う）
import test_setup_script_line_limit as tl

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node が無い（qa-html の検査は node で動く）")

# (正本の module, 定数, 変えた値, 上限の試験, 切りの誤り＝(元の字, 入れる字))
GUARD_CASES = [
    pytest.param("unanswered", "ANSWERED_KEEP", 7, tg.test_まだ知らせていない控えは上限で黙って落ちない,
                 ("return done[-ANSWERED_KEEP:] + [e for e in recent if _unnotified(e)]", "return (done + [e for e in recent if _unnotified(e)])[:ANSWERED_KEEP]"),
                 id="ANSWERED_KEEP"),
    pytest.param("unanswered", "ASK_BATCH", 2, tg.test_出し直しは頭の4件で切らず_5件目まで全部渡す,
                 ("for n, it in enumerate(items, 1):", "for n, it in enumerate(items[:ASK_BATCH], 1):"),
                 id="ASK_BATCH-出し直し"),
    pytest.param("unanswered", "ASK_BATCH", 7, tg.test_閉じた問いが5つでも隣の1行に全部の文面が載る,
                 ('for i in unanswered)', 'for i in unanswered[:ASK_BATCH])'),
                 id="ASK_BATCH-閉じた問い"),
    pytest.param("irreversible", "STEMS_SHOWN", 2, tg.test_離席の止めは閉じた問いが多い時ほか何件と置き場を出す,
                 ("qs[:STEMS_SHOWN]", "qs[:STEMS_SHOWN + 1]"), id="STEMS_SHOWN"),
    pytest.param("qa_page", "RED_SHOWN", 5, tg.test_qa_page_赤が多い時ほか何件と全部の出し方を出す,
                 ("red[:RED_SHOWN]", "red[:RED_SHOWN + 1]"), id="RED_SHOWN", marks=needs_node),
]


def _swap(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{path.name} に {old!r} が 1 か所で無い（注入の当て所が正本から外れた）"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _guard_copy(env, tmp_path, module, name, value, cut=None):
    """guard の写し（without_check が回す所）の正本の値を value に変え、cut があれば切りの誤りも入れた env。"""
    root = tmp_path / "cache" / "market" / "guard" / "v1"
    shutil.copytree(tg.PLUGIN, root)
    src = root / "scripts" / (module + ".py")
    text = src.read_text(encoding="utf-8")
    text, n = re.subn(r"^%s = \d+" % name, "%s = %d" % (name, value), text, flags=re.M)
    assert n == 1, f"{module}.{name} の行が正本に 1 つで無い"
    src.write_text(text, encoding="utf-8")
    if cut:
        _swap(src, *cut)
    env = tg.without_check(env, tmp_path)
    assert tg.guard_limit(env, module, name) == value != tg.guard_limit({}, module, name)
    return env


def _run(test, env, tmp_path):
    return test(env, tmp_path) if test.__code__.co_argcount == 2 else test(env)


@pytest.mark.parametrize("module,name,value,test,cut", GUARD_CASES)
def test_guard_の上限の試験は正本の値を変えても境目のすぐ上で緑(env, tmp_path, module, name, value, test, cut):
    _run(test, _guard_copy(env, tmp_path, module, name, value), tmp_path)


@pytest.mark.parametrize("module,name,value,test,cut", GUARD_CASES)
def test_注入_guard_の切りの誤りは上限の試験が赤(env, tmp_path, module, name, value, test, cut):
    with pytest.raises(AssertionError):
        _run(test, _guard_copy(env, tmp_path, module, name, value, cut), tmp_path)


def _smoke_copy(tmp_path, line_bytes, max_lines, cut=None):
    src = tmp_path / "plugin_smoke.py"
    shutil.copy(tl.ROOT / "scripts" / "plugin_smoke.py", src)
    _swap(src, "LINE_BYTES, MAX_LINES = 200, 100", "LINE_BYTES, MAX_LINES = %d, %d" % (line_bytes, max_lines))
    if cut:
        _swap(src, *cut)
    spec = importlib.util.spec_from_file_location("plugin_smoke_injected", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LINE_TESTS = [tl.test_注入_上限より1バイト長い行を足すと赤, tl.test_上限ちょうどの行は収まる_日本語はバイトで数える,
              tl.test_注入_上限より1行多い塊は赤]


def test_setup_script_の上限の試験は正本の値を変えても境目で緑(tmp_path, monkeypatch):
    block = tl.smoke.setup_block(tl.ROOT).splitlines()
    wide = max(len(s.encode("utf-8")) for s in block) + 7          # 今の塊が収まる、元と違う上限
    monkeypatch.setattr(tl, "smoke", _smoke_copy(tmp_path, wide, len(block) + 3))
    tl.test_使う側に貼る塊は道具の上限に収まる()
    for i, t in enumerate(LINE_TESTS):
        t(tmp_path / str(i))


@pytest.mark.parametrize("cut,test", [
    (("if n > LINE_BYTES]", "if n > LINE_BYTES + 1]"), tl.test_注入_上限より1バイト長い行を足すと赤),
    (("if n > LINE_BYTES]", "if n >= LINE_BYTES]"), tl.test_上限ちょうどの行は収まる_日本語はバイトで数える),
    (("if len(lines) > MAX_LINES:", "if len(lines) > MAX_LINES + 1:"), tl.test_注入_上限より1行多い塊は赤),
], ids=["1バイト越えを通す", "ちょうどを落とす", "1行越えを通す"])
def test_注入_setup_script_の境目の誤りは上限の試験が赤(tmp_path, monkeypatch, cut, test):
    block = tl.smoke.setup_block(tl.ROOT).splitlines()
    monkeypatch.setattr(tl, "smoke", _smoke_copy(tmp_path, max(len(s.encode("utf-8")) for s in block) + 7,
                                                 len(block) + 3, cut))
    with pytest.raises((AssertionError, pytest.fail.Exception, ValueError)):
        test(tmp_path / "t")
