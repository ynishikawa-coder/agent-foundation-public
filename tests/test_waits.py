"""待つ物の表 tests/waits.txt が今の repo と合っているか。

表の行は「まだ無い・どれかの試験が wait_for で待っている」物だけ。入った物の行が残ると、後で同じ path を
待つ形が黙って許される（古い道は畳む）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rows():
    text = (ROOT / "tests" / "waits.txt").read_text(encoding="utf-8")
    return [ln.split()[:2] for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def test_表の物はまだ無く_表の試験が待っている():
    for rel, waiter in rows():
        assert not (ROOT / rel).exists(), f"{rel} はもう在る。表から外し、試験の wait_for を畳む"
        user = (ROOT / waiter).read_text(encoding="utf-8")
        assert f'"{rel}"' in user and "wait_for(" in user, f"{rel} を待つ試験が表の {waiter} に無い。表を直す"
