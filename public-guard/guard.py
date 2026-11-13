#!/usr/bin/env python3
"""公開の検査の本体（土台に 1 つだけ置く。各公開 repo の CI は action `public-guard` を版を決めて呼ぶだけ）。

公開の repo は、いつ誰に見られてもよい状態に保つ。世界に見える物を全部照らす:
  - 中身: git の追跡するファイルの名と全行
  - 歴史: 照らす範囲の各 commit で足された行（消しても歴史に残るため）
  - 外側: commit の説明・名義（名とメール）と PR の題・本文

照らす物:
  - 秘密の形（鍵・トークン）と個人の情報の形（個人を指すメール・電話・郵便番号・Notion と Google の文書の URL）
  - commit の名義のメールは noreply だけ通す（GitHub の `@users.noreply.github.com`・`noreply@anthropic.com`）
  - 置かない語（repo ごとの表。`--deny-words-file`。土台は業務の語の表を渡す）
  - 顧客の語（repo に書かない。環境から渡す。どちらか・両方でよい）
      AF_DENY_BUNDLE … 語を HMAC にした束 `pct1.<鍵>.<束>`（Javis の顧客の語の束と同じ形・同じ値を貼る）
      AF_DENY_WORDS（1 行 1 語）／AF_DENY_WORDS_FILE（その形のファイルの path）
    CI（GITHUB_ACTIONS=true）でどれも無い時は黙って通さず止める。手元でどれも無い時だけ飛ばす。
語そのものは出力に出さない（どこに当たったかだけを出す）。

使い方: python3 guard.py [--repo DIR] [--range REV|ALL] [--deny-words-file F] [--pattern-skip PATH ...] [--files-only]
  --range の既定: CI では event（PR は base..head・push は before..after）、手元では origin/main..HEAD。
  ALL は全ての commit（公開の前に歴史ごと照らす時）。
exit: 0=当たり 0 / 1=当たりあり・CI に顧客の語が無い / 2=使い方・束の形が違う
"""
from __future__ import annotations

import argparse
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
# commit の名義に通すメール（noreply だけ）
NOREPLY_EMAIL = re.compile(r"(@users\.noreply\.github\.com|^noreply@github\.com|^noreply@anthropic\.com)$", re.IGNORECASE)
# 文の中で通すメール（noreply と作り物の置き場）
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

CUSTOMER_HINT = "repo の secret AF_DENY_BUNDLE か AF_DENY_WORDS を入れ、呼ぶ workflow から渡す（docs/公開の検査.md）"


# ---- 語の読み口 ----------------------------------------------------------------

def parse_words(text: str) -> list[str]:
    return [s.strip() for s in text.splitlines() if s.strip() and not s.strip().startswith("#")]


def file_words(path: str | Path | None) -> list[str]:
    """repo ごとの置かない語の表（無ければ空）。"""
    if not path:
        return []
    return parse_words(Path(path).read_text(encoding="utf-8"))


def env_deny_words() -> list[str]:
    """顧客の語の平文（AF_DENY_WORDS／AF_DENY_WORDS_FILE）。"""
    text = os.environ.get("AF_DENY_WORDS", "")
    path = os.environ.get("AF_DENY_WORDS_FILE", "")
    if path:
        text += "\n" + Path(path).read_text(encoding="utf-8")
    return parse_words(text)


# ---- 束（HMAC）の照らし。Javis の顧客の語の束と同じ形 -------------------------------

BUNDLE_PREFIX = "pct1"
DIGEST = 8
MIN_N, MAX_N = 2, 16
MAX_W = 4
RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆ヶぁ-ゟァ-ヺー]+")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9&'.-]*[A-Za-z0-9]|[A-Za-z]")
_K = "㐀-䶿一-鿿豈-﫿々〆ヶぁ-ゟァ-ヺー"
GAP = re.compile("(?<=[%s])[\\s・･]+(?=[%s])" % (_K, _K))


def decode_bundle(value: str):
    """(鍵, 束の set)。形が違えば ValueError（理由には値を入れない＝どこが違うかだけ）。"""
    text = (value or "").strip()
    parts = text.split(".")
    if len(parts) != 3 or parts[0] != BUNDLE_PREFIX:
        raise ValueError(_shape_reason(text, parts))
    try:
        key = base64.urlsafe_b64decode(parts[1])
        raw = base64.urlsafe_b64decode(parts[2])
    except ValueError as e:
        raise ValueError("鍵か束の所が base64 として読めない（途中で切れた・余計な字が混じった）") from e
    if len(key) < 16:
        raise ValueError("鍵の所が短い（16 バイト未満）")
    if not raw or len(raw) % DIGEST:
        raise ValueError(f"束の所の長さが {DIGEST} バイトの倍数でない（途中で切れた）")
    return key, {raw[i:i + DIGEST] for i in range(0, len(raw), DIGEST)}


