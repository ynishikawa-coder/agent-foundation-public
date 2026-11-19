#!/usr/bin/env python3
"""公開の検査の本体（土台に 1 つだけ置く。各公開 repo の CI は action `public-guard` を版を決めて呼ぶだけ）。

公開の repo は、いつ誰に見られてもよい状態に保つ。世界に見える物を全部照らす:
  - 中身: git の追跡するファイルと、まだ git に入れていない新しいファイル（.gitignore の外）の名と全行。
    UTF-8 で読めない字は置き換えて読む（ASCII の鍵の形は照らす）。作業の木で消した追跡のファイルは index の中身を照らす
  - 歴史: 照らす範囲の各 commit で足された行（消しても歴史に残るため。バイナリの差分も字として照らす）
  - 外側: commit の説明・名義（名とメール）と PR の題・本文
照らしていない物は緑と言わない: 範囲の commit が 0・ファイルが 0・手元で PR の event が無く PR の題・本文を
照らしていない・顧客の語の照合を飛ばした・submodule の中身、のどれかが在れば、当たり 0 でも exit 3（照らしていない）で
名指す。名指した置かない語の表に語が 0 の時は 1 段目（前の形）: 名指して ✅ とは言わず exit 0（止めない）。
CI では exit 0 でない物は皆赤。
照合の前の正規化は normalize() 1 つ（NFKC・書式の字〔幅の無い空白など〕を除く）。語の照合はその上で大文字と小文字を
区別しない（fold()）。形・置かない語・顧客の語（平文と束）は皆これを通す（全角・互換の字ですり抜けない）。

照らす物:
  - 秘密の形（鍵・トークン）と個人の情報の形（個人を指すメール・電話・郵便番号・Notion と Google の文書の URL）
  - commit の名義のメールは noreply だけ通す（GitHub の `@users.noreply.github.com`・`noreply@anthropic.com`）
  - 置かない語（repo ごとの表。`--deny-words-file`。土台は業務の語の表を渡す）
  - 顧客の語（repo に書かない。環境から渡す。どちらか・両方でよい）
      AF_DENY_BUNDLE … 語を HMAC にした束 `pct1.<鍵>.<束>`（Javis の顧客の語の束と同じ形・同じ値を貼る）
      AF_DENY_WORDS（1 行 1 語）／AF_DENY_WORDS_FILE（その形のファイルの path）
    CI（GITHUB_ACTIONS=true）でどれも無い時は黙って通さず止める。手元でどれも無い時だけ飛ばす（exit 3）。
語そのものは出力に出さない（どこに当たったかだけを出す）。
--pattern-skip に名指したファイル: 印 `public-guard: 形の見本` が無い file は 1 段目の前の形（形を file ごと外す）。
印が在る file は、印の行の個人の情報の形だけを外す（秘密の形は印の行でも外さない・印の無い行は全部照らす・置かない語と顧客の語は外さない）。

使い方: python3 guard.py [--repo DIR] [--range REV|ALL] [--deny-words-file F] [--pattern-skip PATH ...] [--files-only]
        python3 guard.py --text <場所の名>=<file> [--text …] [--deny-words-file F]
  --text は、GitHub へ出す前の文（PR の題・本文・コメント）だけを同じ表で照らす（中身・歴史は見ない）。
  守りの hook（plugin guard の pr_text）が出す前に呼ぶ。顧客の語が無い・表に語が 0 の時はその照合を飛ばし、照らしていない事を
  出力に名指す（✅ と言わない。exit は CI でも 0＝hook が 0 以外を止めるため。3 にするには hook の受けを先に直す）。
  --range の既定: CI では event（PR は <base の枝の今の先端>..head・push は before..after。before が 0 の並び＝新しい枝は
  <既定の枝の今の先端>..after、既定の枝そのものか先端を聞けない時は after の全ての歴史）、手元では <出所の今の main>..HEAD。
  出所の今の枝の先端は scripts/pr_shape.py の fresh_main（出所へ先端を聞き、手元に無ければ取って来る・手元の origin/main は
  動かさない）。PR の event の base.sha は event の時の先端で、枝が後の main を取り込むと main の commit まで照らすので元にしない。
  出所に出られない時は、PR は event の base.sha・手元は手元の origin/main から照らしてそう名指す（古い元は範囲を広くする
  だけ＝見落としは出ない）。手元の origin/main も無ければ照らさずに止める（exit 2）。
  ALL は全ての commit（公開の前に歴史ごと照らす時）。
exit: 0=当たり 0 で照らす物を全部照らした / 1=当たりあり・CI に顧客の語が無い /
      2=使い方・束の形が違う・置かない語の表が無い・比べる元の main が取れない /
      3=照らしていない（当たりは 0 だが照らしていない物が在り、それを名指す。--text の口は 0 のまま・緑とは言わない）
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
    "OpenAI 形の鍵": r"sk-[A-Za-z0-9]{40,}|\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{20,}",
    "AWS の鍵 ID": r"(?<![0-9A-Z])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Z])",
    "Stripe の本番の鍵": r"\b[rs]k_live_[A-Za-z0-9]{20,}",
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
    """repo ごとの置かない語の表（path を渡さなければ空）。名指した表が無い・読めない時は OSError（空と取り違えない）。"""
    if not path:
        return []
    return parse_words(Path(path).read_text(encoding="utf-8"))


# ---- 照合の前の正規化（全部の照合がここを通る。1 つだけ） --------------------------------

def normalize(text: str) -> str:
    """NFKC にし、書式の字（幅の無い空白・向きの印など Cf）を除く。形・語・束の照合は皆この後の字で照らす。"""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text or "") if unicodedata.category(ch) != "Cf")


def fold(text: str) -> str:
    """語の照合の字: normalize の上で大文字と小文字を区別しない（束の語の作り方〔lower〕と同じ）。"""
    return normalize(text).lower()


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
    text = fold(line)
    out = set()
    words = [w.replace(".", "") for w in WORD.findall(text)]
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

def secret_labels(text: str) -> list[str]:
    """秘密の形に当たった札の並び（値は返さない）。秘密の形の正本はここ 1 つ。
    返事の差し戻し（plugin session-watch の Stop の hook）もこれを直に呼ぶ（写さない）。"""
    text = normalize(text)
    return [label for label, pat in SECRET_PATTERNS.items() if re.search(pat, text)]


def personal_labels(text: str) -> list[str]:
    """個人の情報の形に当たった札の並び（値は返さない）。"""
    text = normalize(text)
    labels = [label for label, pat in PERSONAL_PATTERNS.items() if re.search(pat, text)]
    # 文字列の中の書き方 \n・\t・\r は区切りと読む（"…\n@pytest.mark…" の n を名の頭と読まない。"\nuser@…" は拾う）
    if any(not SAFE_EMAIL.search(m) for m in re.findall(EMAIL, re.sub(r"\\[nrt]", " ", text))):
        labels.append("メールアドレス")
    return labels


def pattern_hits(where: str, text: str) -> list[str]:
    """秘密と個人の情報の形。"""
    return [f"{where}: {label}" for label in secret_labels(text) + personal_labels(text)]


# --pattern-skip のファイルで、個人の情報の形の照らしから外す行の印（形の見本を書いた行にだけ付ける）
SKIP_MARK = "public-guard: 形の見本"


def skipped_pattern_hits(where: str, text: str) -> list[str]:
    """--pattern-skip のファイルの形の照らし（壊れる 1 段目）。

    印が 1 行も無い file は前の形: 形の照らしを file ごと外す（秘密も個人の情報も）。使う側の CI をこの PR で赤にしない。
    見つけ方は plugins/core/古い形.json の public-guard-skip-whole-file。印を 1 行でも書いた file は新しい形:
    印の無い行は全部照らし、印の行は個人の情報の形だけ外し、秘密の形は印の行でも照らす。
    """
    if SKIP_MARK not in text:
        return []
    lines = text.splitlines()
    plain = "\n".join(ln for ln in lines if SKIP_MARK not in ln)
    marked = "\n".join(ln for ln in lines if SKIP_MARK in ln)
    return pattern_hits(where, plain) + [f"{where}: {label}" for label in secret_labels(marked)]


def word_hits(where: str, text: str, words: list[str]) -> list[str]:
    low = fold(text)
    n = sum(1 for w in words if fold(w) in low)
    return [f"{where}: 置かない語 {n} 個"] if n else []     # 語は出さない。数は出す（1 つ消して赤が残る往復をさせない）


def customer_hits(where: str, text: str, words: list[str], bundle) -> list[str]:
    low = fold(text)
    if any(fold(w) in low for w in words):
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
        self.unchecked: list[str] = []   # 照らしていない物（在れば緑と言わない＝exit 3）
        self.files_n = 0
        self.commits_n = 0

    def git(self, *args: str) -> str:
        # 字として読めないバイト（バイナリの差分・UTF-8 でない中身）は置き換えて読む（落とさず、ASCII の形は照らす）
        out = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, check=True).stdout
        return out.decode("utf-8", errors="replace")

    def text_hits(self, where: str, text: str, path: str | None = None) -> list[str]:
        hits = []
        if path in self.skip:
            hits += skipped_pattern_hits(where, text)
        else:
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
        """(path, 中身) の並び。追跡のファイル（index）と、まだ git に入れていない新しいファイル（.gitignore の外）。
        中身は作業の木から読み、作業の木に無い・普通のファイルでない物（消した・symlink）は index の中身を読む。
        UTF-8 で読めないバイトは置き換えて読む（中身を空にしない）。submodule は中身が別の repo なので名だけ照らし、名指す。"""
        staged = subprocess.run(["git", "ls-files", "-z", "-s"], cwd=self.repo, capture_output=True, check=True).stdout
        index = {}
        for rec in filter(None, staged.split(b"\0")):
            meta, _, rel = rec.partition(b"\t")
            mode, blob = meta.split()[:2]
            index[rel.decode("utf-8", errors="replace")] = (mode.decode(), blob.decode())
        others = subprocess.run(["git", "ls-files", "-z", "--others", "--exclude-standard"], cwd=self.repo,
                                capture_output=True, check=True).stdout
        names = list(index) + [r for r in filter(None, others.decode("utf-8", errors="replace").split("\0"))
                               if r not in index]
        for rel in names:
            path = self.repo / rel
            mode, blob = index.get(rel, ("", ""))
            if mode == "160000":
                self.unchecked.append(f"中身: submodule {self.place(rel)} の中身（別の repo。名だけ照らした）")
                yield rel, ""
            elif path.is_file() and not path.is_symlink():
                yield rel, path.read_bytes().decode("utf-8", errors="replace")
            elif blob:
                yield rel, self.git("cat-file", "blob", blob)
            else:
                yield rel, ""

    def check_files(self) -> list[str]:
        hits = []
        for rel, text in self.tracked_files():
            self.files_n += 1
            hits += self.text_hits(self.place(rel), rel + "\n" + text, rel)
        if not self.files_n:
            self.unchecked.append("中身: 照らすファイルが 0")
        return hits

    # 歴史と外側
    def revs(self, rev_range: str | None, event: dict) -> list[str]:
        if rev_range == "ALL":
            return ["--all"]
        if rev_range:
            return [rev_range]
        pr = event.get("pull_request") or {}
        if pr:
            return [f"{self.base_tip(pr)}..{pr['head']['sha']}"]
        if event.get("after"):
            before, after = event.get("before") or "", event["after"]
            if before and set(before) != {"0"}:
                return [f"{before}..{after}"]
            return self.new_branch_revs(event, after)
        if not in_ci():
            # 手元には PR の event が無い（GITHUB_EVENT_PATH を渡せば読む）。PR の題・本文は照らしていない
            self.unchecked.append("外側: PR の題・本文（手元には PR の event が無い。CI の job public-guard と、出す前の守りの"
                                  " hook pr_text が照らす）")
        return [f"{self.local_base()}..HEAD"]

    def new_branch_revs(self, event: dict, after: str) -> list[str]:
        """新しい枝の push（before が 0 の並び）の範囲。先端の 1 つだけでなく、既定の枝の今の先端に無い commit を全部見る。
        既定の枝そのものの初めての push・先端を聞けない時は after の全ての歴史（広い側＝見落としは出ない）と名指す。"""
        ref = str(event.get("ref") or "")
        ref = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
        default = str((event.get("repository") or {}).get("default_branch") or "main")
        if ref and ref != default:
            try:
                return [f"{fresh_main(self.repo, default)}..{after}"]
            except NoBase as e:
                print(f"public-guard: 知らせ — 新しい枝の push で {default} の今の先端を聞けず、{after[:12]} の全ての歴史を照らす"
                      f"（範囲は広い側＝見落としは出ない）: {e}", file=sys.stderr)
        return [after]

    def base_tip(self, pr: dict) -> str:
        """PR の範囲の元＝base の枝の今の先端（出所へ聞く）。event の base.sha は event の時の先端で、枝が後の main を
        取り込むと main の commit まで PR の物として照らす。聞けなければ base.sha（範囲は広い側＝見落としは出ない）と名指す。"""
        base = pr.get("base") or {}
        try:
            return fresh_main(self.repo, str(base.get("ref") or "main"))
        except NoBase as e:
            print(f"public-guard: 知らせ — base の枝の今の先端を聞けず、event の base.sha {str(base.get('sha'))[:12]} から照らす"
                  f"（範囲は広い側＝見落としは出ない）: {e}", file=sys.stderr)
            return str(base["sha"])

    def local_base(self) -> str:
        """手元の範囲の元＝出所の今の main（fresh_main・手元の origin/main は動かさない）。出所に出られなければ手元の
        origin/main から照らし、そう名指す（古い元は範囲を広くするだけ＝見落としは出ない。main で入った物で赤になりうる）。
        手元の origin/main も無ければ照らせない（NoBase）。"""
        try:
            return fresh_main(self.repo)
        except NoBase as e:
            r = subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/main^{commit}"], cwd=self.repo,
                               capture_output=True, text=True)
            local = r.stdout.strip() if r.returncode == 0 else ""
            if not local:
                raise
            print(f"public-guard: 知らせ — 出所に出られず、手元の origin/main {local[:12]} から照らした（範囲は広い側＝見落としは出ない。"
                  f"main で入った物で赤になりうる）: {e}")
            return local

    def check_history(self, revs: list[str]) -> list[str]:
        """各 commit で足された行（ファイルの名と行）。merge の commit も各親との差で見る（-m）。

        path は引用符なしで取る（core.quotePath=false）。それでも `"`・タブ・改行・`\\` を含む名は C の形の引用で出るので解く
        （解けない名も行は捨てず、仮の名で照らす）。見出し（+++）は `diff --git` から最初の `@@` までの間でだけ読む
        （中身が `++ ` で始まる足された行を見出しと取り違えない）。"""
        hits = []
        # バイナリの差分も字として出す（--text）。区切りは回すごとの乱れた印（中身の \x1e で区切りを取り違えない）
        mark = "\x1e" + os.urandom(16).hex()
        log = self.git("-c", "core.quotePath=false", "log", "-p", "-m", "--text", "--no-color", "--no-ext-diff",
                       "--no-renames", f"--format={mark}%h", *revs)
        for chunk in filter(None, log.split(mark)):
            sha, _, diff = chunk.partition("\n")
            path, in_header, added = None, False, {}
            for line in diff.split("\n"):  # splitlines は \x1c-\x1e・\x85 でも切る＝バイナリの行を見失う
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
            self.commits_n += 1
            for mail in {ae, ce}:
                if mail and not NOREPLY_EMAIL.search(mail):
                    hits.append(f"commit {sha} の名義のメール: noreply でない（GitHub の noreply を使う）")
            hits += self.text_hits(f"commit {sha} の名義", f"{an}\n{cn}")
            hits += self.text_hits(f"commit {sha} の説明", body)
        if not self.commits_n:
            self.unchecked.append(f"歴史と外側: 照らす範囲 {' '.join(revs)} に commit が 0（照らす物が無い）")
        return hits


class NoBase(Exception):
    """範囲の元（出所の今の枝の先端）が取れない。呼ぶ側は広い側の元へ名指して倒すか、それも無ければ照らさずに止める。"""


def fresh_main(repo: Path, ref: str = "main") -> str:
    """出所の今の枝 ref（既定 main）の commit。正本は scripts/pr_shape.py の fresh_main（同じ checkout の物を直に読む・写さない）。"""
    src = Path(__file__).resolve().parent.parent / "scripts" / "pr_shape.py"
    if not src.is_file():
        raise NoBase(f"比べる元を決める道具 {src} が無い（土台の checkout 一式から回す）")
    import importlib.util
    spec = importlib.util.spec_from_file_location("af_pr_shape", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        return mod.fresh_main(repo, ref)
    except OSError as e:
        raise NoBase(str(e)) from None


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


def words_unchecked(words_file: str | None, words: list[str]) -> list[str]:
    """名指した置かない語の表に語が 0 なら、その名指し（1 段目は止めない理由。exit 3 には足さない）。"""
    if words_file and not words:
        return [f"置かない語: 表 {words_file} に語が 0（1 段目は止めない。語を入れるか表を外す）"]
    return []


def scan(repo: Path, rev_range: str | None, words_file: str | None, skip: list[str], event: dict | None = None,
         files_only: bool = False) -> tuple[list[str], list[str], Guard]:
    """(当たり, 照らしていない物, guard)。words_file と skip は repo の根からの path。
    files_only は中身だけ（歴史を持ち越さない新しい repo へ移す前）。"""
    words = file_words(repo / words_file if words_file else None)
    guard = Guard(repo, words, set(skip), words_file)
    # 語が 0 は 1 段目: 名指しは main がして exit 0（前の形は止めない）。exit 3 の unchecked には足さない。
    hits = guard.check_files()
    if not files_only:
        event = load_event() if event is None else event
        revs = guard.revs(rev_range, event)
        hits += guard.check_history(revs) + guard.check_meta(revs, event)
    return sorted(set(hits)), guard.unchecked, guard


def run(repo: Path, rev_range: str | None, words_file: str | None, skip: list[str], event: dict | None = None,
        files_only: bool = False) -> list[str]:
    """当たりだけ（照らしていない物は scan が返す）。"""
    return scan(repo, rev_range, words_file, skip, event, files_only)[0]


def check_texts(texts: list[tuple[str, str]], words_file: str | None) -> list[str]:
    """出す前の文（場所の名, 中身）を照らす。words_file は path（相対なら今の dir から）。"""
    # words_home は表そのものの path（中身の照らしで表を外すための物）。文には path が無いので、None と取り違えない値を渡す
    guard = Guard(Path("."), file_words(words_file), set(), words_home=words_file or "")
    hits = []
    for where, text in texts:
        hits += guard.text_hits(where, text)
    return sorted(set(hits))


def main_text(specs: list[str], words_file: str | None) -> int:
    """出す前の文の口。照らしていない物は名指して緑（✅）と言わないが、exit は CI でも 0（守りの hook が 0 以外を止めるため）。"""
    texts = []
    for spec in specs:
        where, sep, path = spec.partition("=")
        if not sep or not where or not path:
            print(f"✗ --text は <場所の名>=<file> の形: {spec}")
            return 2
        try:
            texts.append((where, Path(path).read_text(encoding="utf-8")))
        except OSError as e:
            print(f"✗ 文の file を読めない: {e.__class__.__name__}")
            return 2
    try:
        env_bundle()
    except ValueError as e:
        print(f"✗ AF_DENY_BUNDLE の形が違う（pct1.<鍵>.<束> の 1 行）: {e}")
        return 2
    try:
        unchecked = words_unchecked(words_file, file_words(words_file))
    except OSError as e:
        print(f"✗ 置かない語の表を読めない: {e.__class__.__name__}")
        return 2
    if customer_source_missing():
        unchecked.append("顧客の語（環境に無いので、その照合だけ飛ばした）")
    hits = check_texts(texts, words_file)
    if hits:   # 当たりは先に出す（顧客の語が無くても、照らせた物の当たりを隠さない）
        print("✗ 公開の repo に置かない物:\n  " + "\n  ".join(hits))
        return 1
    if unchecked:
        # 緑（✅）とは言わない。exit は CI でも 0: 守りの hook pr_text は 0 以外を止めるので、ここを 3・1 にすると
        # 顧客の語の無い窓の出す前の文が皆止まる（新しく止める物になる＝オーナーの同意が要る）
        print("公開の検査: 照らしていない（当たりは 0。出す前の文の口は止めない。照らしていない物: "
              + "／".join(unchecked) + "）")
        return 0
    print("✅ 公開の検査: 置かない物 0（出す前の文）")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公開の検査（中身・歴史・外側）")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--range", dest="rev_range")
    ap.add_argument("--deny-words-file")
    ap.add_argument("--pattern-skip", nargs="*", default=[])
    ap.add_argument("--files-only", action="store_true", help="中身だけ（歴史を持ち越さない新しい repo へ移す前）")
    ap.add_argument("--text", action="append", default=[], metavar="場所の名=FILE",
                    help="GitHub へ出す前の文だけを照らす（中身・歴史は見ない）")
    a = ap.parse_args(argv)
    if a.text:
        return main_text(a.text, a.deny_words_file)
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
        named_words = file_words(repo / a.deny_words_file if a.deny_words_file else None)
    except OSError as e:   # 名指した表が無い・読めない（空の表と取り違えて 0 語で照らさない）
        print(f"✗ 置かない語の表 {a.deny_words_file} を読めない: {e.__class__.__name__}")
        return 2
    empty_words = words_unchecked(a.deny_words_file, named_words)
    try:
        hits, unchecked, g = scan(repo, a.rev_range, a.deny_words_file, a.pattern_skip, files_only=a.files_only)
    except NoBase as e:
        print(f"✗ 照らせない: 手元の範囲の元（出所の今の main）が取れない — {e}（--range で範囲を渡すこともできる）")
        return 2
    except subprocess.CalledProcessError as e:
        print(f"✗ git が照らす範囲を読めない（force push の後で前の commit が無い・取り出しが浅い等）: {' '.join(e.cmd[1:4])}")
        if not in_ci():  # 手元の窓は枝だけ・浅い clone が多い。取り方を言う（照らす範囲は main からの差）
            print("  手元の直し: `git fetch origin main`（浅い clone なら `git fetch --deepen=200 origin main` も）で main を取ってから回し直す")
        return 1
    if hits:
        print("✗ 公開の repo に置かない物:\n  " + "\n  ".join(hits))
        return 1
    if customer_source_missing():   # 手元（CI では上で赤）。照合の一部を飛ばしたので緑と言わない
        unchecked = ["顧客の語（環境に無いので、その照合を飛ばした）"] + unchecked
    if unchecked:
        print("公開の検査: 照らしていない（当たりは 0。照らしていない物:）\n  " + "\n  ".join(unchecked))
        if os.environ.get("AF_CHECK_UNCHECKED"):   # 検査の入口 check_all へ訳を渡す（訳の無い 3 は赤）
            Path(os.environ["AF_CHECK_UNCHECKED"]).write_text("照らせない: " + "・".join(unchecked) + "\n", encoding="utf-8")
        return 3
    if empty_words:
        # 1 段目: 語が 0 の表は前の形のまま止めない（使う側の CI をこの PR で赤にしない）。✅ とは言わない。
        # 2 段目で exit 3 にする（古い形 public-guard-empty-deny-words）。
        print("公開の検査: 前の形（" + "／".join(empty_words) + "）。緑の印は出さない")
        return 0
    scope = f"中身 {g.files_n} 個" + ("・歴史と外側は照らさない〔--files-only〕" if a.files_only
                                     else f"・歴史と外側 {g.commits_n} commit")
    print(f"✅ 公開の検査: 置かない物 0（{scope}）")
    return 0


# 当たりで止まる時の最後の行（中身は土台の細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 当たった物を消して出し直すだけで済ませず、置く形になった原因を細目 §3「まず構造を疑う」で探して直す"


def main_with_root_cause(argv=None):
    rc = main(argv)
    if rc == 1:
        print(ROOT_CAUSE)
    return rc


if __name__ == "__main__":
    sys.exit(main_with_root_cause())
