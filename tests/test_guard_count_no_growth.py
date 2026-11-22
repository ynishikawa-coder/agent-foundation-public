"""守りの数（guard の見張り・CI の検査・レビューの点）も main より増えたら赤（オーナー同意 2026-11-23: 守るための守りを足し続けない）。
安全の守り（kaku.SAFETY）は数えない。試験は数を出すだけで止めない。本体は kaku.py grow（CI は scripts/checks/kaku_growth.sh）。"""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)

TABLE = "| 点 | 見る事 | red |\n|---|---|---|\n| 1 甲 | a | b |\n| 2 乙 | a | b |\n\n| 言語 | 点 |\n|---|---|\n| Python | x |\n"

HOOKS_JSON = {"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "guard.py pre"}]}]}}
CI = "jobs:\n  a:\n    steps:\n      - run: bash scripts/check_all.sh\n      - name: x\n        run: python3 public-guard/patrol.py\n"
NEW_HOOK = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "watch.py --stop"}]}]}}


def _g(root, *a):
    subprocess.run(["git", *a], cwd=root, check=True, capture_output=True)


def _repo(tmp_path, monkeypatch):
    """作り物の repo: 見張り 1・安全の見張り 1・検査 1・安全の検査 1・点 2。"""
    _g(tmp_path, "init", "-q")
    _g(tmp_path, "config", "user.email", "t@example.invalid")
    _g(tmp_path, "config", "user.name", "t")
    g = tmp_path / kaku.GUARD_HOOKS
    g.mkdir(parents=True)
    (g / "ask_shape.py").write_text('HOOKS = {"PreToolUse": 1}\n', encoding="utf-8")
    (g / "irreversible.py").write_text('HOOKS = {"PreToolUse": 1}\n', encoding="utf-8")
    (g / "_common.py").write_text("x = 1\n", encoding="utf-8")
    c = tmp_path / kaku.CHECKS
    c.mkdir(parents=True)
    (c / "pr_shape.sh").write_text("true\n", encoding="utf-8")
    (c / "public_guard.sh").write_text("true\n", encoding="utf-8")
    r = tmp_path / kaku.REVIEW_POINTS
    r.parent.mkdir(parents=True)
    r.write_text(TABLE, encoding="utf-8")
    h = tmp_path / "plugins" / "guard" / "hooks"
    h.mkdir(parents=True)
    (h / "hooks.json").write_text(json.dumps(HOOKS_JSON), encoding="utf-8")
    (tmp_path / "plugins" / "session-watch").mkdir()
    w = tmp_path / kaku.WORKFLOWS
    w.mkdir(parents=True)
    (w / "ci.yml").write_text(CI, encoding="utf-8")
    _g(tmp_path, "add", "-A")
    _g(tmp_path, "commit", "-q", "-m", "元")
    monkeypatch.setattr(kaku, "REPO", tmp_path)
    monkeypatch.setattr(kaku, "guarded", lambda: ())
    return g, c, r


def test_数える物と安全の除外():
    assert {"irreversible.py", "outbound.py", "paid_upstream.py", "public_guard.sh"} <= kaku.SAFETY
    n = kaku.guard_counts()
    assert all(v > 0 for v in n.values()), n


def test_見張り_検査_点のどれかを足すと赤(tmp_path, monkeypatch, capsys):
    """注入: 安全でない見張り・検査・点を 1 つ足すと、それぞれ赤。"""
    g, c, r = _repo(tmp_path, monkeypatch)
    assert kaku.grow("HEAD") == 0
    for add, undo, name in (
        (lambda: (g / "new_watch.py").write_text("HOOKS = {}\n", encoding="utf-8"), lambda: (g / "new_watch.py").unlink(), "守りの見張り"),
        (lambda: (c / "new_check.sh").write_text("true\n", encoding="utf-8"), lambda: (c / "new_check.sh").unlink(), "CI の検査"),
        (lambda: r.write_text(TABLE.replace("| 2 乙 | a | b |\n", "| 2 乙 | a | b |\n| 3 丙 | a | b |\n"), encoding="utf-8"),
         lambda: r.write_text(TABLE, encoding="utf-8"), "レビューの点"),
        (lambda: (g / "typed.py").write_text("HOOKS: dict = {}\n", encoding="utf-8"), lambda: (g / "typed.py").unlink(), "守りの見張り"),
        (lambda: _put(tmp_path / "plugins" / "session-watch" / "hooks" / "hooks.json", json.dumps(NEW_HOOK)),
         lambda: (tmp_path / "plugins" / "session-watch" / "hooks" / "hooks.json").unlink(), "hook の口"),
        (lambda: (tmp_path / kaku.WORKFLOWS / "ci.yml").write_text(CI + "      - run: python3 scripts/new.py\n", encoding="utf-8"),
         lambda: (tmp_path / kaku.WORKFLOWS / "ci.yml").write_text(CI, encoding="utf-8"), "CI の段"),
    ):
        add()
        assert kaku.grow("HEAD") == 1, name
        assert f"✗ {name}" in capsys.readouterr().out
        undo()
        assert kaku.grow("HEAD") == 0, name


def _put(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_安全の守りと_HOOKS_の無い部品と_言語の表は数えない(tmp_path, monkeypatch):
    g, c, r = _repo(tmp_path, monkeypatch)
    (g / "outbound.py").write_text("HOOKS = {}\n", encoding="utf-8")
    (g / "paid_upstream.py").write_text("HOOKS = {}\n", encoding="utf-8")
    (g / "_helper.py").write_text("y = 2\n", encoding="utf-8")
    r.write_text(TABLE + "| Shell | y |\n", encoding="utf-8")
    (tmp_path / kaku.WORKFLOWS / "ci.yml").write_text(CI + "      - run: bash public_guard/check.sh\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 0


def test_1_つ足して_1_つ畳めば緑(tmp_path, monkeypatch):
    g, c, r = _repo(tmp_path, monkeypatch)
    (g / "new_watch.py").write_text("HOOKS = {}\n", encoding="utf-8")
    (g / "ask_shape.py").unlink()
    (c / "new_check.sh").write_text("true\n", encoding="utf-8")
    (c / "pr_shape.sh").unlink()
    assert kaku.grow("HEAD") == 0


def test_比べる元が読めなければ止める(tmp_path, monkeypatch, capsys):
    """注入: 比べる元が無い ref だと黙って緑にせず 2。"""
    _repo(tmp_path, monkeypatch)
    assert kaku.grow("no-such-ref") == 2
    assert "守りの数を照らせない" in capsys.readouterr().out


def test_試験は数を出すだけで止めない(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, monkeypatch)
    t = tmp_path / "tests"
    t.mkdir()
    (t / "test_a.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    _g(tmp_path, "add", "-A")
    _g(tmp_path, "commit", "-q", "-m", "試験")
    (t / "test_b.py").write_text("def test_y():\n    pass\n", encoding="utf-8")
    assert kaku.grow("HEAD") == 0
    assert "試験: 2 file・2 本" in capsys.readouterr().out
