"""待つ物の表 tests/waits.txt が今の repo と合っているか。

表の行は「まだ無い・どれかの試験が wait_for で待っている」物だけ。入った物の行が残ると、後で同じ path を
待つ形が黙って許される（古い道は畳む）。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rows():
    text = (ROOT / "tests" / "waits.txt").read_text(encoding="utf-8")
    return [ln.split()[0] for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def test_表の物はまだ無く_どれかの試験が待っている():
    users = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "tests").glob("test_*.py"))
    for rel in rows():
        assert not (ROOT / rel).exists(), f"{rel} はもう在る。表から外し、試験の wait_for を畳む"
        assert f'"{rel}"' in users and "wait_for(" in users, f"{rel} を待つ試験が無い。表から外す"