def _shape_reason(text: str, parts: list[str]) -> str:
    """形の違いの理由。値そのものは返さない。"""
    if not text:
        return "値が空"
    if text[0] in "'\"" or text[-1] in "'\"":
        return "前後に引用符が付いている（引用符を外した中身だけを貼る）"
    if "=" in text.split(".")[0]:
        return "先頭に名前と = が付いている（= の後ろの値だけを貼る）"
    if len(text.splitlines()) > 1:
        return f"値が {len(text.splitlines())} 行ある（1 行の値だけを貼る）"
    if not text.startswith(BUNDLE_PREFIX + "."):
        return f"先頭が {BUNDLE_PREFIX}. でない（別の値を貼っている）"
    return f"区切りの . が {len(parts) - 1} 個（2 個のはず）"


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

def pattern_hits(where: str, text: str) -> list[str]:
    """秘密と個人の情報の形。"""
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


class Guard:
    """1 つの repo を照らす。words＝置かない語の表、skip＝形の照らしから外す path（形を書いた所だけ）。"""

    def __init__(self, repo: Path, words: list[str], skip: set[str], words_home: str | None = None):
        self.repo = repo
        self.words = words
        self.skip = skip
        self.words_home = words_home  # 置かない語の表そのもの（語の照らしから外す）
        self.cust_words = env_deny_words()
        self.bundle = env_bundle()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout

    def text_hits(self, where: str, text: str, path: str | None = None) -> list[str]:
        hits = []
        if path not in self.skip:
            hits += pattern_hits(where, text)
        if path != self.words_home:
            hits += word_hits(where, text, self.words)
        hits += customer_hits(where, text, self.cust_words, self.bundle)
        return hits

    def place(self, path: str) -> str:
        """出力に出す場所の名。path そのものに置かない物があれば伏せる（公開の Actions のログは誰でも読める）。"""
        if self.text_hits("", path, None if path in self.skip else path):
            return "名に置かない物があるファイル #" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]
        return path

    # 中身
    def tracked_files(self):
        out = subprocess.run(["git", "ls-files", "-z"], cwd=self.repo, capture_output=True, check=True).stdout
        for rel in filter(None, out.decode("utf-8").split("\0")):
            path = self.repo / rel
            if not path.is_file():
                continue
            try:
                yield rel, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                yield rel, ""  # 文字でないファイルも名は照らす

    def check_files(self) -> list[str]:
        hits = []
        for rel, text in self.tracked_files():
            hits += self.text_hits(self.place(rel), rel + "\n" + text, rel)
        return hits

    # 歴史と外側
    def revs(self, rev_range: str | None, event: dict) -> list[str]:
        if rev_range == "ALL":
            return ["--all"]
        if rev_range:
            return [rev_range]
        pr = event.get("pull_request") or {}
        if pr:
            return [f"{pr['base']['sha']}..{pr['head']['sha']}"]
        if event.get("after"):
            before, after = event.get("before") or "", event["after"]
            # 新しい枝（before が 0 の並び）は先端の 1 つだけを見る
            return ["-1", after] if (not before or set(before) == {"0"}) else [f"{before}..{after}"]
        return ["origin/main..HEAD"]

    def check_history(self, revs: list[str]) -> list[str]:
        """各 commit で足された行（ファイルの名と行）。merge の commit も各親との差で見る（-m）。

        path は引用符なしで取る（core.quotePath=false）。それでも `"`・タブ・改行・`\\` を含む名は C の形の引用で出るので解く
        （解けない名も行は捨てず、仮の名で照らす）。見出し（+++）は `diff --git` から最初の `@@` までの間でだけ読む
        （中身が `++ ` で始まる足された行を見出しと取り違えない）。"""
        hits = []
        log = self.git("-c", "core.quotePath=false", "log", "-p", "-m", "--no-color", "--no-ext-diff",
                       "--no-renames", "--format=\x1e%h", *revs)
        for chunk in filter(None, log.split("\x1e")):
            sha, _, diff = chunk.partition("\n")
            path, in_header, added = None, False, {}
            for line in diff.splitlines():
                if line.startswith("diff --git "):
                    path, in_header = None, True
                elif in_header:
                    if line.startswith("+++ "):
                        path = diff_path(line[4:])
                        if path:
                            added.setdefault(path, [])
                    elif line.startswith("@@"):
                        in_header = False
                elif path and line.startswith("+"):
                    added[path].append(line[1:])
            for path, lines in added.items():
                hits += self.text_hits(f"commit {sha} の {self.place(path)}", path + "\n" + "\n".join(lines), path)
        return hits

    def check_meta(self, revs: list[str], event: dict) -> list[str]:
        hits = []
        pr = event.get("pull_request") or {}
        if pr:
            hits += self.text_hits("PR の題", pr.get("title") or "")
            hits += self.text_hits("PR の本文", pr.get("body") or "")
        sep, end = "\x1f", "\x1e"
        log = self.git("log", f"--format=%h{sep}%an{sep}%ae{sep}%cn{sep}%ce{sep}%B{end}", *revs)
        for rec in filter(None, (r.strip("\n") for r in log.split(end))):
            sha, an, ae, cn, ce, body = rec.split(sep, 5)
            for mail in {ae, ce}:
                if mail and not NOREPLY_EMAIL.search(mail):
                    hits.append(f"commit {sha} の名義のメール: noreply でない（GitHub の noreply を使う）")
            hits += self.text_hits(f"commit {sha} の名義", f"{an}\n{cn}")
            hits += self.text_hits(f"commit {sha} の説明", body)
        return hits


