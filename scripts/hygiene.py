#!/usr/bin/env python3
"""置かない物（秘密・個人の情報・業務の語・顧客の語）の照らしの 1 本（試験と CI の両方がここを読む）。

この repo は public＝ファイルだけでなく commit の説明・名義・PR の題と本文も世界に見える。
照らす先は 2 つ:
  - 中身: git の追跡するファイルの名と全行（tests/test_hygiene.py が呼ぶ）
  - 外側: commit の説明・名義（名とメール）と PR の題・本文（`python3 scripts/hygiene.py meta`・scripts/checks/meta.sh が呼ぶ）

顧客の語は repo に書かない。環境から 2 つの形で渡す（どちらか・両方でよい）:
  - AF_DENY_WORDS（1 行 1 語）／AF_DENY_WORDS_FILE（その形のファイルの path）
  - AF_DENY_BUNDLE（語を HMAC にした束 `pct1.<鍵>.<束>`。使う側の repo の顧客の語の束と同じ形・同じ値を貼ればよい）
CI（GITHUB_ACTIONS=true）でどちらも無い時は黙って通さず止める（顧客の語の照合が飛んだまま緑になるのを防ぐ）。
語そのものは出力に出さない（どこに当たったかだけを出す）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DENYLIST = ROOT / "tests" / "data" / "denylist.txt"
# 形を書いた所（このファイルと試験）は、形の照らしから外す（語の照らしは外さない）
PATTERN_HOMES = {"scripts/hygiene.py", "tests/test_hygiene.py"}

SECRET_PATTERNS = {
    "GitHub のトークン": r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}",
    "Anthropic の鍵": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI 形の鍵": r"sk-[A-Za-z0-9]{40,}",
    "AWS の鍵 ID": r"AKIA[0-9A-Z]{16}",
    "Slack のトークン": r"xox[abpors]-[A-Za-z0-9-]{10,}",
    "Google の鍵": r"AIza[0-9A-Za-z_\-]{35}|ya29\.[0-9A-Za-z_\-]{20,}",
    "Notion のトークン": r"\b(?:secret_|ntn_)[A-Za-z0-9]{30,}",
    "秘密鍵": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}

EMAIL = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
# 個人を指さないメール（GitHub と Anthropic の返信を受けない名義・作り物の置き場）
SAFE_EMAIL = re.compile(
    r"(@users\.noreply\.github\.com|^noreply@github\.com|^noreply@anthropic\.com"
    r"|@example\.(com|org|net)|\.(invalid|test|example|localhost))$",
    re.IGNORECASE,
)
PERSONAL_PATTERNS = {
    "電話番号": r"(?<![\d\-])0\d{1,4}-\d{1,4}-\d{4}(?![\d\-])|(?<!\d)0[789]0\d{8}(?!\d)",
    "郵便番号": r"〒\s?\d{3}-?\d{4}",
    "Notion のページ": r"notion\.(?:so|site)/[^\s)\]]+",
    "Google の文書・置き場": r"(?:docs|drive|sheets)\.google\.com/[^\s)\]]+",
}


# ---- 語の読み口 ----------------------------------------------------------------

def parse_words(text: str) -> list[str]:
    return [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith("#")]


def deny_words() -> list[str]:
    """業務の語（repo の表）。"""
    return parse_words(DENYLIST.read_text(encoding="utf-8"))


def env_deny_words() -> list[str]:
    """顧客の語の平文（AF_DENY_WORDS／AF_DENY_WORDS_FILE）。"""
    text = os.environ.get("AF_DENY_WORDS", "")
    path = os.environ.get("AF_DENY_WORDS_FILE", "")
    if path:
        text += "\n" + Path(path).read_text(encoding="utf-8")
    return parse_words(text)


# ---- 束（HMAC）の照らし。使う側の repo の顧客の語の束と同じ形 ------------------------

BUNDLE_PREFIX = "pct1"
DIGEST = 8
MIN_N, MAX_N = 2, 16
MAX_W = 4
RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆ヶぁ-ゟァ-ヺー]+")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9&'.-]*[A-Za-z0-9]|[A-Za-z]")
_K = "㐀-䶿一-鿿豈-﫿々〆ヶぁ-ゟァ-ヺー"
GAP = re.compile("(?<=[%s])[\\s・･]+(?=[%s])" % (_K, _K))


def decode_bundle(value: str):
    """(鍵, 束の set)。形が違えば ValueError。"""
    parts = (value or "").strip().split(".")
    if len(parts) != 3 or parts[0] != BUNDLE_PREFIX:
        raise ValueError("束の形が違う")
    key = base64.urlsafe_b64decode(parts[1])
    raw = base64.urlsafe_b64decode(parts[2])
    if len(key) < 16 or not raw or len(raw) % DIGEST:
        raise ValueError("束の形が違う")
    return key, {raw[i:i + DIGEST] for i in range(0, len(raw), DIGEST)}


def env_bundle():
    """(鍵, 束) か None。値があって形が違う時は ValueError（黙って通さない）。"""
    value = os.environ.get("AF_DENY_BUNDLE", "")
    return decode_bundle(value) if value.strip() else None


def grams(line: str) -> set[str]:
    text = unicodedata.normalize("NFKC", line)
    out = set()
    words = [w.lower().replace(".", "") for w in WORD.findall(text)]
    for i in range(len(words)):
        for j in range(i + 1, min(i + MAX_W, len(words)) + 1):
            out.add("w:" + " ".join(words[i:j]))
    for run in RUN.findall(GAP.sub("", text)):
        n = len(run)
        for i in range(n - 1):
            for j in range(i + MIN_N, min(i + MAX_N, n) + 1):
                out.add(run[i:j])
    return out


def bundle_hit(bundle, line: str) -> bool:
    key, digests = bundle
    return any(hmac.new(key, g.encode("utf-8"), hashlib.sha256).digest()[:DIGEST] in digests
               for g in grams(line))


def customer_source_missing() -> bool:
    """顧客の語がどこからも渡っていない。"""
    return not env_deny_words() and not os.environ.get("AF_DENY_BUNDLE", "").strip()


def in_ci() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


# ---- 照らす本体（場所と札だけを返す・語は返さない） ---------------------------------

def pattern_hits(where: str, text: str, skip_patterns: bool = False) -> list[str]:
    """秘密と個人の情報の形。"""
    if skip_patterns:
        return []
    hits = [f"{where}: {label}" for label, pat in SECRET_PATTERNS.items() if re.search(pat, text)]
    hits += [f"{where}: {label}" for label, pat in PERSONAL_PATTERNS.items() if re.search(pat, text)]
    if any(not SAFE_EMAIL.search(m) for m in re.findall(EMAIL, text)):
        hits.append(f"{where}: メールアドレス")
    return hits


def word_hits(where: str, text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [f"{where}: 置かない語" for w in words if w.lower() in low][:1]


def customer_hits(where: str, text: str, words: list[str], bundle) -> list[str]:
    low = text.lower()
    if any(w.lower() in low for w in words):
        return [f"{where}: 顧客の語"]
    if bundle and any(bundle_hit(bundle, line) for line in text.splitlines() or [text]):
        return [f"{where}: 顧客の語"]
    return []


def tracked_text_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    for rel in filter(None, out.decode("utf-8").split("\0")):
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            yield rel, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            yield rel, ""  # 文字でないファイルも名は照らす


# ---- 外側（commit と PR） --------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def meta_items(event_path: str | None, rev_range: str | None):
    """(場所, 文字列, メールか) の並び。event があれば PR か push の範囲、無ければ rev_range（既定 origin/main..HEAD）。"""
    items = []
    event = {}
    if event_path and Path(event_path).is_file():
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    pr = event.get("pull_request") or {}
    revs = [rev_range or "origin/main..HEAD"]
    if pr:
        items.append(("PR の題", pr.get("title") or "", False))
        items.append(("PR の本文", pr.get("body") or "", False))
        revs = [f"{pr['base']['sha']}..{pr['head']['sha']}"]
    elif event.get("after"):
        before, after = event.get("before") or "", event["after"]
        # 新しい枝（before が 0 の並び）は先端の 1 つだけを見る
        revs = ["-1", after] if (not before or set(before) == {"0"}) else [f"{before}..{after}"]
    sep, end = "\x1f", "\x1e"
    log = _git("log", f"--format=%h{sep}%an{sep}%ae{sep}%cn{sep}%ce{sep}%B{end}", *revs)
    for rec in filter(None, (r.strip("\n") for r in log.split(end))):
        sha, an, ae, cn, ce, body = rec.split(sep, 5)
        items.append((f"commit {sha} の名義", f"{an}\n{cn}", False))
        items.append((f"commit {sha} の名義のメール", ae, True))
        items.append((f"commit {sha} の名義のメール", ce, True))
        items.append((f"commit {sha} の説明", body, False))
    return items


def check_meta(event_path=None, rev_range=None) -> list[str]:
    words, bundle = env_deny_words(), env_bundle()
    biz = deny_words()
    hits = []
    for where, text, is_mail in meta_items(event_path, rev_range):
        if is_mail:
            if text and not SAFE_EMAIL.search(text):
                hits.append(f"{where}: 個人を指すメール（GitHub の noreply を使う）")
            continue
        hits += pattern_hits(where, text)
        hits += word_hits(where, text, biz)
        hits += customer_hits(where, text, words, bundle)
    return sorted(set(hits))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] != "meta":
        print("使い方: python3 scripts/hygiene.py meta [<rev の範囲>]")
        return 2
    if in_ci() and customer_source_missing():
        print("✗ 顧客の語がどこからも渡っていない（repo の secret AF_DENY_BUNDLE か AF_DENY_WORDS を入れる・CONTRIBUTING §4）")
        return 1
    hits = check_meta(os.environ.get("GITHUB_EVENT_PATH"), argv[1] if len(argv) > 1 else None)
    if hits:
        print("✗ 公開される外側（commit・PR）に置かない物:\n  " + "\n  ".join(hits))
        return 1
    print("✅ 公開される外側（commit・PR）に置かない物 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
