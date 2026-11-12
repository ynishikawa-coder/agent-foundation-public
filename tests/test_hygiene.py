"""置かない物（秘密・個人の情報・業務の語・顧客の語）が repo に入っていないかを見る。照らしの本体は scripts/hygiene.py。"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hygiene  # noqa: E402


def test_置かない語の表が読める():
    assert hygiene.deny_words(), "denylist.txt が空"


def test_秘密と個人の情報が無い():
    hits = []
    for rel, text in hygiene.tracked_text_files():
        hits += hygiene.pattern_hits(rel, text, skip_patterns=rel in hygiene.PATTERN_HOMES)
    assert not hits, hits


def test_業務の語が無い():
    words = hygiene.deny_words()
    hits = []
    for rel, text in hygiene.tracked_text_files():
        if rel == "tests/data/denylist.txt":
            continue
        hits += hygiene.word_hits(rel, rel + "\n" + text, words)
    assert not hits, hits


def test_顧客の語が無い():
    if hygiene.customer_source_missing():
        if hygiene.in_ci():
            pytest.fail("CI に顧客の語が渡っていない（repo の secret AF_DENY_BUNDLE か AF_DENY_WORDS を入れる・CONTRIBUTING §4）")
        pytest.skip("顧客の語が環境に無い（AF_DENY_BUNDLE / AF_DENY_WORDS / AF_DENY_WORDS_FILE）")
    words, bundle = hygiene.env_deny_words(), hygiene.env_bundle()
    files = set()
    for rel, text in hygiene.tracked_text_files():
        if hygiene.customer_hits(rel, rel + "\n" + text, words, bundle):
            files.add(rel)
    # 語そのものを出力に出さない（secret のため）。assert にはファイル名だけを渡す。
    assert not files, sorted(files)


# ---- 照らしが効くかの見本（作り物の値だけ） ---------------------------------------

@pytest.mark.parametrize("text", [
    "連絡先 taro.yamada@gmail.com",
    "電話 03-1234-5678",
    "携帯 09012345678",
    "〒100-0001",
    "https://www.notion.so/abc123",
    "https://docs.google.com/spreadsheets/d/abc",
])
def test_個人の情報の形は赤(text):
    assert hygiene.pattern_hits("見本", text)


@pytest.mark.parametrize("text", [
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "284810416+someone@users.noreply.github.com",
    "t@example.invalid",
    "2026-11-12 13:00",
    "@pytest.mark.parametrize",
])
def test_個人を指さない物は緑(text):
    assert not hygiene.pattern_hits("見本", text)


def _bundle_of(words, key=b"k" * 32):
    digests = {hmac.new(key, w.encode(), hashlib.sha256).digest()[:hygiene.DIGEST] for w in words}
    return "%s.%s.%s" % (hygiene.BUNDLE_PREFIX, base64.urlsafe_b64encode(key).decode(),
                         base64.urlsafe_b64encode(b"".join(sorted(digests))).decode())


def test_束の語は文の中でも当たる():
    bundle = hygiene.decode_bundle(_bundle_of(["見本商事"]))
    assert hygiene.customer_hits("見本", "今日は見本商事さんへ行く", [], bundle)
    assert not hygiene.customer_hits("見本", "今日は別の所へ行く", [], bundle)


def test_束の形が違えば止める():
    with pytest.raises(ValueError):
        hygiene.decode_bundle("pct1.壊れた.値")


def _run_test(env_extra, test_name):
    env = {k: v for k, v in os.environ.items()
           if k not in ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE", "GITHUB_ACTIONS")}
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tests/test_hygiene.py::{test_name}"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


def test_CIで顧客の語が無ければ赤():
    res = _run_test({"GITHUB_ACTIONS": "true"}, "test_顧客の語が無い")
    assert res.returncode != 0, "CI で顧客の語が渡っていないのに緑になった（照合が飛んだまま通る）"


def test_顧客の語は赤の時も出力に出ない():
    # repo の中身にあり、ファイル名には無い語を、顧客の語のふりで渡して赤にする（平文と束の両方）。
    probe = "土台"
    for extra in ({"AF_DENY_WORDS": probe}, {"AF_DENY_BUNDLE": _bundle_of([probe])}):
        res = _run_test(extra, "test_顧客の語が無い")
        out = res.stdout + res.stderr
        assert res.returncode != 0, "顧客の語があるのに赤にならない"
        assert probe not in out, "顧客の語が出力に出た"


def _commit(repo, msg, email):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": email}
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd=repo, env=env, check=True)


def _meta(tmp_path, monkeypatch, msg, email, pr_body=""):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    _commit(repo, "base", "t@example.invalid")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    _commit(repo, msg, email)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"title": "題", "body": pr_body,
                                                  "base": {"sha": base}, "head": {"sha": head}}}), encoding="utf-8")
    monkeypatch.setattr(hygiene, "ROOT", repo)
    for k in ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE"):
        monkeypatch.delenv(k, raising=False)
    return hygiene.check_meta(str(event))


def test_外側_個人のメールの名義は赤(tmp_path, monkeypatch):
    assert _meta(tmp_path, monkeypatch, "直した", "taro.yamada@gmail.com")


def test_外側_PRの本文の個人の情報は赤(tmp_path, monkeypatch):
    assert _meta(tmp_path, monkeypatch, "直した", "t@example.invalid", pr_body="電話 03-1234-5678")


def test_外側_noreplyの名義と普通の説明は緑(tmp_path, monkeypatch):
    assert not _meta(tmp_path, monkeypatch, "直した\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
                     "1+someone@users.noreply.github.com")