UNREADABLE_PATH = "名を読めないファイル"
_C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def diff_path(spec: str) -> str | None:
    """`+++ ` の後ろ（`b/…`・`"b/…"`・`/dev/null`）から path を取る。消したファイル（/dev/null）は None。
    読めない形でも足された行を捨てないよう、None でなく仮の名を返す。"""
    if spec == "/dev/null":
        return None
    if spec.startswith('"') and spec.endswith('"') and len(spec) >= 2:
        body, out, i = spec[1:-1], bytearray(), 0
        try:
            while i < len(body):
                c = body[i]
                if c != "\\":
                    out += c.encode("utf-8")
                    i += 1
                elif body[i + 1] in _C_ESCAPES:
                    out.append(_C_ESCAPES[body[i + 1]])
                    i += 2
                elif body[i + 1:i + 4].isdigit() and len(body[i + 1:i + 4]) == 3:
                    out.append(int(body[i + 1:i + 4], 8))
                    i += 4
                else:
                    return UNREADABLE_PATH
            spec = out.decode("utf-8", errors="replace")
        except (IndexError, ValueError):
            return UNREADABLE_PATH
    return spec[2:] if spec.startswith("b/") else UNREADABLE_PATH


def load_event() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH", "")
    if path and Path(path).is_file():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def run(repo: Path, rev_range: str | None, words_file: str | None, skip: list[str], event: dict | None = None,
        files_only: bool = False) -> list[str]:
    """words_file と skip は repo の根からの path。files_only は中身だけ（歴史を持ち越さない新しい repo へ移す前）。"""
    guard = Guard(repo, file_words(repo / words_file if words_file else None), set(skip), words_file)
    hits = guard.check_files()
    if not files_only:
        event = load_event() if event is None else event
        revs = guard.revs(rev_range, event)
        hits += guard.check_history(revs) + guard.check_meta(revs, event)
    return sorted(set(hits))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公開の検査（中身・歴史・外側）")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--range", dest="rev_range")
    ap.add_argument("--deny-words-file")
    ap.add_argument("--pattern-skip", nargs="*", default=[])
    ap.add_argument("--files-only", action="store_true", help="中身だけ（歴史を持ち越さない新しい repo へ移す前）")
    a = ap.parse_args(argv)
    repo = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=a.repo,
                               capture_output=True, text=True, check=True).stdout.strip())
    try:
        env_bundle()
    except ValueError as e:
        print(f"✗ AF_DENY_BUNDLE の形が違う（pct1.<鍵>.<束> の 1 行）: {e}")
        return 2
    if customer_source_missing():
        if in_ci():
            print(f"✗ 顧客の語がどこからも渡っていない（{CUSTOMER_HINT}）")
            return 1
        print("（手元: 顧客の語が環境に無いので、顧客の語の照合だけ飛ばす）")
    try:
        hits = run(repo, a.rev_range, a.deny_words_file, a.pattern_skip, files_only=a.files_only)
    except subprocess.CalledProcessError as e:
        print(f"✗ git が照らす範囲を読めない（force push の後で前の commit が無い・取り出しが浅い等）: {' '.join(e.cmd[1:4])}")
        return 1
    if hits:
        print("✗ 公開の repo に置かない物:\n  " + "\n  ".join(hits))
        return 1
    print("✅ 公開の検査: 置かない物 0（中身・歴史・外側）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
