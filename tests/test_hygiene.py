"""置かない物（秘密・業務の語・顧客の語）が repo に入っていないかを見る。"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DENYLIST = ROOT / "tests" / "data" / "denylist.txt"
SECRET_PATTERNS = {
    "GitHub のトークン": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "Anthropic の鍵": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI 形の鍵": r"sk-[A-Za-z0-9]{40,}",
    "AWS の鍵 ID": r"AKIA[0-9A-Z]{16}",
    "Slack のトークン": r"xox[abpors]-[A-Za-z0-9-]{10,}",
    "秘密鍵": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}


def tracked_text_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    for rel in filter(None, out.split("\0")):
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            yield rel, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def parse_words(text):
    words = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def deny_words():
    """業務の語（repo の表）。"""
    return parse_words(DENYLIST.read_text(encoding="utf-8"))


def env_deny_words():
    """顧客の語（repo に置かない。CI の secret か手元の環境・ファイルから渡す）。"""
    text = os.environ.get("AF_DENY_WORDS", "")
    path = os.environ.get("AF_DENY_WORDS_FILE", "")
    if path:
        text += "\n" + Path(path).read_text(encoding="utf-8")
    return parse_words(text)


def test_置かない語の表が読める():
    assert deny_words(), "denylist.txt が空"


def test_秘密が無い():
    hits = []
    for rel, text in tracked_text_files():
        for label, pat in SECRET_PATTERNS.items():
            if rel == "tests/test_hygiene.py":
                continue
            if re.search(pat, text):
                hits.append(f"{rel}: {label}")
    assert not hits, hits


def find_words(words):
    hits = []
    for rel, text in tracked_text_files():
        if rel == "tests/data/denylist.txt":
            continue
        low = text.lower()
        for w in words:
            if w.lower() in low:
                hits.append(f"{rel}: {w}")
    return hits


def test_業務の語が無い():
    hits = find_words(deny_words())
    assert not hits, hits


def test_顧客の語が無い():
    words = env_deny_words()
    if not words:
        pytest.skip("顧客の語が環境に無い（AF_DENY_WORDS / AF_DENY_WORDS_FILE）")
    # 語そのものを出力に出さない（secret のため）。assert にはファイル名だけを渡す。
    files = sorted({h.split(": ")[0] for h in find_words(words)})
    assert not files, files


def test_顧客の語は赤の時も出力に出ない():
    # repo の中身にあり、ファイル名には無い語を、顧客の語のふりで渡して赤にする。
    probe = "合流役"
    assert find_words([probe]), "見本の語が repo に無い（見本を替える）"
    env = {**os.environ, "AF_DENY_WORDS": probe}
    env.pop("AF_DENY_WORDS_FILE", None)
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_hygiene.py::test_顧客の語が無い"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    out = res.stdout + res.stderr
    assert res.returncode != 0, "顧客の語があるのに赤にならない"
    assert probe not in out, "顧客の語が出力に出た"
